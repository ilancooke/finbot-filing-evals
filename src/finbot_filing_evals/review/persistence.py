"""Local serialized saves with durable, hash-checked roll-forward recovery.

Only .review/ is operational state. A pending v1 journal contains the complete
baseline inventory, planned replacement hashes, transaction id and case path.
Staged bytes and backups are retained; never remove a pending journal by hand.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import io
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
from uuid import uuid4

from .dataset import ReviewDataset, _read_json, load_dataset
from .errors import ReviewError
from .exports import EXPORT_FILES, COLUMNS, build_exports, flat_labels, json_bytes, review_state
from .validation import validate_labels


class SaveConflict(ReviewError):
    """The opened case is stale; retain the caller's pending draft."""


class SynchronizationPending(ReviewError):
    def __init__(self, committed: bool, detail: str):
        self.committed = committed
        message = "Labels saved, exports need retry" if committed else "Nothing saved; synchronization needs retry"
        super().__init__(f"{message}. {detail}")


@dataclass(frozen=True)
class SaveResult:
    dataset: ReviewDataset
    case_id: str
    changed: bool


def _digest(raw: bytes) -> dict:
    return dict(sha256=sha256(raw).hexdigest(), size_bytes=len(raw))


def _target(root: Path, relative: str) -> Path:
    """Writes never follow symlinks, even aliases confined inside the bundle."""
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ReviewError("Invalid writer path.")
    parts = PurePosixPath(relative)
    if parts.is_absolute() or '..' in parts.parts or parts == PurePosixPath('.'):
        raise ReviewError("Writer path must remain inside the dataset.")
    current = root
    for part in parts.parts:
        current /= part
        if current.is_symlink():
            raise ReviewError(f"Writer refuses a symlink: {relative}")
    return current


def inventory(root: Path) -> dict[str, dict]:
    """All bundle files except integrity.json and the explicitly excluded .review/."""
    result = {}
    for path in sorted(root.rglob('*')):
        name = path.relative_to(root).as_posix()
        if name.split('/')[0] == '.review' or name == 'integrity.json':
            continue
        _target(root, name)
        if path.is_file():
            result[name] = _digest(path.read_bytes())
    return result


def _sync_dir(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic(root: Path, relative: str, raw: bytes) -> None:
    target = _target(root, relative)
    # Temporary files stay outside the integrity scope, on the same filesystem.
    fd, temporary = tempfile.mkstemp(prefix='atomic-', dir=_target(root, '.review'))
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        _sync_dir(target.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def synchronization_pending(root: str | Path) -> bool:
    root = Path(root).resolve()
    return _target(root, '.review/pending.json').exists()


@contextmanager
def writer_lock(root: Path):
    state = _target(root, '.review')
    state.mkdir(exist_ok=True)
    _sync_dir(root)
    path = _target(root, '.review/writer.lock')
    with path.open('a+b') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ReviewError("Another local writer holds the dataset lock. Retry shortly.") from error
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _source_snapshots(dataset: ReviewDataset) -> None:
    for case in dataset.cases:
        name = (case.path.parent / 'filing-ready.json').relative_to(dataset.root).as_posix()
        snapshot, _, _ = _read_json(dataset.root, name)
        if snapshot != case.to_dict()['filing']:
            raise ReviewError(f"Source filing manifest differs from case: {case.case_id}")
        _read_json(dataset.root, (case.path.parent / 'provenance.json').relative_to(dataset.root).as_posix())


def verify_bundle(dataset: ReviewDataset) -> dict:
    """Check baseline hashes and export semantics before authorizing any save."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    root = dataset.root
    _target(root, 'integrity.json')
    integrity, _, _ = _read_json(root, 'integrity.json')
    if integrity.get('algorithm') != 'sha256' or integrity.get('files') != inventory(root):
        raise ReviewError("Bundle integrity mismatch; refusing to overwrite unexpected changes.")
    _source_snapshots(dataset)
    rows = flat_labels([case.to_dict() for case in dataset.cases])
    try:
        exported = json.loads(_target(root, 'labels.json').read_bytes())
        table = pq.read_table(_target(root, 'labels.parquet'))
        if exported != rows or table.column_names != list(COLUMNS) or table.to_pylist() != rows:
            raise ReviewError("Label exports differ from authoritative cases.")
        if any(field.type != pa.string() for field in table.schema):
            raise ReviewError("Label Parquet fields must all be strings.")
        metadata, _, _ = _read_json(root, 'labels.metadata.json')
        state = review_state([case.to_dict() for case in dataset.cases])
        expected = dict(row_count=len(rows), sha256=sha256(_target(root, 'labels.parquet').read_bytes()).hexdigest(),
                        partial=not state['human_reviewed'])
        expected.update({k: state[k] for k in ('label_source', 'review_status', 'human_reviewed')})
        if any(metadata.get(key) != value for key, value in expected.items()):
            raise ReviewError("Label metadata differs from authoritative cases/Parquet.")
        for key, value in state.items():
            if key in dataset.to_dict() and dataset.to_dict()[key] != value:
                raise ReviewError(f"Dataset {key} differs from authoritative cases.")
        docs, _, _ = _read_json(root, 'documents.metadata.json')
        doc_bytes = _target(root, 'documents.parquet').read_bytes()
        if docs.get('sha256') != sha256(doc_bytes).hexdigest() or docs.get('row_count') != dataset.document_count:
            raise ReviewError("Document metadata differs from its acquisition manifest.")
        document_rows = pq.read_table(io.BytesIO(doc_bytes)).to_pylist()
        if len(document_rows) != dataset.document_count:
            raise ReviewError("Document manifest count differs from source files.")
        indexed = {row.get('artifact_id'): row for row in document_rows}
        if len(indexed) != dataset.document_count:
            raise ReviewError("Document manifest contains duplicate artifact identities.")
        for case in dataset.cases:
            for document in case.documents:
                row = indexed.get(document.artifact_id, {})
                if row.get('path') != document.relative_path or row.get('sha256') != document.sha256:
                    raise ReviewError("Document manifest differs from the source inventory.")
                if 'size_bytes' in row and row['size_bytes'] != document.size_bytes:
                    raise ReviewError("Document manifest source size differs from the case.")
    except (OSError, ValueError, pa.ArrowException) as error:
        if isinstance(error, ReviewError):
            raise
        raise ReviewError(f"Cannot validate bundle exports: {error}") from error
    return integrity


def _utc(clock) -> str:
    now = clock()
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() != timezone.utc.utcoffset(now):
        raise ReviewError("Save clock must return an explicit UTC datetime.")
    return now.isoformat().replace('+00:00', 'Z')


def _now():
    return datetime.now(timezone.utc)


def _journal(root: Path) -> dict:
    marker, _, _ = _read_json(root, '.review/pending.json')
    if marker.get('version') != 1 or not isinstance(marker.get('transaction'), str):
        raise ReviewError("Unsupported recovery journal; pending state retained.")
    transaction = marker['transaction']
    if len(transaction) != 32 or any(c not in '0123456789abcdef' for c in transaction):
        raise ReviewError("Invalid recovery transaction id.")
    return marker


def _resume(root: Path) -> SaveResult:
    marker = _journal(root)
    baseline = marker['baseline']
    replacements = marker['replacements']
    case_path = marker['case_path']
    dataset = load_dataset(root, validate_counts=False)
    cases = {case.path.relative_to(root).as_posix(): case for case in dataset.cases}
    if case_path not in cases or set(replacements) != {case_path, *EXPORT_FILES, 'integrity.json'}:
        raise ReviewError("Recovery journal has unexpected replacement paths.")
    current = inventory(root)
    if set(current) != set(baseline):
        raise ReviewError("Unexpected bundle file membership during recovery.")
    for name, digest in current.items():
        allowed = [baseline[name]]
        if name in replacements:
            allowed.append(replacements[name])
        if digest not in allowed:
            raise ReviewError(f"Unexpected integrity mismatch during recovery: {name}")
    integrity_digest = _digest(_target(root, 'integrity.json').read_bytes())
    if integrity_digest not in [marker['integrity_before'], replacements['integrity.json']]:
        raise ReviewError("Unexpected integrity manifest change during recovery.")
    staged = {}
    for index, (name, digest) in enumerate(replacements.items()):
        raw = _target(root, f".review/{marker['transaction']}/{index}").read_bytes()
        if _digest(raw) != digest:
            raise ReviewError(f"Recovery staging hash mismatch: {name}")
        staged[name] = raw
    proposal = json.loads(staged[case_path])
    original = json.loads(_target(root, marker['backup']).read_bytes())
    if _digest(_target(root, marker['backup']).read_bytes()) != baseline[case_path]:
        raise ReviewError("Recovery backup differs from the baseline case.")
    if _digest(json_bytes(original)) != marker['backup_canonical']:
        raise ReviewError("Recovery backup hash mismatch.")
    if {k: v for k, v in proposal.items() if k not in {'labels', 'review'}} != {k: v for k, v in original.items() if k not in {'labels', 'review'}}:
        raise ReviewError("Recovery may only replace labels and review state.")
    validate_labels(proposal['labels'])
    expected_review = dict(original['review'])
    expected_review.update(status='unreviewed', reviewed_at_utc=None)
    if proposal['review'] != expected_review:
        raise ReviewError("Recovery review state differs from the intended label-save transition.")
    _source_snapshots(dataset)
    records = [proposal if case.case_id == proposal['case_id'] else case.to_dict() for case in dataset.cases]
    # Rebuild from the authoritative cases plus the journal's intended case. This
    # checks staged exports instead of blindly replaying arbitrary cached bytes.
    rebuilt = build_exports(dataset, records, json.loads(staged['labels.metadata.json']), marker['timestamp'])
    if any(rebuilt[name] != staged[name] for name in EXPORT_FILES):
        raise ReviewError("Recovery exports do not match authoritative cases.")
    expected = dict(baseline)
    expected.update({name: digest for name, digest in replacements.items() if name != 'integrity.json'})
    final_integrity = json.loads(staged['integrity.json'])
    if final_integrity.get('algorithm') != 'sha256' or final_integrity.get('files') != expected:
        raise ReviewError("Recovery final integrity does not match planned replacements.")
    # Ordered journal: case first, exports next, integrity last.
    for name in (case_path, *EXPORT_FILES, 'integrity.json'):
        _atomic(root, name, staged[name])
    result = load_dataset(root)
    verify_bundle(result)
    _target(root, '.review/pending.json').unlink()
    try:
        _sync_dir(_target(root, '.review'))
    except OSError:
        # A failed durable deletion must still be reported as a committed save
        # needing retry, with its recovery record available in the running app.
        _atomic(root, '.review/pending.json', json_bytes(marker))
        raise
    return SaveResult(result, proposal['case_id'], proposal['labels'] != original['labels'])


def _pending_error(root: Path, error: Exception) -> SynchronizationPending:
    committed = False
    try:
        marker = _journal(root)
        committed = _digest(_target(root, marker['case_path']).read_bytes()) == marker['replacements'][marker['case_path']]
    except Exception:
        pass
    return SynchronizationPending(committed, str(error))


def retry_synchronization(root: str | Path) -> SaveResult:
    """Roll forward a verified interrupted save under the same local lock."""
    root = Path(root).resolve(strict=True)
    try:
        with writer_lock(root):
            if not synchronization_pending(root):
                raise ReviewError("There is no pending synchronization to retry.")
            try:
                return _resume(root)
            except Exception as error:
                raise _pending_error(root, error) from error
    except OSError as error:
        raise ReviewError(f"Cannot acquire dataset writer state: {error}") from error


def save_changes(root: str | Path, case_id: str, opened_fingerprint: str, labels: dict, *, clock=None) -> SaveResult:
    """Persist valid labels without confirmation; retain existing review notes."""
    root = Path(root).resolve(strict=True)
    try:
        with writer_lock(root):
            if synchronization_pending(root):
                raise ReviewError("Synchronization pending. Retry synchronization before saving again.")
            dataset = load_dataset(root)
            case = next((case for case in dataset.cases if case.case_id == case_id), None)
            if case is None:
                raise ReviewError(f"Unknown case: {case_id}")
            if case.fingerprint != opened_fingerprint:
                raise SaveConflict("Saved case changed outside this session. Pending edits retained; reopen the saved case before retrying.")
            validate_labels(labels)
            integrity = verify_bundle(dataset)
            baseline = dict(integrity['files'])
            integrity_before = _digest(_target(root, 'integrity.json').read_bytes())
            original = case.to_dict()
            if labels == original['labels']:
                return SaveResult(dataset, case_id, False)
            timestamp = _utc(clock or _now)
            proposal = case.to_dict()
            proposal['labels'] = labels
            proposal['review'].update(status='unreviewed', reviewed_at_utc=None)
            records = [proposal if item.case_id == case_id else item.to_dict() for item in dataset.cases]
            metadata, _, _ = _read_json(root, 'labels.metadata.json')
            case_path = case.path.relative_to(root).as_posix()
            replacements = {case_path: json_bytes(proposal), **build_exports(dataset, records, metadata, timestamp)}
            updated = dict(integrity['files'])
            updated.update({name: _digest(raw) for name, raw in replacements.items()})
            integrity.update(files=updated, scope='Current bundle; excludes integrity.json and .review/.', updated_at_utc=timestamp)
            replacements['integrity.json'] = json_bytes(integrity)
            transaction = uuid4().hex
            directory = _target(root, f'.review/{transaction}')
            directory.mkdir()
            _sync_dir(directory.parent)
            backup = f'.review/{transaction}/case.before.json'
            _atomic(root, backup, case.path.read_bytes())
            marker = dict(version=1, transaction=transaction, case_path=case_path, backup=backup,
                          backup_canonical=_digest(json_bytes(original)), timestamp=timestamp,
                          baseline=baseline, integrity_before=integrity_before,
                          replacements={name: _digest(raw) for name, raw in replacements.items()})
            for index, raw in enumerate(replacements.values()):
                _atomic(root, f'.review/{transaction}/{index}', raw)
            _atomic(root, '.review/pending.json', json_bytes(marker))
            try:
                return _resume(root)
            except Exception as error:
                raise _pending_error(root, error) from error
    except OSError as error:
        if synchronization_pending(root):
            raise _pending_error(root, error) from error
        raise ReviewError(f"Nothing saved. Cannot prepare dataset save: {error}") from error
