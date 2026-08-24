from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from finbot_filing_evals.golden_dataset.discovery import (
    DiscoveryError,
    discover_screenshots,
)
from finbot_filing_evals.golden_dataset.models import FilingType, StatementType


EXPECTED_FILES = (
    "10k balance sheet.png",
    "10k cash flows.png",
    "10k income statement.png",
    "10q balance sheet.png",
    "10q cash flows.png",
    "10q income statement.png",
)


def _write_ticker(root: Path, ticker: str) -> None:
    ticker_root = root / ticker
    ticker_root.mkdir(parents=True)
    for filename in reversed(EXPECTED_FILES):
        path = ticker_root / filename
        path.write_bytes(f"{ticker}/{filename}".encode())


def test_discovery_is_sorted_and_derives_metadata_without_llm(tmp_path: Path) -> None:
    _write_ticker(tmp_path, "MSFT")
    _write_ticker(tmp_path, "AAPL")
    (tmp_path / ".DS_Store").write_bytes(b"ignored")
    (tmp_path / "AAPL" / ".DS_Store").write_bytes(b"ignored")

    records = discover_screenshots(
        tmp_path,
        expected_count=12,
        require_complete_ticker_sets=True,
    )

    assert len(records) == 12
    assert [record.ticker for record in records[:6]] == ["AAPL"] * 6
    income = next(
        record
        for record in records
        if record.ticker == "AAPL"
        and record.filing_type is FilingType.FORM_10_Q
        and record.statement_type is StatementType.INCOME_STATEMENT
    )
    assert income.statement_id == "AAPL_10Q_income_statement"
    assert income.statement_title_raw is None
    assert income.units_raw is None
    assert income.source_image.source_file == (
        tmp_path / "AAPL" / "10q income statement.png"
    ).resolve()
    expected_digest = hashlib.sha256(
        b"AAPL/10q income statement.png"
    ).hexdigest()
    assert income.source_image.sha256 == expected_digest
    assert income.source_image.source_image_id == f"sha256:{expected_digest}"


def test_discovery_rejects_misnamed_png(tmp_path: Path) -> None:
    ticker_root = tmp_path / "AAPL"
    ticker_root.mkdir()
    (ticker_root / "10-Q income statement.png").write_bytes(b"image")

    with pytest.raises(DiscoveryError, match="invalid screenshot filename"):
        discover_screenshots(tmp_path)


def test_discovery_rejects_invalid_ticker_directory(tmp_path: Path) -> None:
    _write_ticker(tmp_path, "aapl")

    with pytest.raises(DiscoveryError, match="invalid ticker directory"):
        discover_screenshots(tmp_path)


def test_discovery_reports_incomplete_ticker_set(tmp_path: Path) -> None:
    ticker_root = tmp_path / "AAPL"
    ticker_root.mkdir()
    (ticker_root / "10q income statement.png").write_bytes(b"image")

    with pytest.raises(DiscoveryError, match="incomplete ticker screenshot sets"):
        discover_screenshots(tmp_path, require_complete_ticker_sets=True)


def test_discovery_checks_expected_count(tmp_path: Path) -> None:
    _write_ticker(tmp_path, "AAPL")

    with pytest.raises(DiscoveryError, match="expected 90 screenshots"):
        discover_screenshots(tmp_path, expected_count=90)

