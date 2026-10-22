"""Offline request and comparison checks for the alternative-model experiments."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import save_json
from finbot_filing_evals.evaluation import bedrock, runner
from finbot_filing_evals.evaluation.contracts import FISCAL_CONTRACT, load_schema, project_labels
from finbot_filing_evals.evaluation.extractor import load_config, response
from finbot_filing_evals.evaluation.files import digest
from finbot_filing_evals.evaluation.reports import compare
from finbot_filing_evals.review.dataset import load_dataset

pytest.importorskip('boto3')
pytest.importorskip('PIL')

from test_evaluation import reviewed, all_hashes
from test_evaluation_bedrock import image_request


ROOT = Path(__file__).parents[1]
MODELS = (
    ('claude-sonnet-4-6', 'us.anthropic.claude-sonnet-4-6', 'tool'),
    ('kimi-k3', 'us.moonshotai.kimi-k3', 'text'),
    ('mistral-large-3', 'mistral.mistral-large-3-675b-instruct', 'text'),
    ('qwen3-vl-235b', 'qwen.qwen3-vl-235b-a22b', 'text'),
)


def config_path(name):
    return ROOT / 'configs' / f'bedrock-{name}-prompt-v4.json'


def native_response(payload, mode):
    content = ([{'toolUse': {'name': 'submit_eps', 'toolUseId': 'synthetic', 'input': payload}}]
               if mode == 'tool' else [{'text': json.dumps(payload)}])
    return dict(stopReason='tool_use' if mode == 'tool' else 'end_turn',
                output={'message': {'role': 'assistant', 'content': content}},
                usage={'inputTokens': 1000, 'outputTokens': 100, 'totalTokens': 1100})


@pytest.mark.parametrize('name,model,mode', MODELS)
def test_alternative_model_sends_v4_text_and_original_images(tmp_path, name, model, mode):
    config, prompt = load_config(config_path(name))
    _, baseline_prompt = load_config(ROOT / 'configs/bedrock-nova-2-lite-prompt-v4.json')
    assert prompt == baseline_prompt
    assert config['label_contract'] == FISCAL_CONTRACT
    request = image_request(tmp_path)
    html = b'<p>Diluted EPS: 4.60</p><script>forbidden()</script>'
    (tmp_path / 'release.htm').write_bytes(html)
    request['documents'].insert(0, dict(path='release.htm', filename='release.htm',
                                       sha256=digest(html), content_type='text/html'))
    request.update(prompt=prompt, label_schema=load_schema(FISCAL_CONTRACT))
    save_json(tmp_path / 'request.json', request)
    payload = dict(reported_diluted_eps=[dict(value='4.60', currency='USD',
                   period_type='quarterly', fiscal_year=2026, fiscal_quarter=3)],
                   adjusted_diluted_eps=[])
    calls = []

    def converse(**params):
        calls.append(params)
        assert params['modelId'] == model
        assert params['inferenceConfig'] == {'maxTokens': 4096}
        assert params['system'][0]['text'].startswith(baseline_prompt)
        blocks = params['messages'][0]['content']
        text = '\n'.join(block['text'] for block in blocks if 'text' in block)
        assert 'Diluted EPS: 4.60' in text and 'forbidden()' not in text
        assert next(block['image']['source']['bytes'] for block in blocks if 'image' in block) == (tmp_path / 'page0.jpg').read_bytes()
        if mode == 'tool':
            assert params['toolConfig']['toolChoice'] == {'tool': {'name': 'submit_eps'}}
            assert params['toolConfig']['tools'][0]['toolSpec']['inputSchema']['json'] == load_schema(FISCAL_CONTRACT)
        else:
            assert 'toolConfig' not in params
        return native_response(payload, mode)

    adapter = bedrock.BedrockExtractor.__new__(bedrock.BedrockExtractor)
    adapter.config, adapter.client = config, SimpleNamespace(converse=converse)
    raw, _, error = adapter.invoke(tmp_path / 'request.json', tmp_path, tmp_path / 'response.json')
    assert error is None and len(calls) == 1
    normalized, cost, usage = response(json.loads(raw), contract=FISCAL_CONTRACT)
    assert normalized == payload and usage['inputTokens'] == 1000
    assert (cost is not None) == (name == 'kimi-k3')
    assert (tmp_path / 'release.htm').read_bytes() == html


def test_alternative_runs_preserve_targets_and_compare_with_nova(reviewed, tmp_path, monkeypatch):
    targets = {case.ticker: project_labels(case.to_dict()['labels'])[0]
               for case in load_dataset(reviewed).cases}
    before = all_hashes(reviewed)

    def client(config):
        def converse(**params):
            context = json.loads(params['messages'][0]['content'][0]['text'].removeprefix('Filing context: '))
            return native_response(targets[context['ticker']], config['settings']['output_mode'])
        return SimpleNamespace(converse=converse)

    monkeypatch.setattr(bedrock, 'make_client', client)
    baseline = tmp_path / 'nova'
    runner.run(reviewed, baseline, ROOT / 'configs/bedrock-nova-2-lite-prompt-v4.json')
    for name, model, _ in MODELS:
        output = tmp_path / name
        manifest, results = runner.run(reviewed, output, config_path(name))
        assert manifest['extractor']['model'] == model
        assert results['summary']['exact_cases'] == 2
        assert results['summary']['extraction_errors'] == 0
        assert (output / 'prompt.txt').read_text() == (baseline / 'prompt.txt').read_text()
        assert 'unchanged' in compare(baseline, output)
        assert results['summary']['cost_complete'] == (name == 'kimi-k3')
    assert all_hashes(reviewed) == before
