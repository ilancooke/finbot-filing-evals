"""Acceptance check for the real corpus; skipped in isolated environments."""

from pathlib import Path
import os

import pytest

from finbot_filing_evals.golden_dataset.config import GoldenDatasetConfig
from finbot_filing_evals.golden_dataset.discovery import discover_screenshots


CONVENTIONAL_DATA_ROOT = Path("/Users/ilan/workspace/finbot/data")


def _source_root() -> Path:
    data_root = os.environ.get("FINBOT_DATA_ROOT")
    root = Path(data_root) if data_root else CONVENTIONAL_DATA_ROOT
    return GoldenDatasetConfig.from_data_root(root).source_root


def test_real_source_corpus_has_90_deterministic_screenshots() -> None:
    source_root = _source_root()
    if not source_root.is_dir():
        pytest.skip(f"source corpus is not present at {source_root}")

    first = discover_screenshots(
        source_root,
        expected_count=90,
        require_complete_ticker_sets=True,
    )
    second = discover_screenshots(
        source_root,
        expected_count=90,
        require_complete_ticker_sets=True,
    )

    assert len({record.ticker for record in first}) == 15
    assert first == second
    assert len({record.statement_id for record in first}) == 90

