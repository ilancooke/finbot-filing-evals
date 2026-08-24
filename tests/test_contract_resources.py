import copy

import pytest
from jsonschema import Draft202012Validator

from finbot_filing_evals.golden_dataset import versions
from finbot_filing_evals.golden_dataset._resources import (
    ResourceIntegrityError,
    UnknownResourceVersionError,
)
from finbot_filing_evals.golden_dataset import prompts
from finbot_filing_evals.golden_dataset.prompts import load_prompt, prompt_sha256
from finbot_filing_evals.golden_dataset.schemas import (
    load_visual_table_schema,
    schema_sha256,
)


def test_schema_is_valid_strict_and_freshly_loaded() -> None:
    first = load_visual_table_schema()
    Draft202012Validator.check_schema(first)

    assert first["additionalProperties"] is False
    assert first["$defs"]["row"]["additionalProperties"] is False
    assert first["$defs"]["column"]["additionalProperties"] is False
    assert first["$defs"]["cell"]["additionalProperties"] is False
    assert "statement_id" not in first["properties"]

    modified = copy.deepcopy(first)
    modified["title"] = "changed locally"
    assert load_visual_table_schema()["title"] == "Visual Table Extraction V1"


def test_packaged_contract_hashes_are_pinned() -> None:
    assert prompt_sha256() == versions.VISUAL_TABLE_EXTRACTION_PROMPT_SHA256
    assert schema_sha256() == versions.VISUAL_TABLE_EXTRACTION_SCHEMA_SHA256


def test_prompt_contains_required_visual_only_rules() -> None:
    prompt = load_prompt()

    assert "record what the statement visibly says" in prompt
    assert "Do not map labels to canonical accounting concepts" in prompt
    assert 'value_raw ""' in prompt
    assert 'row_kind "section_heading"' in prompt
    assert "Three Months Ended" in prompt
    assert "Nine Months Ended" in prompt
    assert "(171)" in prompt


def test_unknown_contract_version_fails_clearly() -> None:
    with pytest.raises(UnknownResourceVersionError, match="unknown resource version"):
        load_prompt("visual_table_extraction_v999")
    with pytest.raises(UnknownResourceVersionError, match="unknown resource version"):
        load_visual_table_schema("visual_table_extraction.v999")


def test_modified_prompt_digest_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    version = versions.VISUAL_TABLE_EXTRACTION_PROMPT_VERSION
    filename, _digest = prompts._PROMPTS[version]
    monkeypatch.setitem(prompts._PROMPTS, version, (filename, "0" * 64))

    with pytest.raises(ResourceIntegrityError, match="expected"):
        load_prompt(version)

