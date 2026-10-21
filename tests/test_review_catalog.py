import json
import shutil
import subprocess

import pytest

from finbot_filing_evals.review import catalog
from finbot_filing_evals.review.config import ReviewConfig
from finbot_filing_evals.review.dataset import load_dataset
from finbot_filing_evals.review.errors import ReviewError
from finbot_filing_evals.review.persistence import confirm_case, inventory, verify_bundle


def _confirm(config):
    case = next(case for case in load_dataset(config.dataset_root).cases if case.review_status == 'unreviewed')
    return confirm_case(config.dataset_root, case.case_id, case.fingerprint, case.to_dict()['labels'])


def test_adapter_uses_argument_list_and_receipt_tracks_saved_revision(catalog_config, monkeypatch):
    config = catalog_config
    assert catalog.refresh_status(config) == "unknown"
    _confirm(config)
    assert catalog.refresh_status(config) == "pending"  # save-to-adapter interruption
    before = inventory(config.dataset_root)
    calls = []

    def run(args, **kwargs):
        assert catalog.refresh_status(config) == 'pending'
        calls.append((args, kwargs))

    monkeypatch.setattr(catalog.subprocess, 'run', run)
    assert catalog.refresh_catalog(config)
    assert calls == [([
        str(config.catalog_repo / '.venv/bin/python'),
        str(config.catalog_repo / 'scripts/build_catalog.py'),
        '--data-root', str(config.data_root),
    ], dict(cwd=config.catalog_repo, check=True, capture_output=True, text=True, timeout=60))]
    assert inventory(config.dataset_root) == before
    verify_bundle(load_dataset(config.dataset_root))
    assert catalog.refresh_status(config) == 'current'
    # A later save changes the digest even if it repeats a confirmation.
    _confirm(config)
    assert catalog.refresh_status(config) == 'pending'


@pytest.mark.parametrize('problem', ['missing_python', 'missing_script', 'permission', 'nonzero', 'timeout'])
def test_catalog_failure_is_durable_and_retry_preserves_labels(catalog_config, monkeypatch, problem):
    config = catalog_config
    _confirm(config)
    monkeypatch.setattr(catalog.subprocess, 'run', lambda *args, **kwargs: None)
    catalog.refresh_catalog(config)
    assert catalog.refresh_status(config) == 'current'
    before = inventory(config.dataset_root)
    missing = None
    if problem.startswith('missing'):
        missing = config.catalog_repo / ('.venv/bin/python' if problem == 'missing_python' else 'scripts/build_catalog.py')
        missing.unlink()
    else:
        def fail(*args, **kwargs):
            if problem == 'permission':
                raise PermissionError('not executable')
            if problem == 'timeout':
                raise subprocess.TimeoutExpired(args[0], 60)
            raise subprocess.CalledProcessError(2, args[0], stderr='sensitive output not displayed')
        monkeypatch.setattr(catalog.subprocess, 'run', fail)
    with pytest.raises(ReviewError) as error:
        catalog.refresh_catalog(config)
    assert 'sensitive' not in str(error.value)
    # Fresh config/receipt read, independent of any UI session.
    assert catalog.refresh_status(ReviewConfig(config.dataset_root, config.data_root, config.catalog_repo)) == 'pending'
    assert inventory(config.dataset_root) == before
    assert load_dataset(config.dataset_root).cases[0].review_status == 'human_reviewed'
    if missing:
        missing.touch()
    monkeypatch.setattr(catalog.subprocess, 'run', lambda *args, **kwargs: None)
    catalog.refresh_catalog(config)
    assert catalog.refresh_status(config) == 'current'


@pytest.mark.parametrize('shared', [None, 'different'])
def test_noncanonical_copy_never_launches_or_writes(writable_dataset, tmp_path, shared):
    config = ReviewConfig(writable_dataset, tmp_path / shared if shared else None, tmp_path / 'absent')
    before = inventory(writable_dataset)
    assert catalog.refresh_status(config) == 'disabled'
    assert not catalog.refresh_catalog(config)
    assert not (writable_dataset / '.review').exists()
    assert inventory(writable_dataset) == before


@pytest.mark.parametrize('problem', ['pending', 'corrupt_exports', 'receipt_symlink'])
def test_adapter_refuses_unsynchronized_or_unexpected_bundle(catalog_config, problem):
    config = catalog_config
    root = config.dataset_root
    (root / '.review').mkdir()
    if problem == 'pending':
        (root / '.review/pending.json').write_text('{}')
    elif problem == 'corrupt_exports':
        (root / 'labels.json').write_text('[]')
    else:
        (root / '.review/catalog-refresh.json').symlink_to(root / 'labels.json')
    with pytest.raises(ReviewError):
        catalog.refresh_catalog(config)
    assert catalog.refresh_status(config) in {'pending', 'unknown'}


@pytest.mark.parametrize('raw', ['bad json', '[]', '{}', '{"status":"success","integrity_sha256":"stale"}'])
def test_bad_receipt_never_claims_freshness(catalog_config, raw):
    root = catalog_config.dataset_root
    (root / '.review').mkdir()
    (root / catalog.RECEIPT).write_text(raw)
    assert catalog.refresh_status(catalog_config) == 'pending'


def test_receipt_failure_retains_pending_after_cli_success(catalog_config, monkeypatch):
    _confirm(catalog_config)
    monkeypatch.setattr(catalog.subprocess, 'run', lambda *args, **kwargs: None)
    original = catalog._atomic

    def fail(root, path, raw):
        if json.loads(raw).get('status') == 'success':
            raise OSError('receipt write failed')
        original(root, path, raw)

    monkeypatch.setattr(catalog, '_atomic', fail)
    with pytest.raises(ReviewError, match='record refresh success'):
        catalog.refresh_catalog(catalog_config)
    assert catalog.refresh_status(catalog_config) == 'pending'


def test_moving_bundle_to_another_shared_root_does_not_transfer_freshness(catalog_config, monkeypatch, tmp_path):
    from finbot_filing_evals.review.config import DEFAULT_DATASET_SUBPATH

    config = catalog_config
    _confirm(config)
    monkeypatch.setattr(catalog.subprocess, 'run', lambda *args, **kwargs: None)
    catalog.refresh_catalog(config)
    other = tmp_path / 'other shared'
    destination = other / DEFAULT_DATASET_SUBPATH
    destination.parent.mkdir(parents=True)
    shutil.copytree(config.dataset_root, destination)
    assert catalog.refresh_status(ReviewConfig(destination, other, config.catalog_repo)) == 'pending'
