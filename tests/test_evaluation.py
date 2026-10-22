from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess

import pytest

from conftest import prepare_bundle, save_json
from finbot_filing_evals.evaluation import extractor, runner
from finbot_filing_evals.evaluation.cli import main
from finbot_filing_evals.evaluation.files import load_run, read_json
from finbot_filing_evals.evaluation.reports import compare
from finbot_filing_evals.evaluation.scoring import score_case, summarize
from finbot_filing_evals.review.dataset import load_dataset
from finbot_filing_evals.review.errors import ReviewError


def observation(**changes):
    return dict(value='4.60', currency='USD', period='Q3 2026',
                period_start='2026-07-01', period_end='2026-09-30') | changes


def labels(*rows):
    return dict(reported_diluted_eps=list(rows), adjusted_diluted_eps=[])


@pytest.fixture
def reviewed(writable_dataset):
    for case in load_dataset(writable_dataset).cases:
        record = case.to_dict()
        record['review'].update(status='human_reviewed', reviewed_at_utc='2026-10-22T00:00:00Z')
        save_json(case.path, record)
    return prepare_bundle(writable_dataset)


@pytest.fixture
def config(tmp_path):
    (tmp_path / 'prompt.txt').write_text('Extract reported and adjusted diluted EPS from the supplied filings.')
    path = tmp_path / 'extractor.json'
    save_json(path, dict(name='synthetic', model='fake-model', command=['/fake/python', '/fake/extract.py'],
                         prompt_file='prompt.txt', settings={'temperature': 0}, timeout_seconds=1))
    return path


def predictions(root, destination):
    value = {case.case_id: {'labels': case.to_dict()['labels'], 'cost_usd': '0.001', 'usage': {'input_tokens': 100}}
             for case in load_dataset(root).cases}
    save_json(destination, value)
    return destination


def all_hashes(root):
    return {str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}


def test_exact_numeric_matching_without_float_round_trip():
    expected = labels(observation(), observation(currency='TWD', value='12345678901234567890.01'))
    predicted = deepcopy(expected)
    predicted['reported_diluted_eps'][0].update(value='4.600', period='third quarter')
    assert score_case(expected, predicted)['exact']
    predicted['reported_diluted_eps'][1]['value'] = '12345678901234567890.02'
    score = score_case(expected, predicted)
    assert (score['correct'], score['incorrect'], score['missing'], score['extra']) == (1, 1, 0, 0)
    assert score['precision'] == score['recall'] == score['f1'] == 0.5


@pytest.mark.parametrize('change', [dict(currency='EUR'), dict(period_start=None), dict(period_end='2026-10-01')])
def test_wrong_identity_is_missing_plus_extra(change):
    score = score_case(labels(observation()), labels(observation(**change)))
    assert (score['missing'], score['extra'], score['incorrect'], score['f1']) == (1, 1, 0, 0)


def test_wrong_metric_is_missing_plus_extra():
    row = observation(value='-0.50')
    score = score_case(labels(row), dict(reported_diluted_eps=[], adjusted_diluted_eps=[row]))
    assert score['missing'] == score['extra'] == 1
    assert score['per_metric']['reported_diluted_eps']['missing'] == 1


def test_nullable_starts_and_quarter_ytd_are_not_confused():
    a = observation(period_start=None)
    b = observation(period_start=None, period='Nine months 2026', value='9.00')
    predicted = [dict(b), dict(a, period='  q3   2026 ')]
    assert score_case(labels(a, b), labels(*predicted))['exact']
    predicted[0]['period'] = 'Fiscal year 2026'
    score = score_case(labels(a, b), labels(*predicted))
    assert (score['correct'], score['missing'], score['extra']) == (1, 1, 1)


def test_empty_arrays_negative_and_zero_values():
    empty = score_case(labels(), labels())
    assert empty['exact'] and empty['f1'] == 1
    assert empty['precision'] is empty['recall'] is None
    assert score_case(labels(observation(value='-0.00')), labels(observation(value='0.0')))['exact']
    assert score_case(labels(observation(value='-1.20')), labels())['missing'] == 1
    assert score_case(labels(), labels(observation()))['extra'] == 1
    failed = score_case(labels(), None, failed=True)
    assert not failed['exact'] and failed['f1'] == 0


def test_duplicates_bad_dates_and_partial_payload_are_invalid():
    for predicted in [labels(observation(), observation()), labels(observation(period_end='2026-02-30')),
                      {'reported_diluted_eps': []}]:
        with pytest.raises(ReviewError):
            score_case(labels(), predicted)


def test_saved_run_is_frozen_complete_and_read_only(reviewed, config, tmp_path):
    import pyarrow.parquet as pq

    source_before = all_hashes(reviewed)
    saved = predictions(reviewed, tmp_path / 'predictions.json')
    manifest, results = runner.run(reviewed, tmp_path / 'run1', config, predictions=saved)
    assert manifest['status'] == 'completed'
    assert results['summary']['exact_cases'] == 2 and results['summary']['correct'] == 4
    assert results['summary']['known_cost_usd'] == '0.002'
    assert results['summary']['cost_complete']
    assert results['summary']['f1'] == 1
    output = tmp_path / 'run1'
    assert load_run(output) == (manifest, results)
    assert all_hashes(reviewed) == source_before
    assert not (reviewed / '.review').exists()
    golden = read_json(output / 'golden.json')
    assert golden['cases'][0]['labels']['reported_diluted_eps'][0]['value'] == '4.60'
    rows = pq.read_table(output / 'observations.parquet').to_pylist()
    assert rows[0]['golden_value'] == rows[0]['predicted_value'] == '4.60'
    assert rows[0]['golden_period_start'] is None
    assert pq.read_table(output / 'cases.parquet').num_rows == 2
    for name in ('cases', 'observations'):
        metadata = read_json(output / f'{name}.metadata.json')
        assert metadata['sha256'] == sha256((output / f'{name}.parquet').read_bytes()).hexdigest()
        assert not metadata['partial']
    assert '100.0%' in (output / 'REPORT.md').read_text()
    # Runs retain exact documents and labels even after external inputs go away.
    for case in load_dataset(reviewed).cases:
        request = read_json(output / 'inputs' / case.case_id / 'request.json')
        assert set(request) == {'schema_version', 'case_id', 'filing', 'documents', 'label_schema', 'prompt', 'model', 'settings'}
        assert 'labels' not in request and 'notes' not in request and str(reviewed) not in json.dumps(request)
        for document in request['documents']:
            raw = (output / 'inputs' / case.case_id / document['path']).read_bytes()
            assert sha256(raw).hexdigest() == document['sha256']


def test_command_receives_label_free_documents_and_retains_raw_response(reviewed, config, tmp_path, monkeypatch):
    monkeypatch.setenv('FINBOT_DATA_ROOT', str(reviewed))
    calls = []

    def execute(command, **kwargs):
        request = json.loads(kwargs['input'])
        assert command == ['/fake/python', '/fake/extract.py']
        assert 'FINBOT_DATA_ROOT' not in kwargs['env']
        assert 'shell' not in kwargs and kwargs['timeout'] == 1
        assert set(request['filing']) == {'filing_id', 'ticker', 'company_name', 'form_type', 'filed_at', 'cik'}
        assert (kwargs['cwd'] / request['documents'][0]['path']).is_file()
        assert not list(kwargs['cwd'].glob('case.json'))
        kwargs['stdout'].write(b'{"labels":{"reported_diluted_eps":[],"adjusted_diluted_eps":[]}}')
        calls.append(request['case_id'])
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(extractor.subprocess, 'run', execute)
    manifest, results = runner.run(reviewed, tmp_path / 'command-run', config)
    assert manifest['mode'] == 'command' and len(calls) == 2
    assert results['summary']['missing'] == 4
    assert results['summary']['extraction_errors'] == 0
    assert not results['summary']['cost_complete']
    assert all((tmp_path / 'command-run/responses' / f'{case_id}.json').exists() for case_id in calls)


def test_command_cannot_silently_change_frozen_documents(reviewed, config, tmp_path, monkeypatch):
    def execute(command, **kwargs):
        request = json.loads(kwargs['input'])
        (kwargs['cwd'] / request['documents'][0]['path']).write_bytes(b'altered')
        kwargs['stdout'].write(b'{"labels":{"reported_diluted_eps":[],"adjusted_diluted_eps":[]}}')
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(extractor.subprocess, 'run', execute)
    before = all_hashes(reviewed)
    with pytest.raises(ReviewError, match='changed frozen'):
        runner.run(reviewed, tmp_path / 'altered-run', config)
    assert all_hashes(reviewed) == before
    assert not (tmp_path / 'altered-run').exists()


def test_saved_predictions_can_be_rescored_without_extraction(reviewed, config, tmp_path):
    path = predictions(reviewed, tmp_path / 'predictions.json')
    _, first = runner.run(reviewed, tmp_path / 'first', config, predictions=path)
    _, second = runner.run(reviewed, tmp_path / 'second', config,
                           predictions=tmp_path / 'first/predictions.json')
    assert first['summary'] == second['summary']
    assert first['cases'] == second['cases']


@pytest.mark.parametrize('failure', ['malformed', 'invalid', 'nonzero', 'timeout', 'unavailable', 'oversized'])
def test_failed_outputs_are_scored_and_retained(reviewed, config, tmp_path, monkeypatch, failure):
    def execute(command, **kwargs):
        if failure == 'timeout':
            raise subprocess.TimeoutExpired(command, 1)
        if failure == 'unavailable':
            raise FileNotFoundError(2, 'missing')
        raw = b'not JSON' if failure == 'malformed' else b'{"labels":{}}'
        if failure == 'oversized':
            raw = b'x' * (extractor.MAX_RESPONSE + 1)
        kwargs['stdout'].write(raw)
        return subprocess.CompletedProcess(command, 3 if failure == 'nonzero' else 0)

    monkeypatch.setattr(extractor.subprocess, 'run', execute)
    output = tmp_path / failure
    manifest, results = runner.run(reviewed, output, config)
    assert manifest['status'] == 'completed_with_errors'
    assert results['summary']['extraction_errors'] == 2
    assert results['summary']['missing'] == 4
    assert results['summary']['exact_cases'] == 0
    assert read_json(output / 'cases.metadata.json')['partial']
    load_run(output)
    assert all(p.stat().st_size <= extractor.MAX_RESPONSE for p in (output / 'responses').iterdir())


def test_unreviewed_pending_and_corrupt_inputs_are_refused(writable_dataset, reviewed, config, tmp_path):
    # writable_dataset and reviewed refer to the same fixture; explicitly invalidate one case.
    case = load_dataset(reviewed).cases[0]
    record = case.to_dict()
    record['review'].update(status='unreviewed', reviewed_at_utc=None)
    save_json(case.path, record)
    prepare_bundle(reviewed)
    with pytest.raises(ReviewError, match='every filing'):
        runner.run(reviewed, tmp_path / 'unreviewed', config)
    record['review'].update(status='human_reviewed', reviewed_at_utc='2026-10-22T00:00:00Z')
    save_json(case.path, record)
    prepare_bundle(reviewed)
    (reviewed / '.review').mkdir()
    (reviewed / '.review/pending.json').write_text('{}')
    with pytest.raises(ReviewError, match='synchronization'):
        runner.run(reviewed, tmp_path / 'pending', config)
    (reviewed / '.review/pending.json').unlink()
    (reviewed / 'labels.json').write_text('[]')
    with pytest.raises(ReviewError, match='integrity'):
        runner.run(reviewed, tmp_path / 'corrupt', config)
    assert not any((tmp_path / name).exists() for name in ('unreviewed', 'pending', 'corrupt'))


def test_changed_inputs_during_freeze_are_refused(reviewed, config, tmp_path, monkeypatch):
    real_load = runner.load_dataset
    count = 0

    def load(path):
        nonlocal count
        count += 1
        if count == 2:
            case = real_load(path).cases[0]
            record = case.to_dict()
            record['labels']['reported_diluted_eps'][0]['value'] = '8.00'
            save_json(case.path, record)
            prepare_bundle(path)
        return real_load(path)

    monkeypatch.setattr(runner, 'load_dataset', load)
    with pytest.raises(ReviewError, match='changed while freezing'):
        runner.run(reviewed, tmp_path / 'changed', config)
    assert not (tmp_path / 'changed').exists()


def test_output_paths_cannot_overwrite_source_or_runs(reviewed, config, tmp_path):
    for output in (reviewed / 'runs/one', reviewed.parent, reviewed):
        with pytest.raises(ReviewError, match='separate'):
            runner.run(reviewed, output, config)
    output = tmp_path / 'existing'
    output.mkdir()
    with pytest.raises(ReviewError, match='already exists'):
        runner.run(reviewed, output, config)
    assert list(output.iterdir()) == []


def test_prediction_case_membership_and_duplicate_keys_are_refused(reviewed, config, tmp_path):
    path = predictions(reviewed, tmp_path / 'predictions.json')
    value = read_json(path)
    value.pop(next(iter(value)))
    save_json(path, value)
    with pytest.raises(ReviewError, match='every dataset case_id'):
        runner.run(reviewed, tmp_path / 'omitted', config, predictions=path)
    path.write_text('{"duplicate":{},"duplicate":{}}')
    with pytest.raises(ReviewError, match='duplicate JSON key'):
        runner.run(reviewed, tmp_path / 'duplicate', config, predictions=path)


@pytest.mark.parametrize('cost', [1.0, '-0.01', 'NaN', 'Infinity', 'invalid'])
def test_invalid_cost_is_not_reported_as_zero(cost):
    with pytest.raises(ReviewError, match='cost_usd'):
        extractor.response({'labels': labels(), 'cost_usd': cost})


def test_comparison_reports_regressions_and_refuses_incompatible_or_modified_runs(reviewed, config, tmp_path):
    path = predictions(reviewed, tmp_path / 'predictions.json')
    runner.run(reviewed, tmp_path / 'baseline', config, predictions=path)
    saved = read_json(path)
    case_id = next(iter(saved))
    saved[case_id]['labels']['reported_diluted_eps'][0]['value'] = '5.25'
    save_json(path, saved)
    runner.run(reviewed, tmp_path / 'candidate', config, predictions=path)
    text = compare(tmp_path / 'baseline', tmp_path / 'candidate')
    assert 'regressed' in text and case_id in text and '100.0%' in text
    case = load_dataset(reviewed).cases[0]
    record = case.to_dict()
    record['labels']['reported_diluted_eps'][0]['value'] = '5.25'
    save_json(case.path, record)
    prepare_bundle(reviewed)
    runner.run(reviewed, tmp_path / 'different-gold', config, predictions=path)
    with pytest.raises(ReviewError, match='same frozen dataset'):
        compare(tmp_path / 'baseline', tmp_path / 'different-gold')
    (tmp_path / 'candidate/results.json').write_text('{}')
    with pytest.raises(ReviewError, match='integrity'):
        compare(tmp_path / 'baseline', tmp_path / 'candidate')


def test_cli_exit_codes_defaults_and_comparison(reviewed, config, tmp_path, monkeypatch, capsys):
    saved = predictions(reviewed, tmp_path / 'predictions.json')
    arguments = ['run', '--dataset-root', str(reviewed), '--config', str(config), '--predictions', str(saved)]
    monkeypatch.delenv('FINBOT_DATA_ROOT', raising=False)
    assert main(arguments) == 2
    monkeypatch.setenv('FINBOT_DATA_ROOT', str(tmp_path / 'shared'))
    assert main(arguments) == 0
    root = next((tmp_path / 'shared/filing-evals/runs').iterdir())
    assert main(['compare', str(root), str(root)]) == 0
    assert 'unchanged' in capsys.readouterr().out
    value = read_json(saved)
    value[next(iter(value))] = {'labels': {}}
    save_json(saved, value)
    assert main(arguments + ['--output', str(tmp_path / 'failed-output')]) == 1


def test_all_empty_cases_and_failed_empty_filing(reviewed, config, tmp_path):
    import pyarrow.parquet as pq

    for case in load_dataset(reviewed).cases:
        record = case.to_dict()
        record['labels'] = labels()
        save_json(case.path, record)
    # Update counts before reloading fixtures to regenerate exports.
    manifest = read_json(reviewed / 'dataset.json')
    manifest['observation_count'] = 0
    save_json(reviewed / 'dataset.json', manifest)
    prepare_bundle(reviewed)
    saved = predictions(reviewed, tmp_path / 'empty-predictions.json')
    _, results = runner.run(reviewed, tmp_path / 'empty', config, predictions=saved)
    assert results['summary']['f1'] == 1 and results['summary']['exact_cases'] == 2
    table = pq.read_table(tmp_path / 'empty/observations.parquet')
    assert table.num_rows == 0 and table.schema.field('golden_value').type.__str__() == 'string'
    value = read_json(saved)
    value[next(iter(value))] = {'labels': {}}
    save_json(saved, value)
    _, results = runner.run(reviewed, tmp_path / 'empty-error', config, predictions=saved)
    assert results['summary']['f1'] == 0
    assert results['summary']['exact_cases'] == 1


@pytest.mark.parametrize('changes', [dict(timeout_seconds=0), dict(timeout_seconds=True),
                                    dict(command='python extract.py'), dict(model=''), dict(settings=[]),
                                    dict(prompt_file=''), dict(secret='forbidden')])
def test_bad_config_is_refused(config, changes):
    save_json(config, read_json(config) | changes)
    with pytest.raises(ReviewError):
        extractor.load_config(config)
