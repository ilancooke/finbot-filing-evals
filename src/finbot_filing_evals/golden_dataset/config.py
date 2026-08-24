"""Filesystem configuration for visual golden-dataset artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path
import re


DATA_ROOT_ENV = "FINBOT_DATA_ROOT"
SOURCE_ROOT_ENV = "FINBOT_GOLDEN_DATASET_SOURCE_ROOT"
INTERMEDIATE_ROOT_ENV = "FINBOT_GOLDEN_DATASET_INTERMEDIATE_ROOT"
PROCESSED_ROOT_ENV = "FINBOT_GOLDEN_DATASET_PROCESSED_ROOT"
_PROVIDER_DIRECTORY_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


@dataclass(frozen=True, slots=True)
class GoldenDatasetConfig:
    """Resolved locations without filesystem side effects."""

    data_root: Path
    source_root: Path
    intermediate_root: Path
    annotations_root: Path
    consensus_root: Path
    processed_root: Path

    @classmethod
    def from_data_root(
        cls,
        data_root: str | Path,
        *,
        source_root: str | Path | None = None,
        intermediate_root: str | Path | None = None,
        processed_root: str | Path | None = None,
    ) -> GoldenDatasetConfig:
        data_root_path = _absolute_path(data_root)
        source = _absolute_path(source_root) if source_root else (
            data_root_path / "raw" / "financial_statement_screenshots_golden_dataset"
        )
        intermediate = _absolute_path(intermediate_root) if intermediate_root else (
            data_root_path / "intermediate"
        )
        processed = _absolute_path(processed_root) if processed_root else (
            data_root_path / "processed" / "financial_statement_visual_gold"
        )
        return cls(
            data_root=data_root_path,
            source_root=source,
            intermediate_root=intermediate,
            annotations_root=intermediate / "golden_dataset_annotations",
            consensus_root=intermediate / "golden_dataset_consensus",
            processed_root=processed,
        )

    @classmethod
    def from_env(
        cls, environ: Mapping[str, str] | None = None
    ) -> GoldenDatasetConfig:
        """Resolve configuration from environment variables.

        API keys are intentionally outside this shared path configuration and
        will be read only by their future provider adapters.
        """

        values = os.environ if environ is None else environ
        data_root = values.get(DATA_ROOT_ENV)
        if not data_root:
            raise ValueError(
                f"{DATA_ROOT_ENV} is required; see .env.example for configuration"
            )
        return cls.from_data_root(
            data_root,
            source_root=values.get(SOURCE_ROOT_ENV),
            intermediate_root=values.get(INTERMEDIATE_ROOT_ENV),
            processed_root=values.get(PROCESSED_ROOT_ENV),
        )

    def provider_annotations_root(self, provider: str) -> Path:
        """Return (but do not create) one provider's immutable artifact root."""

        provider_name = provider.strip().lower()
        if _PROVIDER_DIRECTORY_PATTERN.fullmatch(provider_name) is None:
            raise ValueError(f"invalid provider directory name: {provider!r}")
        return self.annotations_root / provider_name


def _absolute_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()
