from copy import deepcopy

import pytest

from finbot_filing_evals.review.editor import (
    COLUMNS, METRIC_NAMES, labels_to_rows, rows_to_labels, validate_rows,
)
from finbot_filing_evals.review.errors import ReviewError
from finbot_filing_evals.review.session import EditorDraft


def test_roundtrip_preserves_precision_signs_currencies_and_periods(labels):
    # Known quarterly and cumulative starts share an end date; foreign-currency
    # and unknown-start rows remain separate. Never round-trip through floats.
    labels["reported_diluted_eps"][0]["period_start"] = "2026-07-01"
    labels["adjusted_diluted_eps"].append(dict(
        value="-0.50", currency="USD", period="Q3 2026",
        period_start=None, period_end="2026-09-30",
    ))
    before = deepcopy(labels)
    rows = labels_to_rows(labels)
    assert rows_to_labels(rows) == before
    assert [row["Value"] for row in rows] == ["4.60", "9.00", "29.43", "-0.50"]
    assert validate_rows(rows).missing_starts == (3, 4)
    rows[0]["Value"] = "9.99"
    assert labels == before


def test_blank_starts_map_to_null_without_changing_other_strings(labels):
    rows = labels_to_rows(labels)
    rows[0]["Start"] = "  "
    rows[0]["Period"] = " Q3 2026 "
    result = rows_to_labels(rows)
    assert result["reported_diluted_eps"][0]["period_start"] is None
    assert result["reported_diluted_eps"][0]["period"] == " Q3 2026 "
    assert set(result) == set(METRIC_NAMES)
    assert set(result["reported_diluted_eps"][0]) == {
        "value", "currency", "period", "period_start", "period_end",
    }


def test_empty_table_blank_new_rows_add_and_delete_last_observation(labels):
    empty = {metric: [] for metric in METRIC_NAMES}
    assert labels_to_rows(empty) == []
    assert rows_to_labels([]) == empty
    blanks = [{}, dict.fromkeys(COLUMNS), dict.fromkeys(COLUMNS, "  ")]
    assert rows_to_labels(blanks) == empty
    row = labels_to_rows(labels)[0]
    row["EPS type"] = "Adjusted diluted EPS"
    rows = blanks + [row]
    result = rows_to_labels(rows)
    assert result["reported_diluted_eps"] == []
    assert result["adjusted_diluted_eps"][0]["value"] == "4.60"
    rows.pop()
    assert rows_to_labels(rows) == empty


@pytest.mark.parametrize(("column", "value", "message"), [
    ("Value", "4", "value"), ("Value", 4.6, "value"),
    ("Value", "NaN", "value"), ("Value", "1e3", "value"),
    ("Value", "", "value"), ("Currency", "usd", "currency"),
    ("Period", " ", "period"), ("End", "2026-02-30", "period_end"),
    ("End", "20260930", "period_end"), ("End", None, "period_end"),
    ("Start", "2026-10-01", "period_start"), ("Start", "2026-02-29", "period_start"),
    ("EPS type", None, "EPS type"), ("EPS type", "Basic EPS", "EPS type"),
])
def test_bad_row_shows_table_position_and_field(labels, column, value, message):
    rows = labels_to_rows(labels)
    rows[1][column] = value
    result = validate_rows(rows)
    assert result.labels is None
    assert len(result.errors) == 1
    assert "Row 2" in result.errors[0]
    assert message in result.errors[0]
    with pytest.raises(ReviewError, match="Row 2"):
        rows_to_labels(rows)


def test_partial_new_rows_are_invalid_and_all_bad_rows_are_reported(labels):
    rows = labels_to_rows(labels)
    rows += [{"Value": "4.60"}, {"EPS type": "Adjusted diluted EPS"}]
    result = validate_rows(rows)
    assert result.labels is None
    assert any("Row 4" in error for error in result.errors)
    assert any("Row 5" in error for error in result.errors)


@pytest.mark.parametrize("known_start", [True, False])
def test_duplicate_errors_map_back_to_mixed_table_row(labels, known_start):
    rows = labels_to_rows(labels)
    if known_start:
        rows[0]["Start"] = "2026-07-01"
    duplicate = deepcopy(rows[0])
    duplicate["Period"] = "Another label" if known_start else " q3  2026 "
    # Interleave the other metric to ensure metric indices don't become UI rows.
    adjusted = deepcopy(rows[0])
    adjusted["EPS type"] = "Adjusted diluted EPS"
    rows += [adjusted, duplicate]
    result = validate_rows(rows)
    assert len(result.errors) == 1
    assert "Row 5" in result.errors[0]
    assert "duplicate" in result.errors[0]


def test_unknown_start_quarter_and_ytd_can_share_end_date(labels):
    rows = labels_to_rows(labels)
    rows[1]["Start"] = None
    assert rows_to_labels(rows)["reported_diluted_eps"][1]["period_start"] is None


def test_draft_keeps_base_stable_tracks_invalid_edits_and_discards(labels):
    draft = EditorDraft(labels, "opened-fingerprint")
    assert not draft.dirty
    labels["reported_diluted_eps"][0]["value"] = "0.00"
    assert draft.saved_labels["reported_diluted_eps"][0]["value"] == "4.60"
    draft.rows[0]["Value"] = "4.70"
    assert draft.dirty
    assert draft.base_rows[0]["Value"] == "4.60"
    draft.rows[0]["Value"] = "4.60"
    draft.rows.append({})
    assert not draft.dirty  # unused blank addition
    draft.rows[-1] = {"Period": "unfinished"}
    assert draft.dirty
    draft.discard()
    assert not draft.dirty
    assert draft.rows == draft.base_rows
    assert draft.generation == 1
    assert draft.opened_fingerprint == "opened-fingerprint"


def test_capture_latest_widget_changes_for_navigation(labels):
    draft = EditorDraft(labels, "fingerprint")
    draft.capture_widget_changes({
        "edited_rows": {"0": {"Value": "-4.60"}}, "deleted_rows": [1],
        "added_rows": [{"EPS type": "Adjusted diluted EPS", "Value": "unfinished"}],
    })
    assert len(draft.rows) == 3
    assert draft.rows[0]["Value"] == "-4.60"
    assert draft.rows[1]["Currency"] == "TWD"
    assert draft.rows[2]["Currency"] is None
    assert draft.dirty
    assert draft.base_rows[0]["Value"] == "4.60"
    draft.capture_widget_changes({})
    assert not draft.dirty
