from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import multiprocessing

import pytest

from conftest import prepare_bundle, save_json
from finbot_filing_evals.review.dataset import load_dataset
from finbot_filing_evals.review.errors import ReviewError
from finbot_filing_evals.review import persistence as p

NOW = datetime(2026, 10, 20, 12, 30, tzinfo=timezone.utc)


def opened(root):
    case = load_dataset(root).cases[0]
    labels = case.to_dict()['labels']
    labels['reported_diluted_eps'][0]['value'] = '-4.60'
    return case, labels


def save(root, case, labels):
    return p.save_changes(root, case.case_id, case.fingerprint, labels, clock=lambda: NOW)


def test_save_reopen_backup_exports_and_sources(writable_dataset):
    root = writable_dataset
    case, labels = opened(root)
    original = case.path.read_bytes()
    before = p.inventory(root)
    manifest = load_dataset(root).to_dict()
    result = save(root, case, labels)
    assert result.changed
    reopened = load_dataset(root).cases[0]
    assert reopened.to_dict()['labels'] == labels
    assert reopened.notes == case.notes
    assert reopened.to_dict()['filing'] == case.to_dict()['filing']
    assert reopened.to_dict()['custom_case_metadata'] == {'keep': True}
    assert reopened.review_status == 'unreviewed'
    assert reopened.to_dict()['review']['reviewed_at_utc'] is None
    assert [f.read_bytes() for f in (root / '.review').glob('*/case.before.json')] == [original]
    assert not p.synchronization_pending(root)
    p.verify_bundle(result.dataset)
    after = p.inventory(root)
    changed = {case.path.relative_to(root).as_posix(), *p.EXPORT_FILES}
    assert all(after[name] == digest for name, digest in before.items() if name not in changed)
    metadata = json.loads((root / 'labels.metadata.json').read_text())
    assert metadata['created_at_utc'] == '2026-01-01T00:00:00Z'
    assert metadata['generated_at_utc'] == '2026-10-20T12:30:00Z'
    assert metadata['custom_acquisition_field'] == {'keep': 1}
    assert result.dataset.to_dict()['created_at_utc'] == manifest['created_at_utc']
    assert 'Review note for DEMO.' in (root / 'REVIEW.md').read_text()
    import pyarrow.parquet as pq
    rows = pq.read_table(root / 'labels.parquet').to_pylist()
    assert rows[0]['value'] == '-4.60'
    assert rows[0]['period_start'] is None
    assert rows[2]['currency'] == 'TWD'


@pytest.mark.parametrize('mode', ['empty', 'add', 'delete'])
def test_observation_count_changes(writable_dataset, mode):
    case, labels = opened(writable_dataset)
    if mode == 'empty':
        labels = {metric: [] for metric in labels}
    elif mode == 'add':
        labels['adjusted_diluted_eps'] = [dict(value='0.00', currency='USD', period='Q3', period_start=None, period_end='2026-09-30')]
    else:
        labels['reported_diluted_eps'].pop()
    result = save(writable_dataset, case, labels)
    p.verify_bundle(result.dataset)
    expected = 1 + sum(len(rows) for rows in labels.values())
    assert result.dataset.to_dict()['observation_count'] == expected
    assert json.loads((writable_dataset / 'labels.metadata.json').read_text())['row_count'] == expected


def test_stale_second_session_cannot_overwrite(writable_dataset):
    case, labels = opened(writable_dataset)
    save(writable_dataset, case, labels)
    before = p.inventory(writable_dataset)
    labels['reported_diluted_eps'][0]['value'] = '8.00'
    with pytest.raises(p.SaveConflict, match='Pending edits retained'):
        save(writable_dataset, case, labels)
    assert p.inventory(writable_dataset) == before
    assert labels['reported_diluted_eps'][0]['value'] == '8.00'


def test_noop_preserves_confirmation_and_changed_labels_invalidate(writable_dataset):
    case = load_dataset(writable_dataset).cases[0]
    record = case.to_dict()
    record['review'].update(status='human_reviewed', reviewed_at_utc='2026-10-19T00:00:00Z', reviewer_extra={'keep': 1})
    save_json(case.path, record)
    prepare_bundle(writable_dataset)
    case = load_dataset(writable_dataset).cases[0]
    before = p.inventory(writable_dataset)
    result = save(writable_dataset, case, case.to_dict()['labels'])
    assert not result.changed
    assert p.inventory(writable_dataset) == before
    assert not list((writable_dataset / '.review').glob('*/case.before.json'))
    case, labels = opened(writable_dataset)
    result = save(writable_dataset, case, labels)
    review = result.dataset.cases[0].to_dict()['review']
    assert review == dict(status='unreviewed', notes=case.to_dict()['review']['notes'], reviewed_at_utc=None, reviewer_extra={'keep': 1})


@pytest.mark.parametrize('labels_mode', ['unchanged', 'corrected', 'empty'])
def test_confirmation_saves_labels_timestamp_and_exports(writable_dataset, labels_mode):
    root = writable_dataset
    case = load_dataset(root).cases[0]
    labels = case.to_dict()['labels']
    if labels_mode == 'corrected':
        labels['reported_diluted_eps'][0]['value'] = '-4.60'
    elif labels_mode == 'empty':
        labels = {metric: [] for metric in labels}
    before = p.inventory(root)
    original = case.path.read_bytes()
    result = p.confirm_case(root, case.case_id, case.fingerprint, labels, clock=lambda: NOW)
    assert result.changed  # Confirmation alone is a durable case change.
    confirmed = load_dataset(root).cases[0]
    assert confirmed.to_dict()['labels'] == labels
    assert confirmed.to_dict()['review'] == dict(
        status='human_reviewed', reviewed_at_utc='2026-10-20T12:30:00Z', notes=list(case.notes),
    )
    assert confirmed.to_dict()['filing'] == case.to_dict()['filing']
    assert [f.read_bytes() for f in (root / '.review').glob('*/case.before.json')] == [original]
    p.verify_bundle(result.dataset)
    after = p.inventory(root)
    changed = {case.path.relative_to(root).as_posix(), *p.EXPORT_FILES}
    assert all(after[name] == digest for name, digest in before.items() if name not in changed)
    rows = json.loads((root / 'labels.json').read_text())
    assert all(row['review_status'] == 'human_reviewed' for row in rows if row['case_id'] == case.case_id)
    assert result.dataset.to_dict()['review_status'] == 'in_progress'
    noop = save(root, confirmed, labels)
    assert not noop.changed
    assert p.inventory(root) == after
    labels = deepcopy(labels)
    labels['adjusted_diluted_eps'] = [dict(
        value='0.00', currency='USD', period='Q3', period_start=None, period_end='2026-09-30',
    )]
    invalidated = save(root, confirmed, labels).dataset.cases[0]
    assert invalidated.review_status == 'unreviewed'
    assert invalidated.to_dict()['review']['reviewed_at_utc'] is None


def test_confirmation_uses_injected_utc_clock_and_preserves_review_extras(writable_dataset):
    root = writable_dataset
    case = load_dataset(root).cases[0]
    record = case.to_dict()
    record['review']['reviewer_extra'] = {'keep': True}
    save_json(case.path, record)
    prepare_bundle(root)
    case = load_dataset(root).cases[0]
    before = p.inventory(root)
    for invalid in (datetime(2026, 10, 20), '2026-10-20T00:00:00Z'):
        with pytest.raises(ReviewError, match='explicit UTC'):
            p.confirm_case(root, case.case_id, case.fingerprint, case.to_dict()['labels'], clock=lambda: invalid)
    assert p.inventory(root) == before
    result = p.confirm_case(root, case.case_id, case.fingerprint, case.to_dict()['labels'], clock=lambda: NOW)
    reviewed = result.dataset.cases[0]
    later = datetime(2026, 10, 21, tzinfo=timezone.utc)
    renewed = p.confirm_case(root, case.case_id, reviewed.fingerprint, reviewed.to_dict()['labels'], clock=lambda: later)
    assert renewed.dataset.cases[0].to_dict()['review'] == dict(
        status='human_reviewed', notes=list(case.notes), reviewed_at_utc='2026-10-21T00:00:00Z',
        reviewer_extra={'keep': True},
    )


def test_confirmation_refuses_stale_or_invalid_labels(writable_dataset):
    root = writable_dataset
    case, labels = opened(root)
    invalid = deepcopy(labels)
    invalid['reported_diluted_eps'][0]['value'] = 'NaN'
    before = p.inventory(root)
    with pytest.raises(ReviewError):
        p.confirm_case(root, case.case_id, case.fingerprint, invalid, clock=lambda: NOW)
    assert p.inventory(root) == before
    save(root, case, labels)
    before = p.inventory(root)
    with pytest.raises(p.SaveConflict):
        p.confirm_case(root, case.case_id, case.fingerprint, labels, clock=lambda: NOW)
    assert p.inventory(root) == before


@pytest.mark.parametrize('fail_at', ['case', 'labels.json', 'integrity.json'])
def test_interrupted_confirmation_recovers_exact_review_transition(writable_dataset, monkeypatch, fail_at):
    root = writable_dataset
    case, labels = opened(root)
    atomic = p._atomic
    def fail(root, name, raw):
        if name == (case.path.relative_to(root).as_posix() if fail_at == 'case' else fail_at):
            raise OSError('interrupted confirmation')
        return atomic(root, name, raw)
    with monkeypatch.context() as m:
        m.setattr(p, '_atomic', fail)
        with pytest.raises(p.SynchronizationPending) as error:
            p.confirm_case(root, case.case_id, case.fingerprint, labels, clock=lambda: NOW)
    assert error.value.committed == (fail_at != 'case')
    recovered = p.retry_synchronization(root)
    assert recovered.changed
    assert recovered.dataset.cases[0].to_dict()['labels'] == labels
    assert recovered.dataset.cases[0].to_dict()['review']['reviewed_at_utc'] == '2026-10-20T12:30:00Z'
    assert recovered.dataset.cases[0].review_status == 'human_reviewed'
    p.verify_bundle(recovered.dataset)


@pytest.mark.parametrize('action', [None, 'confirm', 'unknown'])
def test_recovery_action_validates_transition_and_supports_step4_journals(writable_dataset, monkeypatch, action):
    root = writable_dataset
    case, labels = opened(root)
    atomic = p._atomic
    def fail(root, name, raw):
        if name == 'labels.json':
            raise OSError('stop after commit')
        return atomic(root, name, raw)
    with monkeypatch.context() as m:
        m.setattr(p, '_atomic', fail)
        with pytest.raises(p.SynchronizationPending):
            save(root, case, labels)
    marker_path = root / '.review/pending.json'
    marker = json.loads(marker_path.read_text())
    if action is None:
        marker.pop('action')  # Exact Step 4 v1 journal format.
    else:
        marker['action'] = action
    save_json(marker_path, marker)
    if action is None:
        recovered = p.retry_synchronization(root)
        assert recovered.dataset.cases[0].review_status == 'unreviewed'
        p.verify_bundle(recovered.dataset)
    else:
        before = p.inventory(root)
        with pytest.raises(p.SynchronizationPending, match='review transition|Unknown review action'):
            p.retry_synchronization(root)
        assert p.inventory(root) == before
        assert p.synchronization_pending(root)


@pytest.mark.parametrize('reviewed', [0, 1, 2])
def test_aggregate_and_row_review_states(writable_dataset, reviewed):
    for case in load_dataset(writable_dataset).cases[:reviewed]:
        record = case.to_dict()
        record['review'].update(status='human_reviewed', reviewed_at_utc='2026-10-19T00:00:00Z')
        save_json(case.path, record)
    prepare_bundle(writable_dataset)
    dataset = load_dataset(writable_dataset)
    p.verify_bundle(dataset)
    manifest = dataset.to_dict()
    assert manifest['review_status'] == ['unreviewed', 'in_progress', 'human_reviewed'][reviewed]
    assert manifest['human_reviewed'] == (reviewed == 2)
    assert manifest['label_source'] == ('human_reviewed' if reviewed == 2 else 'agent_draft')
    rows = json.loads((writable_dataset / 'labels.json').read_text())
    assert rows[0]['review_status'] == ('human_reviewed' if reviewed else 'unreviewed')
    assert rows[-1]['review_status'] == ('human_reviewed' if reviewed == 2 else 'unreviewed')
    if reviewed == 2:
        case, labels = opened(writable_dataset)
        saved = save(writable_dataset, case, labels).dataset
        assert saved.to_dict()['review_status'] == 'in_progress'
        assert json.loads((writable_dataset / 'labels.metadata.json').read_text())['partial']


def test_confirm_all_then_edit_reverts_manifest_metadata_and_every_export_row(writable_dataset):
    import pyarrow.parquet as pq

    root = writable_dataset

    def assert_state(expected):
        dataset = load_dataset(root)
        p.verify_bundle(dataset)
        reviewed = sum(value == 'human_reviewed' for value in expected.values())
        status = 'human_reviewed' if reviewed == 2 else 'in_progress' if reviewed else 'unreviewed'
        for record in (dataset.to_dict(), json.loads((root / 'labels.metadata.json').read_text())):
            assert record['reviewed_case_count'] == reviewed
            assert record['unreviewed_case_count'] == 2 - reviewed
            assert record['review_status'] == status
            assert record['human_reviewed'] == (reviewed == 2)
            assert record['label_source'] == ('human_reviewed' if reviewed == 2 else 'agent_draft')
        metadata = json.loads((root / 'labels.metadata.json').read_text())
        assert metadata['partial'] == (reviewed != 2)
        rows = json.loads((root / 'labels.json').read_text())
        assert pq.read_table(root / 'labels.parquet').to_pylist() == rows
        assert all(row['review_status'] == expected[row['case_id']] for row in rows)
        return dataset

    expected = {case.case_id: 'unreviewed' for case in load_dataset(root).cases}
    dataset = assert_state(expected)
    for case in dataset.cases:
        current = next(item for item in load_dataset(root).cases if item.case_id == case.case_id)
        p.confirm_case(root, current.case_id, current.fingerprint, current.to_dict()['labels'], clock=lambda: NOW)
        expected[case.case_id] = 'human_reviewed'
        assert_state(expected)
    case, labels = opened(root)
    save(root, case, labels)
    expected[case.case_id] = 'unreviewed'
    assert_state(expected)


@pytest.mark.parametrize('fail_at,committed', [('case', False), ('labels.json', True), ('dataset.json', True), ('integrity.json', True), ('verify', True), ('clear', True), ('clear_sync', True)])
def test_interrupted_save_recovers_after_restart(writable_dataset, monkeypatch, fail_at, committed):
    root = writable_dataset
    case, labels = opened(root)
    # Change count too: interrupted load must not require stale manifest counts.
    labels['reported_diluted_eps'].pop()
    original_atomic = p._atomic
    original_verify = p.verify_bundle
    original_unlink = p.Path.unlink
    original_sync = p._sync_dir

    def fail_atomic(root, name, raw):
        if name == (case.path.relative_to(root).as_posix() if fail_at == 'case' else fail_at):
            raise OSError('injected write failure')
        return original_atomic(root, name, raw)

    calls = []
    def fail_verify(dataset):
        calls.append(1)
        if len(calls) == 2:
            raise OSError('injected verification failure')
        return original_verify(dataset)

    def fail_unlink(path, *args, **kwargs):
        if path.name == 'pending.json':
            raise OSError('injected marker cleanup failure')
        return original_unlink(path, *args, **kwargs)

    def fail_sync(directory):
        if directory.name == '.review' and not p.synchronization_pending(root) and sha256(case.path.read_bytes()).hexdigest() != case.fingerprint:
            raise OSError('injected marker deletion sync failure')
        return original_sync(directory)

    with monkeypatch.context() as m:
        m.setattr(p, '_atomic', fail_atomic)
        if fail_at == 'verify': m.setattr(p, 'verify_bundle', fail_verify)
        if fail_at == 'clear': m.setattr(p.Path, 'unlink', fail_unlink)
        if fail_at == 'clear_sync': m.setattr(p, '_sync_dir', fail_sync)
        with pytest.raises(p.SynchronizationPending) as error:
            save(root, case, labels)
        assert error.value.committed == committed
    assert p.synchronization_pending(root)
    assert load_dataset(root, validate_counts=False).cases[0].to_dict()['labels'] == (labels if committed else case.to_dict()['labels'])
    with pytest.raises(ReviewError, match='pending'):
        save(root, case, labels)
    recovered = p.retry_synchronization(root)
    assert recovered.dataset.cases[0].to_dict()['labels'] == labels
    p.verify_bundle(recovered.dataset)
    assert not p.synchronization_pending(root)


@pytest.mark.parametrize('target', ['case', 'source', 'provenance', 'export', 'integrity', 'added', 'staged'])
def test_recovery_refuses_unexpected_changes(writable_dataset, monkeypatch, target):
    root = writable_dataset
    case, labels = opened(root)
    atomic = p._atomic
    def fail(root, name, raw):
        if name == 'labels.json': raise OSError('stop after commit')
        return atomic(root, name, raw)
    with monkeypatch.context() as m:
        m.setattr(p, '_atomic', fail)
        with pytest.raises(p.SynchronizationPending): save(root, case, labels)
    paths = dict(case=case.path, source=case.documents[0].path,
                 provenance=case.path.parent / 'provenance.json', export=root / 'labels.json',
                 integrity=root / 'integrity.json', added=root / 'unexpected.txt',
                 staged=next((root / '.review').glob('*/0')))
    path = paths[target]
    path.write_bytes(path.read_bytes() + b' ' if path.exists() else b'unexpected')
    before = {f: f.read_bytes() for f in root.rglob('*') if f.is_file()}
    with pytest.raises(p.SynchronizationPending): p.retry_synchronization(root)
    assert {f: f.read_bytes() for f in root.rglob('*') if f.is_file()} == before
    assert p.synchronization_pending(root)


@pytest.mark.parametrize('target', ['source', 'provenance', 'labels.json', 'missing_integrity', 'invalid_labels', 'manifest'])
def test_preflight_failure_does_not_commit(writable_dataset, target):
    root = writable_dataset
    case, labels = opened(root)
    if target == 'invalid_labels': labels['reported_diluted_eps'][0]['value'] = 'NaN'
    elif target == 'missing_integrity': (root / 'integrity.json').unlink()
    elif target == 'manifest':
        path = case.path.parent / 'filing-ready.json'
        record = json.loads(path.read_text()); record['ready_at'] = 'changed'; save_json(path, record)
        save_json(root / 'integrity.json', {'algorithm': 'sha256', 'files': p.inventory(root)})
    else:
        path = case.documents[0].path if target == 'source' else case.path.parent / 'provenance.json' if target == 'provenance' else root / target
        path.write_bytes(path.read_bytes() + b' ')
    before = case.path.read_bytes()
    with pytest.raises(ReviewError): save(root, case, labels)
    assert case.path.read_bytes() == before
    assert not p.synchronization_pending(root)


def _try_lock(root, connection):
    try:
        with p.writer_lock(root):
            connection.send('acquired')
    except ReviewError:
        connection.send('blocked')
    finally:
        connection.close()


def test_lock_serializes_processes_and_releases_on_exit(writable_dataset):
    ctx = multiprocessing.get_context('fork')
    # Fork before locking so the child doesn't inherit the lock descriptor.
    parent, child = ctx.Pipe()
    def worker():
        child.recv()
        _try_lock(writable_dataset, child)
    process = ctx.Process(target=worker)
    process.start()
    try:
        with p.writer_lock(writable_dataset):
            parent.send('go')
            assert parent.poll(5)
            assert parent.recv() == 'blocked'
        process.join(5)
        assert process.exitcode == 0
        with p.writer_lock(writable_dataset): pass
    finally:
        if process.is_alive(): process.terminate(); process.join()
        parent.close()


@pytest.mark.parametrize('target', ['.review', 'labels.json', 'case'])
def test_writer_refuses_symlinks(writable_dataset, tmp_path, target):
    root = writable_dataset
    case, labels = opened(root)
    path = case.path if target == 'case' else root / target
    outside = tmp_path / 'external'
    if target == '.review': outside.mkdir()
    else: outside.write_bytes(path.read_bytes()); path.unlink()
    path.symlink_to(outside, target_is_directory=target == '.review')
    with pytest.raises(ReviewError, match='symlink|escapes the dataset'):
        save(root, case, labels)
    if outside.is_dir():
        assert not list(outside.iterdir())
    else:
        assert outside.read_bytes() == path.read_bytes()


def test_legacy_initial_exports_are_accepted_and_creation_time_retained(writable_dataset):
    import pyarrow as pa
    import pyarrow.parquet as pq
    from finbot_filing_evals.review.exports import COLUMNS

    root = writable_dataset
    manifest = json.loads((root / 'dataset.json').read_text())
    for key in ('updated_at_utc', 'reviewed_case_count', 'unreviewed_case_count'):
        manifest.pop(key, None)
    save_json(root / 'dataset.json', manifest)
    # Recreate the original flat format independently of build_exports.
    rows = []
    for case in load_dataset(root).cases:
        record = case.to_dict()
        for metric in ('reported_diluted_eps', 'adjusted_diluted_eps'):
            rows.extend(dict(case_id=case.case_id, ticker=case.ticker, filing_id=case.filing_id,
                             form_type=case.form_type, metric=metric, **observation,
                             review_status=case.review_status) for observation in record['labels'][metric])
    save_json(root / 'labels.json', rows)
    pq.write_table(pa.Table.from_pylist(rows, schema=pa.schema([(name, pa.string()) for name in COLUMNS])), root / 'labels.parquet')
    save_json(root / 'labels.metadata.json', dict(
        dataset_name='legacy.labels', generated_at_utc='2026-01-01T00:00:00Z',
        provider='original-acquisition', row_count=4, partial=True, label_source='agent_draft',
        review_status='unreviewed', human_reviewed=False,
        sha256=sha256((root / 'labels.parquet').read_bytes()).hexdigest(),
    ))
    (root / 'REVIEW.md').write_text('Initial draft. All observations await review.')
    save_json(root / 'integrity.json', dict(algorithm='sha256', files=p.inventory(root)))
    case, labels = opened(root)
    saved = save(root, case, labels)
    metadata = json.loads((root / 'labels.metadata.json').read_text())
    assert metadata['created_at_utc'] == '2026-01-01T00:00:00Z'
    assert metadata['provider'] == 'original-acquisition'
    assert saved.dataset.to_dict()['created_at_utc'] == manifest['created_at_utc']
    p.verify_bundle(saved.dataset)


def test_fully_empty_labels_keep_the_string_parquet_schema(writable_dataset):
    import pyarrow as pa
    import pyarrow.parquet as pq
    for case in load_dataset(writable_dataset).cases:
        save(writable_dataset, case, dict(reported_diluted_eps=[], adjusted_diluted_eps=[]))
    dataset = load_dataset(writable_dataset)
    p.verify_bundle(dataset)
    table = pq.read_table(writable_dataset / 'labels.parquet')
    assert table.num_rows == 0
    assert all(field.type == pa.string() for field in table.schema)
    assert json.loads((writable_dataset / 'labels.json').read_text()) == []
    assert dataset.to_dict()['observation_count'] == 0


@pytest.mark.parametrize('phase', ['staging', 'marker', 'marker_fsync'])
def test_failure_preparing_journal_does_not_commit(writable_dataset, monkeypatch, phase):
    root = writable_dataset
    case, labels = opened(root)
    before = p.inventory(root)
    atomic = p._atomic
    def fail(root, name, raw):
        if phase == 'staging' and name.endswith('/0'):
            raise OSError('staging unavailable')
        if phase == 'marker' and name == '.review/pending.json':
            raise OSError('marker unavailable')
        result = atomic(root, name, raw)
        if phase == 'marker_fsync' and name == '.review/pending.json':
            raise OSError('marker replaced but sync failed')
        return result
    with monkeypatch.context() as m:
        m.setattr(p, '_atomic', fail)
        with pytest.raises(ReviewError, match='Nothing saved'):
            save(root, case, labels)
    assert p.inventory(root) == before
    assert p.synchronization_pending(root) == (phase == 'marker_fsync')
    if phase == 'marker_fsync':
        p.retry_synchronization(root)
        assert load_dataset(root).cases[0].to_dict()['labels'] == labels
    else:
        save(root, case, labels)


def test_uncaught_interruption_keeps_durable_recovery_record(writable_dataset, monkeypatch):
    class ProcessStopped(BaseException):
        pass
    case, labels = opened(writable_dataset)
    atomic = p._atomic
    def stopped(root, name, raw):
        if name == 'labels.parquet': raise ProcessStopped()
        return atomic(root, name, raw)
    with monkeypatch.context() as m:
        m.setattr(p, '_atomic', stopped)
        with pytest.raises(ProcessStopped): save(writable_dataset, case, labels)
    assert p.synchronization_pending(writable_dataset)
    recovered = p.retry_synchronization(writable_dataset)
    assert recovered.dataset.cases[0].to_dict()['labels'] == labels


def test_process_exit_releases_lock_without_removing_lockfile(writable_dataset):
    ctx = multiprocessing.get_context('fork')
    parent, child = ctx.Pipe()
    def owner():
        with p.writer_lock(writable_dataset):
            child.send('locked')
            child.recv()
    process = ctx.Process(target=owner)
    process.start()
    try:
        assert parent.poll(5)
        assert parent.recv() == 'locked'
        with pytest.raises(ReviewError, match='Another local writer'):
            with p.writer_lock(writable_dataset): pass
        process.terminate()
        process.join(5)
        assert (writable_dataset / '.review/writer.lock').exists()
        with p.writer_lock(writable_dataset): pass
    finally:
        if process.is_alive(): process.terminate(); process.join()
        parent.close()


def test_document_inventory_semantic_mismatch_is_refused(writable_dataset):
    import pyarrow as pa
    import pyarrow.parquet as pq
    root = writable_dataset
    rows = pq.read_table(root / 'documents.parquet').to_pylist()
    rows[0]['path'] = 'incorrect.htm'
    pq.write_table(pa.Table.from_pylist(rows), root / 'documents.parquet')
    metadata = json.loads((root / 'documents.metadata.json').read_text())
    metadata['sha256'] = sha256((root / 'documents.parquet').read_bytes()).hexdigest()
    save_json(root / 'documents.metadata.json', metadata)
    save_json(root / 'integrity.json', dict(algorithm='sha256', files=p.inventory(root)))
    case, labels = opened(root)
    with pytest.raises(ReviewError, match='source inventory'):
        save(root, case, labels)
