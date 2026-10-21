"""Lossless table/label conversion and validation, independent of Streamlit."""

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .errors import ReviewError
from .validation import METRICS, validate_labels

METRIC_NAMES = {
    "reported_diluted_eps": "Reported diluted EPS",
    "adjusted_diluted_eps": "Adjusted diluted EPS",
}
FIELDS = {
    "Value": "value", "Currency": "currency", "Period": "period",
    "Start": "period_start", "End": "period_end",
}
COLUMNS = ("EPS type", *FIELDS)


def labels_to_rows(labels: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Create independent display rows, retaining exact strings and null starts."""
    return [
        {"EPS type": METRIC_NAMES[metric],
         **{column: item[field] for column, field in FIELDS.items()}}
        for metric in METRICS for item in labels[metric]
    ]


def _blank(value: Any) -> bool:
    return value is None or isinstance(value, str) and not value.strip()


@dataclass(frozen=True)
class EditorResult:
    # No usable payload is exposed when any row is invalid.
    labels: dict[str, list[dict[str, Any]]] | None
    errors: tuple[str, ...]
    missing_starts: tuple[int, ...]


def validate_rows(rows: Sequence[Mapping[str, Any]]) -> EditorResult:
    """Validate every used row, reporting its one-based table position.

    Wholly blank rows are unused. Only blank starts become null; other values
    are not coerced, stripped, rounded, uppercased or inferred from period text.
    The same label validator as the loader owns schema/date/duplicate rules.
    """
    labels = {metric: [] for metric in METRICS}
    errors = []
    missing_starts = []
    metric_keys = {name: metric for metric, name in METRIC_NAMES.items()}
    for number, row in enumerate(rows, 1):
        if all(_blank(row.get(column)) for column in COLUMNS):
            continue
        if _blank(row.get("Start")):
            missing_starts.append(number)
        kind = row.get("EPS type")
        metric = metric_keys.get(kind) if isinstance(kind, str) else None
        if metric is None:
            errors.append(f"Row {number}: EPS type must be Reported diluted EPS or Adjusted diluted EPS.")
        observation = {field: row.get(column) for column, field in FIELDS.items()}
        if _blank(observation["period_start"]):
            observation["period_start"] = None
        # Check row fields even when its type is missing, so partial additions
        # show all useful corrections. Check duplicates against preceding valid
        # rows in the same metric; currencies and quarter/YTD remain distinct.
        target = metric or METRICS[0]
        candidate = deepcopy(labels)
        candidate[target].append(observation)
        try:
            validate_labels(candidate, location=f"Row {number}")
        except ReviewError as error:
            errors.append(str(error))
        else:
            if metric is not None:
                labels[metric].append(observation)
    return EditorResult(None if errors else labels, tuple(errors), tuple(missing_starts))


def rows_to_labels(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Return only valid extraction targets; never include table-only fields."""
    result = validate_rows(rows)
    if result.errors:
        raise ReviewError("\n".join(result.errors))
    assert result.labels is not None
    return result.labels
