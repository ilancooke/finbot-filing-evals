from copy import deepcopy
import hashlib
import json

import pytest

from finbot_filing_evals.review import ReviewError, load_dataset
from conftest import save_json, snapshot


def test_load_is_ordered_read_only_and_lossless(dataset_root):
    before = {p: p.read_bytes() for p in dataset_root.rglob("*") if p.is_file()}
    dataset = load_dataset(dataset_root)
    assert [case.ticker for case in dataset.cases] == ["DEMO", "NEXT"]
    assert (len(dataset.cases), dataset.document_count, dataset.observation_count) == (2, 3, 4)
    case = dataset.cases[0]
    assert case.fingerprint == hashlib.sha256(case.path.read_bytes()).hexdigest()
    assert case.to_dict() == json.loads(case.path.read_text())
    copy = case.to_dict()
    copy["filing"]["extra_upstream_field"]["retain"].append("changed")
    assert case.to_dict()["filing"]["extra_upstream_field"] == {"retain": ["original"]}
    assert dataset.to_dict()["custom_dataset_metadata"] == {"keep": [1, 2]}
    with pytest.raises(TypeError):
        case.labels["reported_diluted_eps"] = ()
    assert {p: p.read_bytes() for p in dataset_root.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("mode", ["missing", "file", "missing_manifest", "invalid_json", "duplicate_json_key", "nonfinite_json", "array_json"])
def test_bad_dataset_inputs_are_actionable(tmp_path, dataset_root, mode):
    path = dataset_root
    expected = "."
    if mode == "missing":
        path = tmp_path / "does-not-exist"
        expected = "unavailable"
    elif mode == "file":
        path = dataset_root / "dataset.json"
        expected = "directory"
    elif mode == "missing_manifest":
        (dataset_root / "dataset.json").unlink()
        expected = "dataset.json"
    else:
        payload = {"invalid_json": "{", "duplicate_json_key": '{"cases":[],"cases":[]}',
                   "nonfinite_json": '{"bad":NaN}', "array_json": "[]"}[mode]
        (dataset_root / "dataset.json").write_text(payload)
    with pytest.raises(ReviewError, match=expected):
        load_dataset(path)


@pytest.mark.parametrize(("key", "value", "expected"), [
    ("schema_version", "earnings_eps.v999", "schema_version"),
    ("cases", [], "nonempty"), ("cases", [1], "case paths"),
    ("case_count", 14, "case_count"), ("document_count", True, "document_count"),
    ("observation_count", 99, "observation_count"),
])
def test_invalid_manifest(dataset_root, key, value, expected):
    manifest = json.loads((dataset_root / "dataset.json").read_text())
    manifest[key] = value
    save_json(dataset_root / "dataset.json", manifest)
    with pytest.raises(ReviewError, match=expected):
        load_dataset(dataset_root)


def test_duplicate_case_paths_are_rejected(dataset_root):
    manifest = json.loads((dataset_root / "dataset.json").read_text())
    manifest["cases"].append(manifest["cases"][0])
    save_json(dataset_root / "dataset.json", manifest)
    with pytest.raises(ReviewError, match="Repeated case path"):
        load_dataset(dataset_root)


def test_duplicate_filing_snapshot_is_rejected(dataset_root, case_file):
    record = json.loads(case_file.read_text())
    record["case_id"] = "clone"
    clone = dataset_root / "cases/clone/case.json"
    clone.parent.mkdir()
    save_json(clone, record)
    manifest = json.loads((dataset_root / "dataset.json").read_text())
    manifest["cases"].append("cases/clone/case.json")
    save_json(dataset_root / "dataset.json", manifest)
    with pytest.raises(ReviewError, match="Repeated case identity or filing snapshot"):
        load_dataset(dataset_root)


@pytest.mark.parametrize("mode", ["wrong_case_id", "bad_accession", "bad_cik", "bad_form", "bad_event", "bad_snapshot",
                                  "missing_mapping", "extra_mapping", "bad_primary", "bad_artifact_id", "duplicate_artifact",
                                  "bad_filename", "bad_size", "bad_hash", "source_missing", "source_size", "source_hash",
                                  "bad_labels", "bad_notes", "bad_status"])
def test_invalid_case_data(dataset_root, case_file, mode):
    record = json.loads(case_file.read_text())
    artifact = record["filing"]["artifacts"][0]
    artifact_id = artifact["artifact_id"]
    mapping = record["documents"][artifact_id]
    source = dataset_root / mapping["path"]
    if mode == "wrong_case_id": record["case_id"] = "different"
    elif mode == "bad_accession": record["filing"]["filing_id"] = "bad"
    elif mode == "bad_cik": record["filing"]["cik"] = "1"
    elif mode == "bad_form": record["filing"]["form_type"] = "DEF 14A"
    elif mode == "bad_event": record["filing"]["event_type"] = "artifact.ready"
    elif mode == "bad_snapshot": record["filing"]["snapshot_id"] = "a" * 64
    elif mode == "missing_mapping": del record["documents"][artifact_id]
    elif mode == "extra_mapping": record["documents"]["extra"] = deepcopy(mapping)
    elif mode == "bad_primary": record["filing"]["primary_artifact_id"] = "not-selected"
    elif mode == "bad_artifact_id": artifact["artifact_id"] = "other/primary.htm"
    elif mode == "duplicate_artifact": record["filing"]["artifacts"].append(deepcopy(artifact))
    elif mode == "bad_filename": artifact["filename"] = "../primary.htm"
    elif mode == "bad_size": artifact["size_bytes"] = True
    elif mode == "bad_hash": mapping["sha256"] = "invalid"
    elif mode == "source_missing": source.unlink()
    elif mode == "source_size": source.write_bytes(b"short")
    elif mode == "source_hash":
        raw = source.read_bytes()
        source.write_bytes(b"x" + raw[1:])
    elif mode == "bad_labels": record["labels"]["reported_diluted_eps"][0]["value"] = 4.6
    elif mode == "bad_notes": record["review"]["notes"] = "not a list"
    elif mode == "bad_status": record["review"]["status"] = {}
    save_json(case_file, record)
    with pytest.raises(ReviewError):
        load_dataset(dataset_root)


@pytest.mark.parametrize("mode", ["absolute_source", "traversal_source", "symlink_source", "symlink_case", "symlink_schema"])
def test_escaping_paths_never_read_external_data(dataset_root, case_file, tmp_path, mode):
    record = json.loads(case_file.read_text())
    artifact_id = record["filing"]["artifacts"][0]["artifact_id"]
    mapping = record["documents"][artifact_id]
    source = dataset_root / mapping["path"]
    outside = tmp_path / source.name
    outside.write_bytes(source.read_bytes())
    if mode == "absolute_source": mapping["path"] = str(outside)
    elif mode == "traversal_source": mapping["path"] = "../" + outside.name
    elif mode == "symlink_source":
        source.unlink()
        source.symlink_to(outside)
    elif mode == "symlink_case":
        external_case = tmp_path / "external-case.json"
        external_case.write_bytes(case_file.read_bytes())
        case_file.unlink()
        case_file.symlink_to(external_case)
    else:
        external_schema = tmp_path / "schema.json"
        schema = dataset_root / "labels.schema.json"
        external_schema.write_bytes(schema.read_bytes())
        schema.unlink()
        schema.symlink_to(external_schema)
    if mode != "symlink_case": save_json(case_file, record)
    with pytest.raises(ReviewError, match="inside the dataset|escapes the dataset"):
        load_dataset(dataset_root)


def test_schema_drift_is_rejected_without_resolving_untrusted_references(dataset_root):
    save_json(dataset_root / "labels.schema.json", {"$ref": "https://example.invalid/schema"})
    with pytest.raises(ReviewError, match="label_schema differs"):
        load_dataset(dataset_root)


def test_oversized_json_fails_before_parsing(dataset_root):
    (dataset_root / "dataset.json").write_bytes(b" " * (4 * 1024 * 1024 + 1))
    with pytest.raises(ReviewError, match="4 MiB limit"):
        load_dataset(dataset_root)


def test_source_access_rechecks_changes_after_initial_load(dataset_root):
    document = load_dataset(dataset_root).cases[0].documents[0]
    path = document.path
    raw = path.read_bytes()
    path.write_bytes(b"x" + raw[1:])
    with pytest.raises(ReviewError, match="SHA-256 mismatch"):
        document.read_bytes()


def test_source_access_rechecks_symlink_confinement(dataset_root, tmp_path):
    document = load_dataset(dataset_root).cases[0].documents[0]
    path = document.path
    outside = tmp_path / path.name
    outside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(ReviewError, match="escapes the dataset"):
        document.read_bytes()


def test_case_fingerprint_tracks_exact_bytes(dataset_root, case_file):
    first = load_dataset(dataset_root).cases[0]
    case_file.write_bytes(case_file.read_bytes() + b"\n")
    second = load_dataset(dataset_root).cases[0]
    assert first.to_dict() == second.to_dict()
    assert first.fingerprint != second.fingerprint


@pytest.mark.parametrize("timestamp", [None, "not-a-date", "2026-10-15T10:00:00", "2026-10-15T11:00:00+01:00"])
def test_reviewed_cases_require_an_explicit_utc_timestamp(dataset_root, case_file, timestamp):
    record = json.loads(case_file.read_text())
    record["review"].update(status="human_reviewed", reviewed_at_utc=timestamp)
    save_json(case_file, record)
    with pytest.raises(ReviewError, match="reviewed_at_utc"):
        load_dataset(dataset_root)


def test_reviewed_status_and_unknown_metadata_survive(dataset_root, case_file):
    record = json.loads(case_file.read_text())
    record["review"].update(status="human_reviewed", reviewed_at_utc="2026-10-15T10:00:00Z", reviewer_extension={"keep": 1})
    save_json(case_file, record)
    case = load_dataset(dataset_root).cases[0]
    assert case.review_status == "human_reviewed"
    assert case.to_dict()["review"] == record["review"]
