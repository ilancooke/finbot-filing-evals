"""Read and validate authoritative local cases without importing UI/provider code."""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from types import MappingProxyType
from typing import Any

from .errors import ReviewError
from .validation import (
    METRICS,
    SCHEMA_VERSION,
    load_label_schema,
    require_object,
    require_text,
    validate_labels,
)

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_ACCESSION = re.compile(r"\d{10}-\d{2}-\d{6}\Z", re.ASCII)
_FORMS = {"8-K", "8-K/A", "6-K", "6-K/A", "10-Q", "10-Q/A", "10-K", "10-K/A"}
_SNAPSHOT_FIELDS = (
    "filing_id", "cik", "ticker", "company_name", "form_type", "filed_at",
    "primary_artifact_id", "artifacts",
)


def safe_file(root: Path, relative: Any) -> Path:
    """Resolve a required file, rejecting absolute/traversal/escaping symlink paths."""
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ReviewError("Dataset file paths must be nonempty relative POSIX paths.")
    parts = PurePosixPath(relative)
    if parts.is_absolute() or ".." in parts.parts or parts == PurePosixPath("."):
        raise ReviewError(f"Dataset file path must stay inside the dataset: {relative}")
    try:
        path = (root / relative).resolve(strict=True)
        if not path.is_relative_to(root):
            raise ReviewError(f"Dataset file path escapes the dataset: {relative}")
        if not path.is_file():
            raise ReviewError(f"Expected a dataset file: {relative}")
        return path
    except (OSError, RuntimeError) as error:
        raise ReviewError(f"Cannot read dataset file: {relative} ({error.strerror if isinstance(error, OSError) else 'symlink loop'})") from error


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise ReviewError(f"Cannot read dataset file: {path.name} ({error.strerror})") from error


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    record = {}
    for key, value in pairs:
        if key in record:
            raise ValueError(f"duplicate JSON key: {key}")
        record[key] = value
    return record


def _nonfinite(value: str) -> None:
    raise ValueError(f"nonfinite JSON number: {value}")


def _read_json(root: Path, relative: str) -> tuple[dict[str, Any], bytes, Path]:
    path = safe_file(root, relative)
    try:
        with path.open("rb") as source:
            raw = source.read(4 * 1024 * 1024 + 1)
    except OSError as error:
        raise ReviewError(f"Cannot read dataset JSON: {relative} ({error.strerror})") from error
    if len(raw) > 4 * 1024 * 1024:
        raise ReviewError(f"Dataset JSON exceeds the 4 MiB limit: {relative}")
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_nonfinite)
    except (ValueError, UnicodeError) as error:
        raise ReviewError(f"Invalid JSON in {relative}: {error}") from error
    return require_object(value, relative), raw, path


def _hash(value: Any, location: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise ReviewError(f"{location} must be a lowercase SHA-256 digest.")
    return value


@dataclass(frozen=True)
class Observation:
    value: str
    currency: str
    period: str
    period_start: str | None
    period_end: str

    def to_dict(self) -> dict[str, Any]:
        return dict(value=self.value, currency=self.currency, period=self.period,
                    period_start=self.period_start, period_end=self.period_end)


@dataclass(frozen=True)
class SourceDocument:
    root: Path
    relative_path: str
    artifact_id: str
    filename: str
    sha256: str
    size_bytes: int
    document_type: str | None
    content_type: str | None

    @property
    def path(self) -> Path:
        return safe_file(self.root, self.relative_path)

    def read_bytes(self) -> bytes:
        """Recheck confinement and content on access, not just at initial load."""
        raw = _read_bytes(self.path)
        if len(raw) != self.size_bytes:
            raise ReviewError(f"Source size mismatch: {self.relative_path}")
        if hashlib.sha256(raw).hexdigest() != self.sha256:
            raise ReviewError(f"Source SHA-256 mismatch: {self.relative_path}")
        return raw


@dataclass(frozen=True)
class ReviewCase:
    case_id: str
    path: Path
    fingerprint: str
    ticker: str
    form_type: str
    filing_id: str
    snapshot_id: str
    primary_artifact_id: str
    documents: tuple[SourceDocument, ...]
    labels: Mapping[str, tuple[Observation, ...]]
    review_status: str
    notes: tuple[str, ...]
    _record: dict[str, Any] = field(repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        """Lossless independent copy, including unknown upstream metadata."""
        return deepcopy(self._record)

    @property
    def observation_count(self) -> int:
        return sum(len(rows) for rows in self.labels.values())


@dataclass(frozen=True)
class ReviewDataset:
    root: Path
    dataset_id: str
    fingerprint: str
    cases: tuple[ReviewCase, ...]
    _manifest: dict[str, Any] = field(repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self._manifest)

    @property
    def document_count(self) -> int:
        return sum(len(case.documents) for case in self.cases)

    @property
    def observation_count(self) -> int:
        return sum(case.observation_count for case in self.cases)


def _review(record: dict[str, Any], location: str) -> tuple[str, tuple[str, ...]]:
    review = require_object(record.get("review"), f"{location}.review")
    status = review.get("status")
    if not isinstance(status, str) or status not in {"unreviewed", "human_reviewed"}:
        raise ReviewError(f"{location}.review.status must be unreviewed or human_reviewed.")
    notes = review.get("notes")
    if not isinstance(notes, list) or any(not isinstance(note, str) for note in notes):
        raise ReviewError(f"{location}.review.notes must be a list of strings.")
    timestamp = review.get("reviewed_at_utc")
    if status == "human_reviewed":
        try:
            parsed = datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else None
        except ValueError:
            parsed = None
        if parsed is None or parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
            raise ReviewError(f"{location}.review.reviewed_at_utc must be an explicit UTC timestamp for a reviewed case.")
    elif timestamp is not None:
        raise ReviewError(f"{location}.review.reviewed_at_utc must be null for an unreviewed case.")
    return status, tuple(notes)


def _case(root: Path, relative: str) -> ReviewCase:
    record, raw, path = _read_json(root, relative)
    case_id = require_text(record, "case_id", relative)
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", case_id) is None:
        raise ReviewError(f"{relative}.case_id must be a filename-safe identifier.")
    if path.name != "case.json" or path.parent.name != case_id:
        raise ReviewError(f"{relative}: case_id does not match its case directory.")
    filing = require_object(record.get("filing"), f"{relative}.filing")
    text = {key: require_text(filing, key, f"{relative}.filing") for key in _SNAPSHOT_FIELDS if key != "artifacts"}
    filing_id = text["filing_id"]
    if _ACCESSION.fullmatch(filing_id) is None:
        raise ReviewError(f"{relative}.filing.filing_id must be a dashed SEC accession.")
    if re.fullmatch(r"[0-9]{10}", text["cik"]) is None:
        raise ReviewError(f"{relative}.filing.cik must have ten digits.")
    if text["form_type"] not in _FORMS:
        raise ReviewError(f"{relative}.filing.form_type is not a supported SEC filing type.")
    if filing.get("event_type") != "filing.ready" or filing.get("schema_version") != "1.0":
        raise ReviewError(f"{relative}.filing must contain a FilingReady 1.0 manifest.")
    snapshot = _hash(filing.get("snapshot_id"), f"{relative}.filing.snapshot_id")
    artifacts = filing.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ReviewError(f"{relative}.filing.artifacts must be a nonempty list.")
    mappings = require_object(record.get("documents"), f"{relative}.documents")
    documents = []
    artifact_ids = set()
    source_paths = set()
    for index, value in enumerate(artifacts):
        location = f"{relative}.filing.artifacts[{index}]"
        artifact = require_object(value, location)
        artifact_id = require_text(artifact, "artifact_id", location)
        filename = require_text(artifact, "filename", location)
        if filename in {".", ".."} or "/" in filename or "\\" in filename or any(ord(char) < 32 for char in filename):
            raise ReviewError(f"{location}.filename must be a safe basename.")
        if artifact_id != f"{filing_id}/{filename}" or artifact_id in artifact_ids:
            raise ReviewError(f"{location}: artifact identity is inconsistent or duplicated.")
        artifact_ids.add(artifact_id)
        size = artifact.get("size_bytes")
        if type(size) is not int or size < 0:
            raise ReviewError(f"{location}.size_bytes must be a nonnegative integer.")
        require_text(artifact, "s3_uri", location)  # Provenance only; never fetched.
        for key in ("document_type", "content_type"):
            if key in artifact and not isinstance(artifact[key], str):
                raise ReviewError(f"{location}.{key} must be a string when present.")
        mapping = require_object(mappings.get(artifact_id), f"{relative}.documents[{artifact_id}]")
        source_name = require_text(mapping, "path", f"{relative}.documents[{artifact_id}]")
        source_path = safe_file(root, source_name)
        if source_path.name != filename or source_path in source_paths:
            raise ReviewError(f"{location}: document filename/path is inconsistent or duplicated.")
        source_paths.add(source_path)
        document = SourceDocument(
            root, source_name, artifact_id, filename,
            _hash(mapping.get("sha256"), f"{relative}.documents[{artifact_id}].sha256"),
            size, artifact.get("document_type"), artifact.get("content_type"),
        )
        document.read_bytes()
        documents.append(document)
    if set(mappings) != artifact_ids or text["primary_artifact_id"] not in artifact_ids:
        raise ReviewError(f"{relative}: documents must cover the complete manifest, including the primary artifact.")
    canonical = {key: filing[key] for key in _SNAPSHOT_FIELDS}
    canonical["artifacts"] = sorted(artifacts, key=lambda artifact: artifact["artifact_id"])
    expected = hashlib.sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if snapshot != expected:
        raise ReviewError(f"{relative}.filing.snapshot_id does not match its filing manifest.")
    validate_labels(record.get("labels"), location=f"{relative}.labels")
    status, notes = _review(record, relative)
    labels = MappingProxyType({metric: tuple(Observation(**row) for row in record["labels"][metric]) for metric in METRICS})
    return ReviewCase(case_id, path, hashlib.sha256(raw).hexdigest(), text["ticker"],
                      text["form_type"], filing_id, snapshot, text["primary_artifact_id"],
                      tuple(documents), labels, status, notes, deepcopy(record))


def load_dataset(root: str | Path, *, validate_counts: bool = True) -> ReviewDataset:
    """Load authoritative cases in manifest order; never read/write derived exports."""
    try:
        directory = Path(root).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ReviewError(f"Dataset directory is unavailable: {root}") from error
    if not directory.is_dir():
        raise ReviewError(f"Dataset root must be a directory: {directory}")
    manifest, raw, _ = _read_json(directory, "dataset.json")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ReviewError(f"Unsupported dataset schema_version; expected {SCHEMA_VERSION}.")
    dataset_id = require_text(manifest, "dataset_id", "dataset.json")
    names = manifest.get("cases")
    if not isinstance(names, list) or not names or any(not isinstance(name, str) for name in names):
        raise ReviewError("dataset.json.cases must be a nonempty list of relative case paths.")
    schema_name = require_text(manifest, "label_schema", "dataset.json")
    schema, _, _ = _read_json(directory, schema_name)
    if schema != load_label_schema():
        raise ReviewError("Dataset label_schema differs from the supported earnings_eps.v1 contract.")
    seen_paths, seen_ids, seen_snapshots, seen_artifacts = set(), set(), set(), set()
    cases = []
    for name in names:
        path = safe_file(directory, name)
        if path in seen_paths:
            raise ReviewError(f"Repeated case path in dataset.json: {name}")
        seen_paths.add(path)
        case = _case(directory, name)
        identity = (case.filing_id, case.snapshot_id)
        if case.case_id in seen_ids or identity in seen_snapshots:
            raise ReviewError(f"Repeated case identity or filing snapshot: {case.case_id}")
        if any(document.artifact_id in seen_artifacts for document in case.documents):
            raise ReviewError(f"Repeated document identity across cases: {case.case_id}")
        seen_ids.add(case.case_id)
        seen_snapshots.add(identity)
        seen_artifacts.update(document.artifact_id for document in case.documents)
        cases.append(case)
    dataset = ReviewDataset(directory, dataset_id, hashlib.sha256(raw).hexdigest(), tuple(cases), deepcopy(manifest))
    for key, count in (("case_count", len(cases)), ("document_count", dataset.document_count), ("observation_count", dataset.observation_count)):
        if validate_counts and key in manifest and (type(manifest[key]) is not int or manifest[key] != count):
            raise ReviewError(f"dataset.json.{key} does not match the authoritative case files ({count}).")
    return dataset
