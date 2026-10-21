"""Local, read-only foundations for reviewing document EPS labels."""

from .config import resolve_dataset_root
from .dataset import ReviewCase, ReviewDataset, SourceDocument, load_dataset
from .errors import ReviewError

__all__ = [
    "ReviewCase",
    "ReviewDataset",
    "ReviewError",
    "SourceDocument",
    "load_dataset",
    "resolve_dataset_root",
]
