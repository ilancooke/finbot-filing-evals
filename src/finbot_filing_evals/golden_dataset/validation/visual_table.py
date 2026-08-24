"""Validation and conversion for the frozen visual-table extraction contract."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from jsonschema import Draft202012Validator

from ..models import (
    CellAnnotation,
    ColumnAnnotation,
    RowAnnotation,
    RowKind,
    StatementAnnotation,
    StatementMetadata,
)
from ..schemas import load_visual_table_schema
from ..versions import VISUAL_TABLE_EXTRACTION_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One stable, path-addressed response validation problem."""

    path: str
    message: str


class VisualTableValidationError(ValueError):
    """A response failed structural or cross-record V1 validation."""

    def __init__(self, issues: Sequence[ValidationIssue]) -> None:
        self.issues = tuple(issues)
        details = "; ".join(f"{issue.path}: {issue.message}" for issue in self.issues)
        super().__init__(f"visual table response is invalid: {details}")


def validate_visual_table_response(
    payload: Mapping[str, Any],
    *,
    schema_version: str = VISUAL_TABLE_EXTRACTION_SCHEMA_VERSION,
) -> None:
    """Validate V1 JSON shape, ordering, references, and raw path content."""

    schema = load_visual_table_schema(schema_version)
    validator = Draft202012Validator(schema)
    schema_issues = [
        ValidationIssue(_json_path(error.absolute_path), error.message)
        for error in sorted(
            validator.iter_errors(payload),
            key=lambda error: (_json_path(error.absolute_path), error.message),
        )
    ]
    if schema_issues:
        raise VisualTableValidationError(schema_issues)

    issues = _semantic_issues(payload)
    if issues:
        raise VisualTableValidationError(issues)


def parse_visual_table_response(
    payload: Mapping[str, Any],
    source_statement: StatementMetadata,
    *,
    schema_version: str = VISUAL_TABLE_EXTRACTION_SCHEMA_VERSION,
) -> StatementAnnotation:
    """Validate provider output and attach deterministic source metadata."""

    validate_visual_table_response(payload, schema_version=schema_version)
    statement_id = source_statement.statement_id
    rows = tuple(
        RowAnnotation(
            statement_id=statement_id,
            row_index=row["row_index"],
            row_path_raw=tuple(row["row_path_raw"]),
            row_kind=RowKind(row["row_kind"]),
        )
        for row in payload["rows"]
    )
    columns = tuple(
        ColumnAnnotation(
            statement_id=statement_id,
            column_index=column["column_index"],
            column_path_raw=tuple(column["column_path_raw"]),
        )
        for column in payload["columns"]
    )
    row_by_index = {row.row_index: row for row in rows}
    column_by_index = {column.column_index: column for column in columns}
    cells = tuple(
        CellAnnotation(
            statement_id=statement_id,
            row_index=cell["row_index"],
            row_path_raw=row_by_index[cell["row_index"]].row_path_raw,
            column_index=cell["column_index"],
            column_path_raw=column_by_index[cell["column_index"]].column_path_raw,
            value_raw=cell["value_raw"],
        )
        for cell in payload["cells"]
    )
    statement = replace(
        source_statement,
        statement_title_raw=payload["statement_title_raw"],
        units_raw=payload["units_raw"],
    )
    return StatementAnnotation(
        statement=statement,
        rows=rows,
        columns=columns,
        cells=cells,
    )


def _semantic_issues(payload: Mapping[str, Any]) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []
    rows = payload["rows"]
    columns = payload["columns"]
    cells = payload["cells"]

    for name in ("statement_title_raw", "units_raw"):
        value = payload[name]
        if isinstance(value, str) and not value.strip():
            issues.append(
                ValidationIssue(f"$.{name}", "must contain visible text or be null")
            )

    for position, row in enumerate(rows):
        if row["row_index"] != position:
            issues.append(
                ValidationIssue(
                    f"$.rows[{position}].row_index",
                    f"must be {position} to remain contiguous and zero-based",
                )
            )
        issues.extend(_raw_path_issues(row["row_path_raw"], f"$.rows[{position}].row_path_raw"))

    for position, column in enumerate(columns):
        if column["column_index"] != position:
            issues.append(
                ValidationIssue(
                    f"$.columns[{position}].column_index",
                    f"must be {position} to remain contiguous and zero-based",
                )
            )
        issues.extend(
            _raw_path_issues(
                column["column_path_raw"],
                f"$.columns[{position}].column_path_raw",
            )
        )

    coordinates = [(cell["row_index"], cell["column_index"]) for cell in cells]
    if coordinates != sorted(coordinates):
        issues.append(
            ValidationIssue("$.cells", "must be ordered by row_index, then column_index")
        )
    duplicate_coordinates = {
        coordinate for coordinate, count in Counter(coordinates).items() if count > 1
    }
    if duplicate_coordinates:
        formatted = ", ".join(str(coordinate) for coordinate in sorted(duplicate_coordinates))
        issues.append(ValidationIssue("$.cells", f"contains duplicate coordinates: {formatted}"))

    used_rows: set[int] = set()
    used_columns: set[int] = set()
    for position, cell in enumerate(cells):
        row_index = cell["row_index"]
        column_index = cell["column_index"]
        if row_index >= len(rows):
            issues.append(
                ValidationIssue(
                    f"$.cells[{position}].row_index", "does not reference an existing row"
                )
            )
        else:
            used_rows.add(row_index)
            if rows[row_index]["row_kind"] == RowKind.SECTION_HEADING.value:
                issues.append(
                    ValidationIssue(
                        f"$.cells[{position}].row_index",
                        "cannot reference a section-heading row",
                    )
                )
        if column_index >= len(columns):
            issues.append(
                ValidationIssue(
                    f"$.cells[{position}].column_index",
                    "does not reference an existing column",
                )
            )
        else:
            used_columns.add(column_index)

    for position, row in enumerate(rows):
        if row["row_kind"] == RowKind.DATA.value and position not in used_rows:
            issues.append(
                ValidationIssue(
                    f"$.rows[{position}]", "data rows must contain at least one cell"
                )
            )
    for position, _column in enumerate(columns):
        if position not in used_columns:
            issues.append(
                ValidationIssue(
                    f"$.columns[{position}]", "columns must contain at least one cell"
                )
            )
    return tuple(issues)


def _raw_path_issues(path: Sequence[str], base_path: str) -> list[ValidationIssue]:
    return [
        ValidationIssue(
            f"{base_path}[{position}]", "must contain visible text"
        )
        for position, component in enumerate(path)
        if not component.strip()
    ]


def _json_path(parts: Sequence[str | int]) -> str:
    path = "$"
    for part in parts:
        path += f"[{part}]" if isinstance(part, int) else f".{part}"
    return path
