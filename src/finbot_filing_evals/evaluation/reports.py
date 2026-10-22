"""Human-readable reports and explicitly typed Parquet datasets."""

from .files import digest, load_run, write_json
from .scoring import COUNTS
from .contracts import FISCAL_CONTRACT, FISCAL_FIELDS, LEGACY_CONTRACT, period_display
from ..review.errors import ReviewError


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def percent(value):
    return "n/a" if value is None else f"{value:.1%}"


def token_total(results, key):
    """Display known provider counts without treating absent usage as zero."""
    counts = [case.get('usage', {}).get(key) for case in results['cases']]
    known = [value for value in counts if type(value) is int and value >= 0]
    if len(known) == len(counts):
        return f'{sum(known):,}'
    value = f'{sum(known):,}' if known else 'n/a'
    return f'{value} (partial; {len(known)}/{len(counts)} filings reported)'


def report(manifest, results):
    summary = results["summary"]
    lines = ["# EPS evaluation", "", f"Run: {manifest['run_id']}", "",
             f"Extractor: {cell(manifest['extractor']['name'])} · {cell(manifest['extractor']['model'])}", "",
             f"Dataset revision: `{manifest['dataset_revision']}`", "",
             f"Label contract: `{manifest.get('label_contract', LEGACY_CONTRACT)}`", "",
             f"Preprocessing: {cell(manifest.get('preprocessing', 'not recorded'))}", "",
             f"Provider-reported inputTokens: {token_total(results, 'inputTokens')} · "
             f"outputTokens: {token_total(results, 'outputTokens')}", "",
             f"Precision: {percent(summary['precision'])} · Recall: {percent(summary['recall'])} · "
             f"F1: {percent(summary['f1'])} · Exact filings: {summary['exact_cases']}/{summary['case_count']}", "",
             f"Extraction errors: {summary['extraction_errors']} · Measured runtime: {summary['duration_seconds']:.2f}s · "
             f"Known estimated cost: ${summary['known_cost_usd']} "
             f"({'complete' if summary['cost_complete'] else 'incomplete; unknown costs are not zero'})", "",
             "| Metric | Correct | Incorrect value | Missing | Extra | Precision | Recall | F1 |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for metric, score in summary["per_metric"].items():
        lines.append("| " + " | ".join([metric, *(str(score[k]) for k in COUNTS),
                                       *(percent(score[k]) for k in ("precision", "recall", "f1"))]) + " |")
    projection = manifest.get('target_projection')
    if projection:
        lines += ['', f"Golden targets: {projection['target_observation_count']} quarterly/annual observations; "
                  f"{projection['excluded_observation_count']} cumulative/YTD observations excluded from "
                  f"{projection['source_observation_count']} reviewed source observations."]
    lines += ["", "## Filing results", "",
              "| Filing | Status | Correct | Incorrect value | Missing | Extra | Exact |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for case in results["cases"]:
        lines.append("| " + " | ".join([cell(case['case_id']), case['status'],
                                       *(str(case['score'][k]) for k in COUNTS), str(case['score']['exact'])]) + " |")
    for case in results["cases"]:
        differences = [item for item in case["score"]["observations"] if item["status"] != "correct"]
        if not differences and not case["error"]:
            continue
        lines += ["", f"## {cell(case['case_id'])}", ""]
        if case["error"]:
            lines += [cell(case["error"]), ""]
        for item in differences:
            lines += [f"- {item['status']} · {item['metric']}",
                      f"  Fiscal period: {cell(period_display(item['golden'] or item['predicted']))}",
                      f"  Golden: {cell(item['golden'])}",
                      f"  Predicted: {cell(item['predicted'])}"]
    lines += ["", "## Scoring policy", ""]
    lines += [f"- {key}: {value}" for key, value in manifest["scoring_policy"].items()]
    lines += ["", "Incorrect values count against both precision and recall. Invalid responses and failed calls",
              "remain in the denominator; failed empty filings are never exact matches.", "",
              "These scores describe this small golden dataset, not performance on unseen filings.", ""]
    return "\n".join(lines)


def write_parquet(root, name, rows, schema, manifest):
    import pyarrow as pa
    import pyarrow.parquet as pq

    path = root / f"{name}.parquet"
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(table, path)
    if pq.read_table(path).to_pylist() != rows:
        raise ReviewError("Evaluation Parquet round-trip failed.")
    write_json(root / f"{name}.metadata.json", dict(
        dataset_name=f"filing-evals.{name}", owner_repo="finbot-filing-evals",
        schema_version=manifest['schema_version'], label_contract=manifest.get('label_contract', LEGACY_CONTRACT), run_id=manifest['run_id'],
        generated_at_utc=manifest['finished_at_utc'], row_count=len(rows),
        parquet_file=path.name, sha256=digest(path.read_bytes()),
        partial=manifest['status'] != 'completed', dataset_revision=manifest['dataset_revision'],
    ))


def export_tables(root, manifest, results):
    import pyarrow as pa

    text = ("case_id", "ticker", "form_type", "status", "error", "cost_usd")
    fields = [pa.field(key, pa.string()) for key in text]
    fields += [pa.field(key, pa.int64()) for key in COUNTS]
    fields += [pa.field('exact', pa.bool_()), pa.field('duration_seconds', pa.float64())]
    rows = [dict(**{key: case[key] for key in text},
                 **{key: case['score'][key] for key in COUNTS},
                 exact=case['score']['exact'], duration_seconds=case['duration_seconds'])
            for case in results['cases']]
    write_parquet(root, 'cases', rows, pa.schema(fields), manifest)
    fiscal = manifest.get('label_contract') == FISCAL_CONTRACT
    observation_fields = FISCAL_FIELDS if fiscal else ('value', 'currency', 'period', 'period_start', 'period_end')
    names = ['case_id', 'metric', 'status'] + [
        f'{side}_{field}' for side in ('golden', 'predicted') for field in observation_fields
    ]
    rows = [dict(case_id=case['case_id'], metric=item['metric'], status=item['status'], **{
        f'{side}_{field}': item[side][field] if item[side] else None
        for side in ('golden', 'predicted') for field in observation_fields
    }) for case in results['cases'] for item in case['score']['observations']]
    integer_fields = {f'{side}_{field}' for side in ('golden', 'predicted') for field in ('fiscal_year', 'fiscal_quarter')} if fiscal else set()
    schema = pa.schema([pa.field(key, pa.int64() if key in integer_fields else pa.string()) for key in names])
    write_parquet(root, 'observations', rows, schema, manifest)


def compare(baseline, candidate):
    left, left_results = load_run(baseline)
    right, right_results = load_run(candidate)
    if left.get('label_contract', LEGACY_CONTRACT) != right.get('label_contract', LEGACY_CONTRACT):
        raise ReviewError('Run comparison requires the same label contract; legacy and fiscal v2 scores cannot be compared.')
    if left['dataset_revision'] != right['dataset_revision'] or left['scoring_policy'] != right['scoring_policy']:
        raise ReviewError("Run comparison requires the same frozen dataset revision and scoring policy.")
    old = {case['case_id']: case for case in left_results['cases']}
    if set(old) != {case['case_id'] for case in right_results['cases']}:
        raise ReviewError("Run comparison requires identical filing membership.")
    lines = ['# EPS run comparison', '', f"Baseline: {left['run_id']}", '', f"Candidate: {right['run_id']}", '',
             f"Baseline preprocessing: {cell(left.get('preprocessing', 'not recorded'))}", '',
             f"Candidate preprocessing: {cell(right.get('preprocessing', 'not recorded'))}", '',
             '| Measure | Baseline | Candidate |', '| --- | --- | --- |']
    for key in ('precision', 'recall', 'f1', 'exact_case_rate', 'extraction_errors', 'known_cost_usd', 'cost_complete', 'duration_seconds'):
        a, b = left_results['summary'][key], right_results['summary'][key]
        if key in ('precision', 'recall', 'f1', 'exact_case_rate'):
            a, b = percent(a), percent(b)
        lines.append(f'| {key} | {a} | {b} |')
    for key in ('inputTokens', 'outputTokens'):
        lines.append(f'| {key} | {token_total(left_results, key)} | {token_total(right_results, key)} |')
    lines += ['', '| Filing | Baseline F1 | Candidate F1 | Change |', '| --- | --- | --- | --- |']
    for case in right_results['cases']:
        previous = old[case['case_id']]
        def rank(item):
            return (item['status'] == 'ok', item['score']['exact'], item['score']['f1'])
        change = 'improved' if rank(case) > rank(previous) else 'regressed' if rank(case) < rank(previous) else 'unchanged'
        lines.append(f"| {cell(case['case_id'])} | {percent(previous['score']['f1'])} | {percent(case['score']['f1'])} | {change} |")
    lines += ['', 'Change prioritizes extraction success, then exact filing match, then observation F1.',
              'Equal scores may still contain different mistakes; inspect the filing details in each report.', '']
    return '\n'.join(lines)
