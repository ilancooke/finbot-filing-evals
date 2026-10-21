"""Explicit CLI/environment configuration; no dotenv loading or directory creation."""

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import os
from pathlib import Path

from .errors import ReviewError

DEFAULT_DATASET_SUBPATH = Path("filing-evals/golden/earnings-eps-v1")
DEFAULT_CATALOG_REPO = Path(__file__).resolve().parents[4] / "finbot-catalog"


@dataclass(frozen=True)
class ReviewConfig:
    dataset_root: Path
    data_root: Path | None
    catalog_repo: Path

    @property
    def catalog_enabled(self) -> bool:
        return self.data_root is not None and self.dataset_root == (
            self.data_root / DEFAULT_DATASET_SUBPATH
        ).resolve()


def resolve_dataset_root(
    explicit: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """An explicit dataset overrides FINBOT_DATA_ROOT; missing config is an error."""
    if explicit is not None:
        if not str(explicit).strip():
            raise ReviewError("--dataset-root must name a dataset directory.")
        candidate = Path(explicit)
    else:
        env = os.environ if environ is None else environ
        data_root = env.get("FINBOT_DATA_ROOT", "")
        if not data_root.strip():
            raise ReviewError(
                "Set FINBOT_DATA_ROOT or pass --dataset-root pointing to the EPS dataset."
            )
        candidate = Path(data_root) / DEFAULT_DATASET_SUBPATH
    try:
        return candidate.expanduser().resolve()
    except (OSError, RuntimeError) as error:
        raise ReviewError(f"Cannot resolve dataset directory: {candidate}") from error


def parse_dataset_root(argv: Sequence[str] | None = None) -> Path:
    return parse_config(argv).dataset_root


def parse_config(argv: Sequence[str] | None = None) -> ReviewConfig:
    parser = argparse.ArgumentParser(description="Review and confirm a local EPS dataset.")
    parser.add_argument("--dataset-root", type=Path, help="Override the shared dataset path")
    parser.add_argument("--catalog-repo", type=Path, default=DEFAULT_CATALOG_REPO,
                        help="Catalog repository (defaults to sibling finbot-catalog)")
    args = parser.parse_args(argv)
    root = resolve_dataset_root(args.dataset_root)
    try:
        shared = os.environ.get("FINBOT_DATA_ROOT", "").strip()
        return ReviewConfig(root, Path(shared).expanduser().resolve() if shared else None,
                            args.catalog_repo.expanduser().resolve())
    except (OSError, RuntimeError) as error:
        raise ReviewError("Cannot resolve FINBOT_DATA_ROOT or --catalog-repo.") from error
