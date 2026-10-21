from pathlib import Path

import pytest

from finbot_filing_evals.review import ReviewError, resolve_dataset_root
from finbot_filing_evals.review.config import DEFAULT_DATASET_SUBPATH, parse_config, parse_dataset_root


def test_explicit_dataset_overrides_environment_without_creating_paths(tmp_path):
    explicit = tmp_path / "not-created"
    assert resolve_dataset_root(explicit, environ={"FINBOT_DATA_ROOT": str(tmp_path / "other")}) == explicit
    assert not explicit.exists()


def test_default_is_derived_only_from_explicit_environment(tmp_path):
    assert resolve_dataset_root(environ={"FINBOT_DATA_ROOT": str(tmp_path)}) == tmp_path / DEFAULT_DATASET_SUBPATH


@pytest.mark.parametrize("environ", [{}, {"FINBOT_DATA_ROOT": ""}, {"FINBOT_DATA_ROOT": "   "}])
def test_missing_environment_is_actionable(environ):
    with pytest.raises(ReviewError, match="FINBOT_DATA_ROOT.*--dataset-root"):
        resolve_dataset_root(environ=environ)


def test_no_dotenv_loading_or_silent_fallback(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("FINBOT_DATA_ROOT=/ignored/root\n")
    with pytest.raises(ReviewError):
        resolve_dataset_root(environ={})


def test_cli_override(monkeypatch, tmp_path):
    monkeypatch.delenv("FINBOT_DATA_ROOT", raising=False)
    assert parse_dataset_root(["--dataset-root", str(tmp_path)]) == tmp_path


def test_empty_override_is_rejected():
    with pytest.raises(ReviewError, match="--dataset-root"):
        resolve_dataset_root("", environ={"FINBOT_DATA_ROOT": "/ignored"})


def test_catalog_config_canonical_explicit_and_copy_paths(monkeypatch, tmp_path):
    shared = tmp_path / "shared"
    monkeypatch.setenv("FINBOT_DATA_ROOT", str(shared))
    config = parse_config([])
    assert config.catalog_enabled
    assert config.catalog_repo.name == "finbot-catalog"
    assert config.catalog_repo.parent == Path(__file__).resolve().parents[2]
    canonical = shared / DEFAULT_DATASET_SUBPATH
    assert parse_config(["--dataset-root", str(canonical)]).catalog_enabled
    alias = tmp_path / "alias"
    shared.mkdir()
    alias.symlink_to(shared, target_is_directory=True)
    assert parse_config(["--dataset-root", str(alias / DEFAULT_DATASET_SUBPATH)]).catalog_enabled
    copied = parse_config(["--dataset-root", str(tmp_path / "copy"), "--catalog-repo", str(tmp_path / "custom")])
    assert not copied.catalog_enabled
    assert copied.catalog_repo == tmp_path / "custom"
    monkeypatch.delenv("FINBOT_DATA_ROOT")
    assert not parse_config(["--dataset-root", str(canonical)]).catalog_enabled
