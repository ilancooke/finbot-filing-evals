from copy import deepcopy

import pytest

from finbot_filing_evals.review import ReviewError
from finbot_filing_evals.review.validation import load_label_schema, validate_labels


def test_preserves_precision_negative_values_currencies_and_cumulative_periods(labels):
    original = deepcopy(labels)
    labels["adjusted_diluted_eps"].append(dict(value="-0.50", currency="USD", period="Q3", period_start="2026-07-01", period_end="2026-09-30"))
    validate_labels(labels)
    assert labels["reported_diluted_eps"] == original["reported_diluted_eps"]
    assert labels["reported_diluted_eps"][0]["value"] == "4.60"
    assert labels["reported_diluted_eps"][0]["period_start"] is None


def test_empty_arrays_are_valid():
    validate_labels(dict(reported_diluted_eps=[], adjusted_diluted_eps=[]))


@pytest.mark.parametrize(("field", "value"), [
    ("value", 4.60), ("value", "NaN"), ("value", "1e3"), ("value", "4"),
    ("currency", "usd"), ("currency", "US"), ("period", "   "),
    ("period_end", None), ("period_end", "2026-02-30"), ("period_end", "20260930"),
    ("period_start", "2026-10-01"), ("period_start", "2026-02-29"),
])
def test_bad_observations_have_field_context(labels, field, value):
    labels["reported_diluted_eps"][0][field] = value
    with pytest.raises(ReviewError, match=field):
        validate_labels(labels, location="case.labels")


def test_extra_target_fields_are_rejected(labels):
    labels["reported_diluted_eps"][0]["evidence"] = "Not in the agreed targets"
    with pytest.raises(ReviewError, match="Additional properties"):
        validate_labels(labels)


def test_known_interval_duplicates_cannot_hide_behind_another_period_label(labels):
    row = deepcopy(labels["reported_diluted_eps"][1])
    row["period"] = "YTD"
    labels["reported_diluted_eps"].append(row)
    with pytest.raises(ReviewError, match="duplicate"):
        validate_labels(labels)


def test_unknown_start_duplicates_use_normalized_period_label(labels):
    row = deepcopy(labels["reported_diluted_eps"][0])
    row["period"] = " q3   2026 "
    labels["reported_diluted_eps"].append(row)
    with pytest.raises(ReviewError, match="duplicate"):
        validate_labels(labels)


def test_schema_returns_independent_copies():
    first = load_label_schema()
    first["properties"].clear()
    assert len(load_label_schema()["properties"]) == 2
