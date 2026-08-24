"""Integrity-checked JSON Schemas for model-facing extraction responses."""

from __future__ import annotations

from typing import Any
import json

from jsonschema import Draft202012Validator

from .._resources import load_versioned_resource
from ..versions import (
    VISUAL_TABLE_EXTRACTION_SCHEMA_SHA256,
    VISUAL_TABLE_EXTRACTION_SCHEMA_VERSION,
)


_SCHEMAS = {
    VISUAL_TABLE_EXTRACTION_SCHEMA_VERSION: (
        "visual_table_extraction_v1.schema.json",
        VISUAL_TABLE_EXTRACTION_SCHEMA_SHA256,
    )
}


def load_visual_table_schema(
    version: str = VISUAL_TABLE_EXTRACTION_SCHEMA_VERSION,
) -> dict[str, Any]:
    """Return a fresh, integrity-checked copy of a valid JSON Schema."""

    content = load_versioned_resource(
        package=__package__, version=version, registry=_SCHEMAS
    )
    schema = json.loads(content)
    Draft202012Validator.check_schema(schema)
    return schema


def schema_sha256(version: str = VISUAL_TABLE_EXTRACTION_SCHEMA_VERSION) -> str:
    """Return the verified SHA-256 digest for a packaged schema."""

    load_visual_table_schema(version)
    return _SCHEMAS[version][1]


__all__ = ["load_visual_table_schema", "schema_sha256"]
