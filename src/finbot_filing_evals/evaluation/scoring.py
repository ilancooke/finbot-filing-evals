"""Versioned, deterministic matching of validated EPS observations."""

from decimal import Decimal

from ..review.validation import METRICS
from .contracts import FISCAL_CONTRACT, LEGACY_CONTRACT, require_contract, validate_labels

POLICY = {
    "version": "eps_exact.v1",
    "identity": "metric, currency, start and end; normalized period also required when start is null",
    "value": "exact Decimal equality, no tolerance; trailing zeroes are equivalent",
    "period": "wording ignored for known date intervals; otherwise collapse whitespace and casefold",
    "unknown_start": "null matches only null; never infer dates",
    "identity_error": "a wrong metric, currency or interval counts as missing plus extra",
    "invalid_output": "whole filing fails; all golden observations are missing; never an exact case",
    "zero_denominator": "precision/recall null; F1 is 1 only for a successful empty/empty result",
}
COUNTS = ("correct", "incorrect", "missing", "extra")
FISCAL_POLICY = {
    'version': 'eps_fiscal_exact.v2',
    'identity': 'metric, currency, period_type, fiscal_year and fiscal_quarter',
    'value': 'exact Decimal equality, no tolerance; trailing zeroes are equivalent',
    'scope': 'standalone quarterly and annual results only; cumulative/YTD observations excluded',
    'period': 'structured fiscal identifiers only; no dates or free-text period matching',
    'identity_error': 'a wrong metric, currency, fiscal year, quarter or period type counts as missing plus extra',
    'invalid_output': POLICY['invalid_output'],
    'zero_denominator': POLICY['zero_denominator'],
}


def policy_for(contract):
    require_contract(contract)
    return dict(FISCAL_POLICY if contract == FISCAL_CONTRACT else POLICY)


def identity(row, contract=LEGACY_CONTRACT):
    if contract == FISCAL_CONTRACT:
        return (row['currency'], row['period_type'], row['fiscal_year'], row['fiscal_quarter'])
    return (row["currency"], row["period_start"], row["period_end"],
            " ".join(row["period"].split()).casefold() if row["period_start"] is None else None)


def rates(counts, *, failed=False):
    correct, incorrect, missing, extra = (counts[key] for key in COUNTS)
    predicted = correct + incorrect + extra
    expected = correct + incorrect + missing
    return dict(
        **counts, expected=expected, predicted=predicted,
        precision=correct / predicted if predicted else None,
        recall=correct / expected if expected else None,
        f1=2 * correct / (predicted + expected) if predicted + expected else float(not failed),
    )


def score_case(golden, predicted, *, failed=False, contract=LEGACY_CONTRACT):
    validate_labels(golden, contract=contract)
    if not failed:
        validate_labels(predicted, contract=contract)
    details, per_metric = [], {}
    for metric in METRICS:
        actual = {} if failed else {identity(row, contract): row for row in predicted[metric]}
        counts = dict.fromkeys(COUNTS, 0)
        for expected in golden[metric]:
            found = actual.pop(identity(expected, contract), None)
            status = "missing" if found is None else (
                "correct" if Decimal(found["value"]) == Decimal(expected["value"]) else "incorrect"
            )
            counts[status] += 1
            details.append(dict(metric=metric, status=status, golden=expected, predicted=found))
        for found in actual.values():
            counts["extra"] += 1
            details.append(dict(metric=metric, status="extra", golden=None, predicted=found))
        per_metric[metric] = rates(counts, failed=failed)
    total = {key: sum(item[key] for item in per_metric.values()) for key in COUNTS}
    return dict(**rates(total, failed=failed), exact=not failed and not any(
        total[key] for key in ("incorrect", "missing", "extra")
    ), per_metric=per_metric, observations=details)


def summarize(cases):
    failures = sum(case["status"] != "ok" for case in cases)
    counts = {key: sum(case["score"][key] for case in cases) for key in COUNTS}
    per_metric = {
        metric: rates({key: sum(case["score"]["per_metric"][metric][key] for case in cases)
                       for key in COUNTS}, failed=bool(failures))
        for metric in METRICS
    }
    costs = [case["cost_usd"] for case in cases]
    return dict(
        **rates(counts, failed=bool(failures)), case_count=len(cases),
        exact_cases=sum(case["score"]["exact"] for case in cases), extraction_errors=failures,
        exact_case_rate=sum(case["score"]["exact"] for case in cases) / len(cases),
        duration_seconds=sum(case["duration_seconds"] for case in cases),
        known_cost_usd=str(sum((Decimal(cost) for cost in costs if cost is not None), Decimal(0))),
        cost_complete=all(cost is not None for cost in costs), per_metric=per_metric,
    )
