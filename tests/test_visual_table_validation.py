from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from finbot_filing_evals.golden_dataset.models import (
    FilingType,
    RowKind,
    SourceImage,
    StatementMetadata,
    StatementType,
)
from finbot_filing_evals.golden_dataset.validation import (
    VisualTableValidationError,
    parse_visual_table_response,
    validate_visual_table_response,
)


FIXTURES = Path(__file__).parent / "fixtures" / "golden_dataset"


def _payload(name: str = "valid_visual_table_v1.json") -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _source_statement(tmp_path: Path) -> StatementMetadata:
    digest = "b" * 64
    return StatementMetadata(
        statement_id="AAPL_10Q_income_statement",
        ticker="AAPL",
        filing_type=FilingType.FORM_10_Q,
        statement_type=StatementType.INCOME_STATEMENT,
        source_image=SourceImage(
            source_file=(tmp_path / "10q income statement.png").resolve(),
            source_image_id=f"sha256:{digest}",
            sha256=digest,
        ),
    )


def test_valid_fixture_hydrates_self_contained_cells(tmp_path: Path) -> None:
    payload = _payload()

    annotation = parse_visual_table_response(payload, _source_statement(tmp_path))

    assert annotation.statement.statement_id == "AAPL_10Q_income_statement"
    assert annotation.statement.statement_title_raw == payload["statement_title_raw"]
    assert annotation.statement.units_raw == payload["units_raw"]
    assert annotation.rows[0].row_kind is RowKind.SECTION_HEADING
    assert annotation.rows[1].row_path_raw == (
        "Net sales",
        "Products¹",
        "Domestic",
    )
    assert annotation.cells[0].row_path_raw == annotation.rows[1].row_path_raw
    assert annotation.cells[0].column_path_raw == annotation.columns[0].column_path_raw
    assert annotation.cells[0].value_raw == " 78,678 "
    assert annotation.cells[5].value_raw == ""
    assert annotation.cells[7].value_raw == "—"


def test_json_round_trip_preserves_all_raw_strings(tmp_path: Path) -> None:
    payload = _payload()
    round_tripped = json.loads(json.dumps(payload, ensure_ascii=False))

    annotation = parse_visual_table_response(
        round_tripped, _source_statement(tmp_path)
    )

    assert annotation.statement.statement_title_raw == payload["statement_title_raw"]
    assert annotation.statement.units_raw == payload["units_raw"]
    assert annotation.rows[1].row_path_raw[1] == "Products¹"
    assert [cell.value_raw for cell in annotation.cells] == [
        cell["value_raw"] for cell in payload["cells"]
    ]


def test_more_than_two_level_row_and_column_paths_validate() -> None:
    payload = _payload()
    payload["columns"][0]["column_path_raw"].insert(0, "Results")

    validate_visual_table_response(payload)

    assert len(payload["rows"][1]["row_path_raw"]) == 3
    assert len(payload["columns"][0]["column_path_raw"]) == 3


@pytest.mark.parametrize(
    ("mutation", "expected_message"),
    [
        (lambda data: data["rows"][1].update(row_index=2), "contiguous and zero-based"),
        (lambda data: data["rows"][1]["row_path_raw"].append("  "), "visible text"),
        (lambda data: data["cells"].reverse(), "must be ordered"),
        (lambda data: data["cells"].append(dict(data["cells"][-1])), "duplicate"),
        (lambda data: data["cells"][0].update(row_index=0), "section-heading"),
        (lambda data: data["cells"][0].update(row_index=99), "existing row"),
        (lambda data: data.update(statement_title_raw="  "), "visible text or be null"),
    ],
)
def test_semantically_malformed_responses_fail_clearly(
    mutation: Any,
    expected_message: str,
) -> None:
    payload = _payload()
    mutation(payload)

    with pytest.raises(VisualTableValidationError, match=expected_message):
        validate_visual_table_response(payload)


def test_unused_data_row_is_rejected() -> None:
    payload = _payload()
    payload["cells"] = [cell for cell in payload["cells"] if cell["row_index"] != 2]

    with pytest.raises(VisualTableValidationError, match="data rows must contain"):
        validate_visual_table_response(payload)


def test_unused_column_is_rejected() -> None:
    payload = _payload()
    payload["cells"] = [
        cell for cell in payload["cells"] if cell["column_index"] != 3
    ]

    with pytest.raises(VisualTableValidationError, match="columns must contain"):
        validate_visual_table_response(payload)


def test_schema_rejects_missing_wrong_and_extra_fields() -> None:
    invalid_extra = _payload("invalid_visual_table_v1.json")
    with pytest.raises(VisualTableValidationError, match="Additional properties"):
        validate_visual_table_response(invalid_extra)

    missing = _payload()
    del missing["units_raw"]
    with pytest.raises(VisualTableValidationError, match="required property"):
        validate_visual_table_response(missing)

    wrong_type = _payload()
    wrong_type["cells"][0]["value_raw"] = 78678
    with pytest.raises(VisualTableValidationError, match="not of type 'string'"):
        validate_visual_table_response(wrong_type)


def test_validation_does_not_mutate_provider_payload() -> None:
    payload = _payload()
    before = copy.deepcopy(payload)

    validate_visual_table_response(payload)

    assert payload == before
