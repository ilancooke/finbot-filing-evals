"""Fiscal v2 contract, reviewed-target projection and legacy-run isolation."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from conftest import prepare_bundle, save_json
from test_evaluation import all_hashes, config, labels, observation, predictions, reviewed
from finbot_filing_evals.evaluation import bedrock, extractor, runner
from finbot_filing_evals.evaluation.cli import main
from finbot_filing_evals.evaluation.contracts import (
    FISCAL_CONTRACT, FISCAL_FIELDS, LEGACY_CONTRACT, fiscal_period,
    load_schema, period_display, project_labels, validate_labels,
)
from finbot_filing_evals.evaluation.files import load_run, read_json, seal
from finbot_filing_evals.evaluation.reports import compare
from finbot_filing_evals.evaluation.scoring import policy_for, score_case
from finbot_filing_evals.review.dataset import load_dataset
from finbot_filing_evals.review.errors import ReviewError


def fiscal_row(**changes):
    return dict(value='4.60', currency='USD', period_type='quarterly', fiscal_year=2026, fiscal_quarter=3) | changes


def fiscal_labels(*rows):
    return dict(reported_diluted_eps=list(rows), adjusted_diluted_eps=[])


@pytest.fixture
def fiscal_config(config):
    record = read_json(config)
    record['label_contract'] = FISCAL_CONTRACT
    save_json(config, record)
    return config


def fiscal_predictions(root, path):
    records = {}
    for case in load_dataset(root).cases:
        targets, _ = project_labels(case.to_dict()['labels'], location=case.case_id)
        records[case.case_id] = dict(labels=targets, cost_usd='0.001', usage={})
    save_json(path, dict(schema_version='eps_predictions.v2', label_contract=FISCAL_CONTRACT, cases=records))
    return path


@pytest.mark.parametrize('description,expected', [
    ('Q3 2026', ('quarterly', 2026, 3)),
    ('Fiscal Q3 2026', ('quarterly', 2026, 3)),
    ('FY2026 Q3', ('quarterly', 2026, 3)),
    ('q3 FY2026', ('quarterly', 2026, 3)),
    ('Third Quarter 2026', ('quarterly', 2026, 3)),
    ('third fiscal quarter of FY2026', ('quarterly', 2026, 3)),
    ('Q4 2025', ('quarterly', 2025, 4)),
    ('  FY2026  ', ('annual', 2026, None)),
    ('Fiscal year 2026', ('annual', 2026, None)),
    ('Annual 2026', ('annual', 2026, None)),
])
def test_explicit_fiscal_periods_are_standardized(description, expected):
    result = fiscal_period(description)
    assert tuple(result[key] for key in ('period_type', 'fiscal_year', 'fiscal_quarter')) == expected


@pytest.mark.parametrize('description', [
    'Nine months 2026', 'Nine fiscal months 2026', 'Three fiscal quarters 2026',
    'Six months 2026', '2 fiscal quarters 2026', 'YTD 2026', 'FY-to-date 2026',
    'Year to date FY2026', 'Q1-Q3 FY2026', 'Q1–Q3 2026',
])
def test_cumulative_and_ytd_observations_are_explicitly_excluded(description):
    assert fiscal_period(description) is None


@pytest.mark.parametrize('description', [
    'Quarterly', 'Q3', 'FY', 'Q5 2026', '2026', 'Q3 2025/2026',
    'Q3 and YTD 2026', 'Q3 2026 or Q2 2026', 'Year ended September 30, 2026',
    'Three months ended September 30, 2026', '',
])
def test_ambiguous_descriptions_are_not_inferred_from_dates(description):
    with pytest.raises(ReviewError, match='Ambiguous or unsupported'):
        fiscal_period(description)


def test_projection_preserves_amounts_currencies_and_ignores_dates():
    source = labels(observation(value='-4.600', period='Fiscal Q3 2026'),
                    observation(value='29.43', currency='TWD', period='Q3 2026'),
                    observation(value='9.00', period='Nine fiscal months 2026', period_start='2026-01-01'))
    original = deepcopy(source)
    projected, excluded = project_labels(source)
    assert source == original
    assert projected == fiscal_labels(fiscal_row(value='-4.600'), fiscal_row(value='29.43', currency='TWD'))
    assert excluded == [dict(metric='reported_diluted_eps', source_index=2,
                             period='Nine fiscal months 2026', reason='cumulative/YTD')]
    source['reported_diluted_eps'][0].update(period_start=None, period_end='2026-10-01')
    assert project_labels(source) == (projected, excluded)
    assert all(set(row) == set(FISCAL_FIELDS) for rows in projected.values() for row in rows)
    assert period_display(projected['reported_diluted_eps'][0]) == 'FY2026 Q3'


def test_annual_and_q4_are_distinct_and_no_q4_is_calculated():
    source = labels(observation(value='4.60', period='FY2026'),
                    observation(value='1.20', period='Q4 2026', period_start='2026-10-01', period_end='2026-12-31'),
                    observation(value='3.40', period='Nine months 2026', period_start='2026-01-01'))
    targets, excluded = project_labels(source)
    assert targets == fiscal_labels(fiscal_row(period_type='annual', fiscal_quarter=None), fiscal_row(value='1.20', fiscal_quarter=4))
    assert len(excluded) == 1
    annual_only, _ = project_labels(labels(source['reported_diluted_eps'][0], source['reported_diluted_eps'][2]))
    assert len(annual_only['reported_diluted_eps']) == 1
    assert period_display(annual_only['reported_diluted_eps'][0]) == 'FY2026'
    score = score_case(fiscal_labels(fiscal_row(period_type='annual', fiscal_quarter=None)),
                       fiscal_labels(fiscal_row(fiscal_quarter=4)), contract=FISCAL_CONTRACT)
    assert score['missing'] == score['extra'] == 1


@pytest.mark.parametrize('changes', [
    dict(period_type='ytd'), dict(period_type='quarterly', fiscal_quarter=None),
    dict(period_type='annual', fiscal_quarter=4), dict(fiscal_quarter=0), dict(fiscal_quarter=5),
    dict(fiscal_quarter='Q3'), dict(fiscal_year='2026'), dict(fiscal_year=True),
    dict(fiscal_year=2026.0), dict(fiscal_quarter=3.0), dict(currency='NT$'),
    dict(value=4.60), dict(period='FY2026 Q3'), dict(period_start=None), dict(period_end='2026-09-30'),
])
def test_fiscal_schema_rejects_noncanonical_or_legacy_fields(changes):
    with pytest.raises(ReviewError):
        validate_labels(fiscal_labels(fiscal_row(**changes)), contract=FISCAL_CONTRACT)


def test_duplicates_after_projection_cannot_be_silently_deduplicated():
    # Legacy intervals differ, but the new fiscal identity collides.
    source = labels(observation(period='Q3 2026'),
                    observation(period='Fiscal Q3 2026', period_start='2026-07-02'))
    with pytest.raises(ReviewError, match='duplicate fiscal-period'):
        project_labels(source)
    with pytest.raises(ReviewError, match='duplicate fiscal-period'):
        validate_labels(fiscal_labels(fiscal_row(), fiscal_row(value='5.25')), contract=FISCAL_CONTRACT)


def test_fiscal_scoring_is_exact_on_identity_and_decimal_but_not_order():
    gold = fiscal_labels(fiscal_row(), fiscal_row(currency='TWD', value='29.43'))
    predicted = fiscal_labels(fiscal_row(currency='TWD', value='29.430'), fiscal_row(value='4.600'))
    assert score_case(gold, predicted, contract=FISCAL_CONTRACT)['exact']
    predicted['reported_diluted_eps'][1]['value'] = '4.61'
    score = score_case(gold, predicted, contract=FISCAL_CONTRACT)
    assert (score['correct'], score['incorrect'], score['missing'], score['extra']) == (1, 1, 0, 0)
    assert score['precision'] == score['recall'] == 0.5
    for change in (dict(fiscal_year=2025), dict(fiscal_quarter=2), dict(currency='EUR')):
        score = score_case(fiscal_labels(fiscal_row()), fiscal_labels(fiscal_row(**change)), contract=FISCAL_CONTRACT)
        assert score['missing'] == score['extra'] == 1


def test_complete_fiscal_run_has_date_free_targets_and_preserves_source(reviewed, fiscal_config, tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    source_before = all_hashes(reviewed)
    path = fiscal_predictions(reviewed, tmp_path / 'predictions.json')
    output = tmp_path / 'fiscal-run'
    manifest, results = runner.run(reviewed, output, fiscal_config, predictions=path)
    assert manifest['schema_version'] == 'eps_evaluation.v2'
    assert manifest['label_contract'] == FISCAL_CONTRACT
    assert manifest['scoring_policy'] == policy_for(FISCAL_CONTRACT)
    assert results['summary']['correct'] == 3
    assert results['summary']['exact_cases'] == 2
    projection = read_json(output / 'target_projection.json')
    assert projection['source_observation_count'] == 4
    assert projection['target_observation_count'] == 3
    assert projection['excluded_observation_count'] == 1
    assert len(projection['excluded']) == 1
    golden = read_json(output / 'golden.json')
    for text in (json.dumps(golden), (output / 'REPORT.md').read_text()):
        assert 'period_start' not in text and 'period_end' not in text
    assert 'FY2026 Q3' not in json.dumps(golden)  # identity is structural, not a display label
    assert read_json(output / 'source_snapshot.json')['cases'][0]['labels']['reported_diluted_eps'][0]['value'] == '4.60'
    assert read_json(output / 'labels.schema.json') == load_schema(FISCAL_CONTRACT)
    for case in load_dataset(reviewed).cases:
        request = read_json(output / 'inputs' / case.case_id / 'request.json')
        assert request['schema_version'] == 'eps_extraction_request.v2'
        assert request['label_contract'] == FISCAL_CONTRACT
        assert request['label_schema'] == load_schema(FISCAL_CONTRACT)
        assert 'labels' not in request and 'notes' not in request
    table = pq.read_table(output / 'observations.parquet')
    assert 'golden_period_start' not in table.column_names and 'golden_period_end' not in table.column_names
    assert table.schema.field('golden_fiscal_year').type == pa.int64()
    assert table.schema.field('golden_fiscal_quarter').type == pa.int64()
    assert table.schema.field('golden_value').type == pa.string()
    assert table.to_pylist()[0]['golden_value'] == '4.60'
    assert read_json(output / 'observations.metadata.json')['label_contract'] == FISCAL_CONTRACT
    assert read_json(output / 'predictions.json')['schema_version'] == 'eps_predictions.v2'
    assert load_run(output) == (manifest, results)
    assert all_hashes(reviewed) == source_before
    assert not (reviewed / '.review').exists()


def test_fiscal_report_explains_errors_in_canonical_periods(reviewed, fiscal_config, tmp_path):
    path = fiscal_predictions(reviewed, tmp_path / 'predictions.json')
    saved = read_json(path)
    next(iter(saved['cases'].values()))['labels']['reported_diluted_eps'][0]['value'] = '0.00'
    save_json(path, saved)
    output = tmp_path / 'wrong-value'
    _, results = runner.run(reviewed, output, fiscal_config, predictions=path)
    assert results['summary']['incorrect'] == 1
    assert 'FY2026 Q3' in (output / 'REPORT.md').read_text()
    assert 'cumulative/YTD observations excluded' in (output / 'REPORT.md').read_text()


def test_ambiguous_reviewed_period_stops_before_any_provider_call(reviewed, fiscal_config, tmp_path, monkeypatch):
    case = load_dataset(reviewed).cases[0]
    record = case.to_dict()
    record['labels']['reported_diluted_eps'][0]['period'] = 'Quarterly'
    save_json(case.path, record)
    prepare_bundle(reviewed)
    before = all_hashes(reviewed)
    def forbidden(*args, **kwargs):
        raise AssertionError('Ambiguous targets must fail before extraction')
    monkeypatch.setattr(extractor, 'invoke', forbidden)
    with pytest.raises(ReviewError, match='Quarterly'):
        runner.run(reviewed, tmp_path / 'ambiguous', fiscal_config)
    assert not (tmp_path / 'ambiguous').exists()
    assert all_hashes(reviewed) == before


def test_new_predictions_and_runs_are_not_reinterpreted_as_legacy(reviewed, config, fiscal_config, tmp_path):
    # These fixtures share a config file: save an explicit legacy copy first.
    legacy_config = tmp_path / 'legacy-config.json'
    save_json(legacy_config, read_json(fiscal_config) | {'label_contract': LEGACY_CONTRACT})
    legacy_predictions = predictions(reviewed, tmp_path / 'legacy-predictions.json')
    legacy_output = tmp_path / 'legacy'
    runner.run(reviewed, legacy_output, legacy_config, predictions=legacy_predictions)
    legacy_manifest = read_json(legacy_output / 'run.json')
    legacy_manifest.pop('label_contract')  # Original stored runs omitted this field.
    save_json(legacy_output / 'run.json', legacy_manifest)
    seal(legacy_output)
    before = all_hashes(legacy_output)
    with pytest.raises(ReviewError, match='legacy predictions are not converted'):
        runner.run(reviewed, tmp_path / 'wrong-input', fiscal_config, predictions=legacy_predictions)
    new_predictions = fiscal_predictions(reviewed, tmp_path / 'fiscal-predictions.json')
    fiscal_output = tmp_path / 'fiscal'
    runner.run(reviewed, fiscal_output, fiscal_config, predictions=new_predictions)
    assert load_run(legacy_output)[0]['schema_version'] == 'eps_evaluation.v1'
    assert 'unchanged' in compare(legacy_output, legacy_output)
    with pytest.raises(ReviewError, match='same label contract'):
        compare(legacy_output, fiscal_output)
    with pytest.raises(ReviewError):
        runner.run(reviewed, tmp_path / 'wrong-legacy-input', legacy_config, predictions=new_predictions)
    assert all_hashes(legacy_output) == before


def test_fiscal_rescore_compare_and_cli_use_versioned_envelopes(reviewed, fiscal_config, tmp_path, capsys):
    saved = fiscal_predictions(reviewed, tmp_path / 'predictions.json')
    common = ['run', '--dataset-root', str(reviewed), '--config', str(fiscal_config)]
    assert main(common + ['--output', str(tmp_path / 'a'), '--predictions', str(saved)]) == 0
    assert main(common + ['--output', str(tmp_path / 'b'), '--predictions', str(tmp_path / 'a/predictions.json')]) == 0
    assert read_json(tmp_path / 'a/results.json') == read_json(tmp_path / 'b/results.json')
    assert main(['compare', str(tmp_path / 'a'), str(tmp_path / 'b')]) == 0
    assert 'unchanged' in capsys.readouterr().out


@pytest.mark.parametrize('alteration', ['version', 'contract', 'omitted', 'unknown'])
def test_bad_fiscal_saved_envelopes_fail_clearly(reviewed, fiscal_config, tmp_path, alteration):
    saved = fiscal_predictions(reviewed, tmp_path / 'predictions.json')
    data = read_json(saved)
    if alteration == 'version':
        data['schema_version'] = 'eps_predictions.v1'
    elif alteration == 'contract':
        data['label_contract'] = LEGACY_CONTRACT
    elif alteration == 'omitted':
        data['cases'].pop(next(iter(data['cases'])))
    else:
        data['cases']['unknown-case'] = dict(labels=fiscal_labels())
    save_json(saved, data)
    with pytest.raises(ReviewError):
        runner.run(reviewed, tmp_path / alteration, fiscal_config, predictions=saved)


def test_cumulative_only_case_remains_in_exact_case_denominator(reviewed, fiscal_config, tmp_path):
    case = load_dataset(reviewed).cases[0]
    record = case.to_dict()
    record['labels'] = labels(record['labels']['reported_diluted_eps'][1])
    save_json(case.path, record)
    manifest = read_json(reviewed / 'dataset.json')
    manifest['observation_count'] = 2
    save_json(reviewed / 'dataset.json', manifest)
    prepare_bundle(reviewed)
    path = fiscal_predictions(reviewed, tmp_path / 'predictions.json')
    _, results = runner.run(reviewed, tmp_path / 'empty-target', fiscal_config, predictions=path)
    assert results['summary']['case_count'] == 2
    assert results['summary']['correct'] == 1
    assert results['summary']['exact_cases'] == 2
    assert results['cases'][0]['score']['expected'] == 0


@pytest.mark.parametrize('annual', [False, True])
def test_empty_and_annual_exports_keep_nullable_integer_quarter_columns(reviewed, fiscal_config, tmp_path, annual):
    import pyarrow as pa
    import pyarrow.parquet as pq

    for case in load_dataset(reviewed).cases:
        record = case.to_dict()
        record['labels'] = labels(observation(period='FY2026')) if annual else labels()
        save_json(case.path, record)
    manifest = read_json(reviewed / 'dataset.json')
    manifest['observation_count'] = 2 if annual else 0
    save_json(reviewed / 'dataset.json', manifest)
    prepare_bundle(reviewed)
    path = fiscal_predictions(reviewed, tmp_path / 'predictions.json')
    output = tmp_path / 'export'
    _, results = runner.run(reviewed, output, fiscal_config, predictions=path)
    table = pq.read_table(output / 'observations.parquet')
    assert table.schema.field('golden_fiscal_quarter').type == pa.int64()
    assert table.num_rows == (2 if annual else 0)
    assert all(row['golden_fiscal_quarter'] is None for row in table.to_pylist())
    assert results['summary']['exact_cases'] == 2


def test_command_receives_fiscal_schema_and_returns_only_fiscal_targets(reviewed, fiscal_config, tmp_path, monkeypatch):
    def execute(command, **kwargs):
        request = json.loads(kwargs['input'])
        assert request['label_contract'] == FISCAL_CONTRACT
        assert 'period_start' not in json.dumps(request['label_schema'])
        assert 'period_end' not in json.dumps(request['label_schema'])
        kwargs['stdout'].write(json.dumps({'labels': fiscal_labels()}).encode())
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(extractor.subprocess, 'run', execute)
    _, results = runner.run(reviewed, tmp_path / 'command', fiscal_config)
    assert results['summary']['extraction_errors'] == 0
    assert results['summary']['missing'] == 3


def test_bedrock_adapter_sends_fiscal_tool_schema_and_scores_native_arguments(reviewed, tmp_path, monkeypatch):
    config_root = Path(__file__).parents[1] / 'configs'
    targets = {case.ticker: project_labels(case.to_dict()['labels'])[0] for case in load_dataset(reviewed).cases}
    expected_prompt = None
    def converse(**params):
        assert params['system'][0]['text'].startswith(expected_prompt)
        assert params['toolConfig']['tools'][0]['toolSpec']['inputSchema']['json'] == load_schema(FISCAL_CONTRACT)
        context = json.loads(params['messages'][0]['content'][0]['text'].removeprefix('Filing context: '))
        return dict(stopReason='tool_use', output={'message': {'content': [
            {'toolUse': {'name': 'submit_eps', 'input': targets[context['ticker']]}}
        ]}}, usage={'inputTokens': 1000, 'outputTokens': 100})
    monkeypatch.setattr(bedrock, 'make_client', lambda _: SimpleNamespace(converse=converse))
    manifests, configs = [], []
    names = ('bedrock-nova-2-lite', 'bedrock-nova-2-lite-prompt-v3',
             'bedrock-nova-2-lite-prompt-v4', 'bedrock-nova-2-lite-prompt-v5')
    for name in names:
        provider_config = config_root / f'{name}.json'
        config, expected_prompt = extractor.load_config(provider_config)
        configs.append({key: value for key, value in config.items() if key not in {'name', 'prompt_file', 'config_sha256'}})
        manifest, results = runner.run(reviewed, tmp_path / name, provider_config)
        manifests.append(manifest)
        assert (tmp_path / name / 'prompt.txt').read_text() == expected_prompt
        assert results['summary']['correct'] == 3
        assert results['summary']['exact_cases'] == 2
    assert all(config == configs[0] for config in configs)
    assert len({manifest['prompt_sha256'] for manifest in manifests}) == len(manifests)
    for name in names[1:]:
        assert 'unchanged' in compare(tmp_path / 'bedrock-nova-2-lite', tmp_path / name)


def test_archived_configs_and_shipped_fiscal_configs_are_explicit():
    root = Path(__file__).parents[1]
    for provider in ('bedrock-nova-2-lite', 'bedrock-luna'):
        current, prompt = extractor.load_config(root / 'configs' / f'{provider}.json')
        archived, old_prompt = extractor.load_config(root / 'configs/legacy' / f'{provider}-v1.json')
        assert current['label_contract'] == FISCAL_CONTRACT
        assert archived['label_contract'] == LEGACY_CONTRACT
        assert current['model'] == archived['model']
        assert current['settings'] == archived['settings']
        assert current['pricing'] == archived['pricing']
        assert 'Exclude cumulative' in prompt
        assert 'current fiscal year-to-date' in old_prompt


def test_unknown_contract_is_rejected(fiscal_config):
    data = read_json(fiscal_config)
    data['label_contract'] = 'unknown-contract'
    save_json(fiscal_config, data)
    with pytest.raises(ReviewError, match='Unsupported label_contract'):
        extractor.load_config(fiscal_config)
