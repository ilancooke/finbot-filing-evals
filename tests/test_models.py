from datetime import UTC, datetime
from pathlib import Path

import pytest

from finbot_filing_evals.golden_dataset.models import (
    CellAnnotation,
    ColumnAnnotation,
    ExtractionRequest,
    ExtractionResult,
    ExtractionStatus,
    FilingType,
    Provider,
    RowAnnotation,
    RowKind,
    SourceImage,
    StatementAnnotation,
    StatementMetadata,
    StatementType,
)


def _statement(tmp_path: Path) -> StatementMetadata:
    digest = "a" * 64
    return StatementMetadata(
        statement_id="AAPL_10Q_income_statement",
        ticker="AAPL",
        filing_type=FilingType.FORM_10_Q,
        statement_type=StatementType.INCOME_STATEMENT,
        source_image=SourceImage(
            source_file=(tmp_path / "image.png").resolve(),
            source_image_id=f"sha256:{digest}",
            sha256=digest,
        ),
        statement_title_raw="CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS",
        units_raw="(In millions)",
    )


def _annotation(tmp_path: Path) -> StatementAnnotation:
    statement = _statement(tmp_path)
    row = RowAnnotation(
        statement_id=statement.statement_id,
        row_index=0,
        row_path_raw=("Net sales", "Products"),
        row_kind=RowKind.DATA,
    )
    column = ColumnAnnotation(
        statement_id=statement.statement_id,
        column_index=0,
        column_path_raw=("Three Months Ended", "June 27, 2026"),
    )
    cell = CellAnnotation(
        statement_id=statement.statement_id,
        row_index=0,
        row_path_raw=row.row_path_raw,
        column_index=0,
        column_path_raw=column.column_path_raw,
        value_raw="(171)",
    )
    return StatementAnnotation(
        statement=statement,
        rows=(row,),
        columns=(column,),
        cells=(cell,),
    )


def test_cell_preserves_hierarchical_paths_and_raw_value(tmp_path: Path) -> None:
    annotation = _annotation(tmp_path)

    assert annotation.cells[0].row_path_raw == ("Net sales", "Products")
    assert annotation.cells[0].column_path_raw == (
        "Three Months Ended",
        "June 27, 2026",
    )
    assert annotation.cells[0].value_raw == "(171)"


def test_cell_rejects_empty_hierarchy(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="row_path_raw"):
        CellAnnotation(
            statement_id=_statement(tmp_path).statement_id,
            row_index=0,
            row_path_raw=(),
            column_index=0,
            column_path_raw=("2026",),
            value_raw="",
        )


def test_cell_rejects_mutable_path_sequences(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="row_path_raw must be a tuple"):
        CellAnnotation(
            statement_id=_statement(tmp_path).statement_id,
            row_index=0,
            row_path_raw=["Net sales"],  # type: ignore[arg-type]
            column_index=0,
            column_path_raw=("2026",),
            value_raw="1",
        )


def test_success_result_requires_raw_and_parsed_responses(tmp_path: Path) -> None:
    statement = _statement(tmp_path)
    request = ExtractionRequest(
        statement=statement,
        provider=Provider.OPENAI,
        model_identifier="future-model",
        prompt_version="visual_table_extraction_v1",
        schema_version="visual_table_extraction.v1",
    )

    with pytest.raises(ValueError, match="successful results require"):
        ExtractionResult(
            request=request,
            request_timestamp=datetime.now(UTC),
            status=ExtractionStatus.SUCCESS,
            retry_count=0,
            raw_provider_response=None,
            parsed_response=_annotation(tmp_path),
        )


def test_statement_annotation_rejects_cells_on_section_headings(
    tmp_path: Path,
) -> None:
    annotation = _annotation(tmp_path)
    section_row = RowAnnotation(
        statement_id=annotation.statement.statement_id,
        row_index=0,
        row_path_raw=("Net sales",),
        row_kind=RowKind.SECTION_HEADING,
    )

    with pytest.raises(ValueError, match="section-heading rows"):
        StatementAnnotation(
            statement=annotation.statement,
            rows=(section_row,),
            columns=annotation.columns,
            cells=annotation.cells,
        )


def test_failure_result_retains_structured_error(tmp_path: Path) -> None:
    statement = _statement(tmp_path)
    request = ExtractionRequest(
        statement=statement,
        provider=Provider.QWEN,
        model_identifier="future-model",
        prompt_version="visual_table_extraction_v1",
        schema_version="visual_table_extraction.v1",
    )
    result = ExtractionResult(
        request=request,
        request_timestamp=datetime.now(UTC),
        status=ExtractionStatus.FAILURE,
        retry_count=2,
        raw_provider_response={"provider_error": "retained verbatim"},
        parsed_response=None,
        error_details={"type": "timeout", "message": "request timed out"},
    )

    assert result.retry_count == 2
    assert result.raw_provider_response == {"provider_error": "retained verbatim"}
