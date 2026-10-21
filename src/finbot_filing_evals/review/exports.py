"""Deterministic label exports from authoritative cases; no UI or disk writes."""

from collections import Counter
from copy import deepcopy
from hashlib import sha256
import io
import json
from typing import Any

from .dataset import ReviewDataset
from .errors import ReviewError
from .validation import METRICS

COLUMNS = (
    "case_id", "ticker", "filing_id", "form_type", "metric", "value", "currency",
    "period", "period_start", "period_end", "review_status",
)
EXPORT_FILES = ("labels.json", "labels.parquet", "labels.metadata.json", "dataset.json", "REVIEW.md")


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def flat_labels(records: list[dict]) -> list[dict]:
    return [
        dict(case_id=case["case_id"], ticker=case["filing"]["ticker"],
             filing_id=case["filing"]["filing_id"], form_type=case["filing"]["form_type"],
             metric=metric, **observation, review_status=case["review"]["status"])
        for case in records for metric in METRICS for observation in case["labels"][metric]
    ]


def review_state(records: list[dict]) -> dict:
    reviewed = sum(case["review"]["status"] == "human_reviewed" for case in records)
    complete = reviewed == len(records)
    return dict(
        reviewed_case_count=reviewed, unreviewed_case_count=len(records) - reviewed,
        review_status="human_reviewed" if complete else "in_progress" if reviewed else "unreviewed",
        human_reviewed=complete, label_source="human_reviewed" if complete else "agent_draft",
    )


def _cell(value: Any) -> str:
    return str(value if value is not None else "Unknown").replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def review_markdown(dataset: ReviewDataset, records: list[dict]) -> bytes:
    state = review_state(records)
    rows = flat_labels(records)
    lines = ["# EPS golden dataset review", "",
             f"{len(records)} filing packages · {dataset.document_count} original documents · "
             f"{len(rows)} EPS observations · {state['reviewed_case_count']} confirmed.", "",
             "Saving corrections does not confirm a filing. Confirmation covers the complete package.",
             "Empty arrays mean no qualifying observation was identified; unknown starts remain unresolved.", "",
             "## Scope and policy", ""]
    for key, value in dataset.to_dict().get("policy", {}).items():
        lines.extend([f"- {_cell(key)}: {_cell(value)}"])
    for model, case in zip(dataset.cases, records, strict=True):
        filing = case["filing"]
        lines.extend(["", f"## {_cell(filing['ticker'])} · {_cell(filing['form_type'])} · {filing['filing_id']}", "",
                      f"Status: {case['review']['status']} · Confirmation: {case['review'].get('reviewed_at_utc') or 'None'}", "",
                      "| Metric | Value | Currency | Period | Start | End |",
                      "| --- | --- | --- | --- | --- | --- |"])
        for metric in METRICS:
            for obs in case["labels"][metric]:
                lines.append("| " + " | ".join(_cell(v) for v in [metric, obs['value'], obs['currency'], obs['period'], obs['period_start'], obs['period_end']]) + " |")
            if not case["labels"][metric]:
                lines.append(f"| {metric} | — | — | No qualifying observation identified | — | — |")
        lines.extend(["", "Documents:", ""])
        lines.extend(f"- [{doc.filename}]({doc.relative_path})" for doc in model.documents)
        lines.extend(["", "Review notes:", ""])
        lines.extend(f"- {_cell(note)}" for note in case["review"]["notes"])
    lines.extend(["", "## Saving and recovery", "",
                  "Use Save changes in the local review app. Derived exports and integrity hashes are synchronized together.",
                  "If synchronization is pending, use Retry synchronization before further saves or filing navigation.",
                  "Structural and hash checks do not establish accounting correctness.", ""])
    return "\n".join(lines).encode("utf-8")


def build_exports(dataset: ReviewDataset, records: list[dict], metadata: dict, timestamp: str) -> dict[str, bytes]:
    """Build/round-trip all replacements in memory before any authoritative write."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    rows = flat_labels(records)
    schema = pa.schema([pa.field(name, pa.string()) for name in COLUMNS])
    table = pa.Table.from_pylist(rows, schema=schema)
    sink = io.BytesIO()
    pq.write_table(table, sink)
    parquet = sink.getvalue()
    if pq.read_table(io.BytesIO(parquet)).to_pylist() != rows:
        raise ReviewError("Staged JSON/Parquet labels do not agree.")
    state = review_state(records)
    manifest = dataset.to_dict()
    manifest.update(state, case_count=len(records), document_count=dataset.document_count,
                    observation_count=len(rows), updated_at_utc=timestamp,
                    filing_types=dict(Counter(case['filing']['form_type'] for case in records)))
    sidecar = deepcopy(metadata)
    keys = sidecar.get("primary_key", ["case_id", "metric", "currency", "period"])
    if not isinstance(keys, list) or not keys or any(not isinstance(key, str) or key not in COLUMNS for key in keys):
        raise ReviewError("Label metadata primary_key must name export columns.")
    identities = [tuple(row[key] for key in keys) for row in rows]
    sidecar.update(state, row_count=len(rows), entity_count=len({row['ticker'] for row in rows}),
                   parquet_file="labels.parquet", sha256=sha256(parquet).hexdigest(),
                   duplicate_key_count=len(identities) - len(set(identities)),
                   missing_required_columns=[], partial=not state['human_reviewed'], updated_at_utc=timestamp)
    # generated_at_utc describes this export; retain the initial generation separately.
    sidecar.setdefault("created_at_utc", sidecar.get("generated_at_utc", timestamp))
    sidecar["generated_at_utc"] = timestamp
    sidecar["notes"] = "All filing packages confirmed." if state['human_reviewed'] else "EPS annotations await complete human review."
    return {"dataset.json": json_bytes(manifest), "labels.json": json_bytes(rows),
            "labels.parquet": parquet, "labels.metadata.json": json_bytes(sidecar),
            "REVIEW.md": review_markdown(dataset, records)}
