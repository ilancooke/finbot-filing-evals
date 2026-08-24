"""Deterministic discovery of statement screenshots and path metadata."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re

from .models import FilingType, SourceImage, StatementMetadata, StatementType


_TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]*$")
_FILE_PATTERN = re.compile(
    r"^(?P<filing>10k|10q) "
    r"(?P<statement>balance sheet|income statement|cash flows)\.png$"
)
_FILING_TYPES = {"10k": FilingType.FORM_10_K, "10q": FilingType.FORM_10_Q}
_STATEMENT_TYPES = {
    "balance sheet": StatementType.BALANCE_SHEET,
    "income statement": StatementType.INCOME_STATEMENT,
    "cash flows": StatementType.CASH_FLOWS,
}
EXPECTED_IDENTITIES_PER_TICKER = frozenset(
    (filing_type, statement_type)
    for filing_type in FilingType
    for statement_type in StatementType
)


class DiscoveryError(ValueError):
    """The screenshot tree does not satisfy its deterministic contract."""


def discover_screenshots(
    source_root: str | Path,
    *,
    expected_count: int | None = None,
    require_complete_ticker_sets: bool = False,
) -> tuple[StatementMetadata, ...]:
    """Discover screenshots in stable identity order and hash their contents.

    Only direct ``{ticker}/{expected filename}`` PNGs are accepted. Hidden files
    are ignored so Finder metadata does not affect a manifest.
    """

    root = Path(source_root).expanduser().resolve()
    if not root.is_dir():
        raise DiscoveryError(f"source screenshot directory does not exist: {root}")

    records: list[StatementMetadata] = []
    seen_ids: set[str] = set()
    ticker_identities: dict[str, set[tuple[FilingType, StatementType]]] = {}

    for ticker_dir in sorted(root.iterdir(), key=lambda path: path.name):
        if ticker_dir.name.startswith("."):
            continue
        if not ticker_dir.is_dir():
            raise DiscoveryError(f"unexpected file at source root: {ticker_dir}")
        ticker = ticker_dir.name
        if not _TICKER_PATTERN.fullmatch(ticker):
            raise DiscoveryError(f"invalid ticker directory name: {ticker!r}")

        identities = ticker_identities.setdefault(ticker, set())
        for source_file in sorted(ticker_dir.iterdir(), key=lambda path: path.name):
            if source_file.name.startswith("."):
                continue
            if not source_file.is_file():
                raise DiscoveryError(f"unexpected nested directory: {source_file}")
            match = _FILE_PATTERN.fullmatch(source_file.name)
            if match is None:
                raise DiscoveryError(f"invalid screenshot filename: {source_file}")

            filing_type = _FILING_TYPES[match.group("filing")]
            statement_type = _STATEMENT_TYPES[match.group("statement")]
            identity = (filing_type, statement_type)
            if identity in identities:
                raise DiscoveryError(
                    f"duplicate {filing_type.value} {statement_type.value} for {ticker}"
                )
            identities.add(identity)

            statement_id = f"{ticker}_{filing_type.id_token}_{statement_type.value}"
            if statement_id in seen_ids:
                raise DiscoveryError(f"duplicate statement_id: {statement_id}")
            seen_ids.add(statement_id)

            digest = sha256_file(source_file)
            records.append(
                StatementMetadata(
                    statement_id=statement_id,
                    ticker=ticker,
                    filing_type=filing_type,
                    statement_type=statement_type,
                    source_image=SourceImage(
                        source_file=source_file.resolve(),
                        source_image_id=f"sha256:{digest}",
                        sha256=digest,
                    ),
                )
            )

    records.sort(
        key=lambda item: (
            item.ticker,
            item.filing_type.value,
            item.statement_type.value,
        )
    )
    _validate_discovery(
        records,
        ticker_identities,
        expected_count=expected_count,
        require_complete_ticker_sets=require_complete_ticker_sets,
    )
    return tuple(records)


def sha256_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Return the lowercase SHA-256 digest without loading the image at once."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_discovery(
    records: list[StatementMetadata],
    ticker_identities: dict[str, set[tuple[FilingType, StatementType]]],
    *,
    expected_count: int | None,
    require_complete_ticker_sets: bool,
) -> None:
    if expected_count is not None and len(records) != expected_count:
        raise DiscoveryError(
            f"expected {expected_count} screenshots but discovered {len(records)}"
        )
    if require_complete_ticker_sets:
        incomplete = {
            ticker: sorted(
                f"{filing.value}/{statement.value}"
                for filing, statement in EXPECTED_IDENTITIES_PER_TICKER - identities
            )
            for ticker, identities in ticker_identities.items()
            if identities != EXPECTED_IDENTITIES_PER_TICKER
        }
        if incomplete:
            details = "; ".join(
                f"{ticker} missing {', '.join(missing)}"
                for ticker, missing in sorted(incomplete.items())
            )
            raise DiscoveryError(f"incomplete ticker screenshot sets: {details}")

