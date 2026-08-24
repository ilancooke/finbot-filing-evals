"""Visual financial-statement golden-dataset contracts and utilities."""

from .config import GoldenDatasetConfig
from .models import (
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
from .prompts import load_prompt, prompt_sha256
from .schemas import load_visual_table_schema, schema_sha256
from .versions import (
    ANNOTATION_ENVELOPE_SCHEMA_VERSION,
    VISUAL_TABLE_EXTRACTION_PROMPT_VERSION,
    VISUAL_TABLE_EXTRACTION_SCHEMA_VERSION,
)
from .validation import parse_visual_table_response, validate_visual_table_response

__all__ = [
    "ANNOTATION_ENVELOPE_SCHEMA_VERSION",
    "CellAnnotation",
    "ColumnAnnotation",
    "ExtractionRequest",
    "ExtractionResult",
    "ExtractionStatus",
    "FilingType",
    "GoldenDatasetConfig",
    "Provider",
    "RowAnnotation",
    "RowKind",
    "SourceImage",
    "StatementAnnotation",
    "StatementMetadata",
    "StatementType",
    "VISUAL_TABLE_EXTRACTION_PROMPT_VERSION",
    "VISUAL_TABLE_EXTRACTION_SCHEMA_VERSION",
    "load_prompt",
    "load_visual_table_schema",
    "parse_visual_table_response",
    "prompt_sha256",
    "schema_sha256",
    "validate_visual_table_response",
]
