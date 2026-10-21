"""The supported document label schema and deterministic semantic validation."""

from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from functools import lru_cache
from importlib.resources import files
import json
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .errors import ReviewError

SCHEMA_VERSION = "earnings_eps.v1"
METRICS = ("reported_diluted_eps", "adjusted_diluted_eps")


def load_label_schema() -> dict[str, Any]:
    """Return a fresh copy of the packaged contract, independent of dataset input."""
    resource = files("finbot_filing_evals.review").joinpath("schemas/earnings_eps_v1.schema.json")
    return json.loads(resource.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema = load_label_schema()
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_labels(labels: Any, *, location: str = "labels") -> None:
    """Validate shape, actual dates, nonblank periods and duplicate intervals."""
    error = next(_validator().iter_errors(labels), None)
    if error is not None:
        suffix = ".".join(str(part) for part in error.absolute_path)
        field = f"{location}.{suffix}" if suffix else location
        raise ReviewError(f"{field}: {error.message}")
    for metric in METRICS:
        seen = set()
        for index, row in enumerate(labels[metric]):
            field = f"{location}.{metric}[{index}]"
            if not row["period"].strip():
                raise ReviewError(f"{field}.period must not be blank.")
            if not Decimal(row["value"]).is_finite():
                raise ReviewError(f"{field}.value must be a finite decimal string.")
            start = row["period_start"]
            end = row["period_end"]
            if start is not None and date.fromisoformat(start) > date.fromisoformat(end):
                raise ReviewError(f"{field}: period_start must not follow period_end.")
            interval = (start, end) if start is not None else (
                None, end, " ".join(row["period"].split()).casefold()
            )
            key = (row["currency"], interval)
            if key in seen:
                raise ReviewError(f"{field}: duplicate {metric} observation for this currency/period.")
            seen.add(key)


def require_object(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReviewError(f"{location} must be a JSON object.")
    return value


def require_text(record: Mapping[str, Any], key: str, location: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ReviewError(f"{location}.{key} must be a nonblank string.")
    return value
