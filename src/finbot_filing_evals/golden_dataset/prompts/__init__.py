"""Integrity-checked access to immutable, versioned prompt resources."""

from __future__ import annotations

from .._resources import load_versioned_resource
from ..versions import (
    VISUAL_TABLE_EXTRACTION_PROMPT_SHA256,
    VISUAL_TABLE_EXTRACTION_PROMPT_VERSION,
)


_PROMPTS = {
    VISUAL_TABLE_EXTRACTION_PROMPT_VERSION: (
        "visual_table_extraction_v1.txt",
        VISUAL_TABLE_EXTRACTION_PROMPT_SHA256,
    )
}


def load_prompt(version: str = VISUAL_TABLE_EXTRACTION_PROMPT_VERSION) -> str:
    """Load a prompt only if its bytes match the frozen version digest."""

    return load_versioned_resource(
        package=__package__, version=version, registry=_PROMPTS
    ).decode("utf-8")


def prompt_sha256(version: str = VISUAL_TABLE_EXTRACTION_PROMPT_VERSION) -> str:
    """Return the verified SHA-256 digest for a packaged prompt."""

    load_prompt(version)
    return _PROMPTS[version][1]


__all__ = ["load_prompt", "prompt_sha256"]
