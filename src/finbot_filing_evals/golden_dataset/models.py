"""Core, provider-neutral contracts for raw visual table annotations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
import re
from typing import Any


_TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]*$")


class FilingType(str, Enum):
    FORM_10_K = "10-K"
    FORM_10_Q = "10-Q"

    @property
    def id_token(self) -> str:
        return self.value.replace("-", "")


class StatementType(str, Enum):
    BALANCE_SHEET = "balance_sheet"
    INCOME_STATEMENT = "income_statement"
    CASH_FLOWS = "cash_flows"


class Provider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    QWEN = "qwen"


class ExtractionStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"


class RowKind(str, Enum):
    DATA = "data"
    SECTION_HEADING = "section_heading"


@dataclass(frozen=True, slots=True)
class SourceImage:
    """Immutable identity and location of one source screenshot."""

    source_file: Path
    source_image_id: str
    sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_file, Path):
            raise TypeError("source_file must be a pathlib.Path")
        if not self.source_file.is_absolute():
            raise ValueError("source_file must be an absolute path")
        if len(self.sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sha256
        ):
            raise ValueError("sha256 must be a lowercase 64-character hex digest")
        if self.source_image_id != f"sha256:{self.sha256}":
            raise ValueError("source_image_id must be 'sha256:<sha256>'")


@dataclass(frozen=True, slots=True)
class StatementMetadata:
    """Path-derived identity plus raw statement-level text when extracted."""

    statement_id: str
    ticker: str
    filing_type: FilingType
    statement_type: StatementType
    source_image: SourceImage
    statement_title_raw: str | None = None
    units_raw: str | None = None
    visual_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if _TICKER_PATTERN.fullmatch(self.ticker) is None:
            raise ValueError("ticker must follow the uppercase ticker convention")
        if not isinstance(self.filing_type, FilingType):
            raise TypeError("filing_type must be a FilingType")
        if not isinstance(self.statement_type, StatementType):
            raise TypeError("statement_type must be a StatementType")
        expected_id = (
            f"{self.ticker}_{self.filing_type.id_token}_{self.statement_type.value}"
        )
        if self.statement_id != expected_id:
            raise ValueError(f"statement_id must be {expected_id!r}")
        for name in ("statement_title_raw", "units_raw"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, str):
                raise TypeError(f"{name} must be a string or None")
            if isinstance(value, str) and not value.strip():
                raise ValueError(f"{name} must contain visible text or be None")


@dataclass(frozen=True, slots=True)
class RowAnnotation:
    """One meaningful table row in visual order."""

    statement_id: str
    row_index: int
    row_path_raw: tuple[str, ...]
    row_kind: RowKind

    def __post_init__(self) -> None:
        if self.row_index < 0:
            raise ValueError("row_index must be non-negative")
        _validate_raw_path("row_path_raw", self.row_path_raw)
        if not isinstance(self.row_kind, RowKind):
            raise TypeError("row_kind must be a RowKind")


@dataclass(frozen=True, slots=True)
class ColumnAnnotation:
    """One value column in visual order."""

    statement_id: str
    column_index: int
    column_path_raw: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.column_index < 0:
            raise ValueError("column_index must be non-negative")
        _validate_raw_path("column_path_raw", self.column_path_raw)


@dataclass(frozen=True, slots=True)
class CellAnnotation:
    """One visibly reported value cell; raw strings are never normalized here."""

    statement_id: str
    row_index: int
    row_path_raw: tuple[str, ...]
    column_index: int
    column_path_raw: tuple[str, ...]
    value_raw: str
    visual_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.row_index < 0 or self.column_index < 0:
            raise ValueError("row_index and column_index must be non-negative")
        _validate_raw_path("row_path_raw", self.row_path_raw)
        _validate_raw_path("column_path_raw", self.column_path_raw)
        if not isinstance(self.value_raw, str):
            raise TypeError("value_raw must be a string, including for blank cells")


@dataclass(frozen=True, slots=True)
class StatementAnnotation:
    """One provider's parsed transcription of a complete statement."""

    statement: StatementMetadata
    rows: tuple[RowAnnotation, ...]
    columns: tuple[ColumnAnnotation, ...]
    cells: tuple[CellAnnotation, ...]

    def __post_init__(self) -> None:
        for name in ("rows", "columns", "cells"):
            if not isinstance(getattr(self, name), tuple):
                raise TypeError(f"{name} must be a tuple")
        if not self.rows or not self.columns or not self.cells:
            raise ValueError("statement annotations require rows, columns, and cells")
        statement_id = self.statement.statement_id
        if any(row.statement_id != statement_id for row in self.rows):
            raise ValueError("every row must reference the enclosing statement_id")
        if any(column.statement_id != statement_id for column in self.columns):
            raise ValueError("every column must reference the enclosing statement_id")
        if any(cell.statement_id != statement_id for cell in self.cells):
            raise ValueError("every cell must reference the enclosing statement_id")
        if [row.row_index for row in self.rows] != list(range(len(self.rows))):
            raise ValueError("rows must be contiguous and ordered from zero")
        if [column.column_index for column in self.columns] != list(
            range(len(self.columns))
        ):
            raise ValueError("columns must be contiguous and ordered from zero")

        row_by_index = {row.row_index: row for row in self.rows}
        column_by_index = {column.column_index: column for column in self.columns}
        coordinates = [(cell.row_index, cell.column_index) for cell in self.cells]
        if coordinates != sorted(coordinates) or len(coordinates) != len(
            set(coordinates)
        ):
            raise ValueError("cells must have unique coordinates in row-major order")

        used_rows: set[int] = set()
        used_columns: set[int] = set()
        for cell in self.cells:
            row = row_by_index.get(cell.row_index)
            column = column_by_index.get(cell.column_index)
            if row is None or column is None:
                raise ValueError("every cell must reference an existing row and column")
            if row.row_kind is not RowKind.DATA:
                raise ValueError("section-heading rows cannot contain cells")
            if cell.row_path_raw != row.row_path_raw:
                raise ValueError("cell row_path_raw must match its row")
            if cell.column_path_raw != column.column_path_raw:
                raise ValueError("cell column_path_raw must match its column")
            used_rows.add(cell.row_index)
            used_columns.add(cell.column_index)

        data_rows = {
            row.row_index for row in self.rows if row.row_kind is RowKind.DATA
        }
        if data_rows != used_rows:
            raise ValueError("every data row must contain at least one cell")
        if set(column_by_index) != used_columns:
            raise ValueError("every column must contain at least one cell")


@dataclass(frozen=True, slots=True)
class ExtractionRequest:
    """Provider-neutral input for one independent image request."""

    statement: StatementMetadata
    provider: Provider
    model_identifier: str
    prompt_version: str
    schema_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.provider, Provider):
            raise TypeError("provider must be a Provider")
        for name in ("model_identifier", "prompt_version", "schema_version"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be blank")


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Auditable envelope retaining provider-native and parsed responses."""

    request: ExtractionRequest
    request_timestamp: datetime
    status: ExtractionStatus
    retry_count: int
    raw_provider_response: Any | None
    parsed_response: StatementAnnotation | None
    model_version: str | None = None
    usage_metadata: Mapping[str, Any] = field(default_factory=dict)
    error_details: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ExtractionStatus):
            raise TypeError("status must be an ExtractionStatus")
        if self.request_timestamp.utcoffset() is None:
            raise ValueError("request_timestamp must be timezone-aware")
        if self.retry_count < 0:
            raise ValueError("retry_count must be non-negative")
        if self.status is ExtractionStatus.SUCCESS:
            if self.parsed_response is None or self.raw_provider_response is None:
                raise ValueError(
                    "successful results require raw_provider_response and parsed_response"
                )
            if (
                self.parsed_response.statement.statement_id
                != self.request.statement.statement_id
            ):
                raise ValueError("parsed response does not match request statement_id")
            if (
                self.parsed_response.statement.source_image
                != self.request.statement.source_image
            ):
                raise ValueError("parsed response does not match request source image")
        elif not self.error_details:
            raise ValueError("failed results require error_details")


def _validate_raw_path(name: str, value: tuple[str, ...]) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be a tuple")
    if not value:
        raise ValueError(f"{name} must contain at least one visible label")
    if any(not isinstance(part, str) for part in value):
        raise TypeError(f"every {name} component must be a string")
    if any(not part.strip() for part in value):
        raise ValueError(f"every {name} component must contain visible text")
