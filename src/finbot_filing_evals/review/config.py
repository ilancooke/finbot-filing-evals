"""Explicit CLI/environment configuration; no dotenv loading or directory creation."""

import argparse
from collections.abc import Mapping, Sequence
import os
from pathlib import Path

from .errors import ReviewError

DEFAULT_DATASET_SUBPATH = Path("filing-evals/golden/earnings-eps-v1")


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
    parser = argparse.ArgumentParser(description="Inspect a local EPS dataset (read-only).")
    parser.add_argument("--dataset-root", type=Path, help="Override the shared dataset path")
    return resolve_dataset_root(parser.parse_args(argv).dataset_root)
