from copy import deepcopy
from decimal import Decimal
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import save_json
from finbot_filing_evals.evaluation import bedrock, runner
from finbot_filing_evals.evaluation.extractor import load_config
from finbot_filing_evals.evaluation.files import digest, read_json
from finbot_filing_evals.evaluation.contracts import FISCAL_CONTRACT, load_schema, project_labels
from finbot_filing_evals.review.errors import ReviewError

pytest.importorskip('boto3')
pytest.importorskip('PIL')

# Reuse complete synthetic evaluation fixtures without depending on shared data.
from test_evaluation import reviewed, config, labels, observation, predictions, all_hashes


@pytest.fixture
def bedrock_config(config):
    value = read_json(config)
    value.pop('command')
    value.update(provider='bedrock', region='us-east-1', model='us.openai.gpt-6-luna',
                 settings={'max_output_tokens': 4096}, pricing=read_json(
                     Path(__file__).parents[1] / 'configs/bedrock-luna.json')['pricing'])
    save_json(config, value)
    return config


def native_response(payload=None, **changes):
    import json
    return dict(output={'message': {'role': 'assistant', 'content': [{'text': json.dumps(payload or labels())}]}},
                usage={'inputTokens': 1000, 'outputTokens': 100, 'totalTokens': 1100},
                stopReason='end_turn', metrics={'latencyMs': 20}, **changes)


def test_bedrock_run_reuses_client_has_bounded_tokens_and_no_labels(reviewed, bedrock_config, tmp_path, monkeypatch):
    calls = []
    clients = []

    def converse(**request):
        assert request['modelId'] == 'us.openai.gpt-6-luna'
        assert request['inferenceConfig'] == {'maxTokens': 4096}
        assert request['messages'][0]['role'] == 'user'
        text = '\n'.join(block['text'] for block in request['messages'][0]['content'] if 'text' in block)
        assert 'Diluted EPS: 4.60' in text
        assert 'Review note' not in text and str(reviewed) not in text
        assert '<script>' not in text and 'window.forbidden' not in text
        assert 'Required JSON schema' in request['system'][0]['text']
        calls.append(request)
        return native_response()

    def client(config):
        clients.append(config)
        return SimpleNamespace(converse=converse)

    monkeypatch.setattr(bedrock, 'make_client', client)
    before = all_hashes(reviewed)
    manifest, results = runner.run(reviewed, tmp_path / 'bedrock-run', bedrock_config)
    assert manifest['mode'] == 'bedrock'
    assert len(clients) == 1 and len(calls) == 2
    assert results['summary']['missing'] == 4
    assert results['summary']['extraction_errors'] == 0
    assert Decimal(results['summary']['known_cost_usd']) == Decimal('0.00033')
    assert results['summary']['cost_complete']
    assert len(list((tmp_path / 'bedrock-run/responses').glob('*.provider.json'))) == 2
    assert all_hashes(reviewed) == before


@pytest.mark.parametrize('failure', ['access', 'credentials', 'truncated', 'refusal', 'invalid_json', 'invalid_schema', 'fenced_json'])
def test_provider_failures_remain_visible_and_billed_usage_survives(reviewed, bedrock_config, tmp_path, monkeypatch, failure):
    from botocore.exceptions import ClientError, NoCredentialsError

    def converse(**kwargs):
        if failure == 'access':
            raise ClientError({'Error': {'Code': 'AccessDeniedException', 'Message': 'DO_NOT_LOG_SECRET'}}, 'Converse')
        if failure == 'credentials':
            raise NoCredentialsError()
        result = native_response()
        if failure == 'truncated':
            result['stopReason'] = 'max_tokens'
        elif failure == 'refusal':
            result['stopReason'] = 'content_filtered'
        elif failure == 'invalid_json':
            result['output']['message']['content'] = [{'text': 'not JSON'}]
        elif failure == 'invalid_schema':
            result['output']['message']['content'] = [{'text': '{}'}]
        elif failure == 'fenced_json':
            result['output']['message']['content'][0]['text'] = '```json\n' + json.dumps(labels()) + '\n```'
        return result

    monkeypatch.setattr(bedrock, 'make_client', lambda config: SimpleNamespace(converse=converse))
    output = tmp_path / failure
    _, results = runner.run(reviewed, output, bedrock_config)
    assert results['summary']['extraction_errors'] == 2
    assert results['summary']['missing'] == 4
    assert results['summary']['cost_complete'] == (failure not in {'access', 'credentials'})
    assert 'DO_NOT_LOG_SECRET' not in (output / 'results.json').read_text()


def test_saved_bedrock_predictions_never_construct_a_client(reviewed, bedrock_config, tmp_path, monkeypatch):
    def forbidden(*args):
        raise AssertionError('Scoring must not initialize AWS')
    monkeypatch.setattr(bedrock, 'make_client', forbidden)
    path = predictions(reviewed, tmp_path / 'predictions.json')
    _, result = runner.run(reviewed, tmp_path / 'replayed', bedrock_config, predictions=path)
    assert result['summary']['exact_cases'] == 2


def test_sdk_uses_credentials_chain_region_timeouts_and_retry_configuration(bedrock_config, monkeypatch):
    import boto3

    calls = {}
    def session(**kwargs):
        calls['session'] = kwargs
        def client(service, **kwargs):
            calls['service'] = service
            calls['config'] = kwargs['config']
            return 'fake-client'
        return SimpleNamespace(client=client)
    monkeypatch.setattr(boto3, 'Session', session)
    config, _ = load_config(bedrock_config)
    assert bedrock.make_client(config) == 'fake-client'
    assert calls['session'] == {'profile_name': None, 'region_name': 'us-east-1'}
    assert calls['service'] == 'bedrock-runtime'
    assert calls['config'].retries == {'total_max_attempts': 2, 'mode': 'adaptive'}
    assert calls['config'].read_timeout == 1


def image_request(tmp_path, *, count=1, raw=None):
    from PIL import Image
    if raw is None:
        buffer = BytesIO()
        Image.new('RGB', (20, 20), 'white').save(buffer, format='JPEG')
        raw = buffer.getvalue()
    documents = []
    for index in range(count):
        path = tmp_path / f'page{index}.jpg'
        path.write_bytes(raw)
        documents.append(dict(path=path.name, filename=path.name, sha256=digest(raw), content_type='image/jpeg'))
    return dict(filing={'ticker': 'SYNTHETIC'}, documents=documents)


def test_original_verified_images_are_sent_without_network_or_reencoding(tmp_path):
    request = image_request(tmp_path)
    blocks = bedrock.content_blocks(request, tmp_path)
    image = next(block['image'] for block in blocks if 'image' in block)
    assert image['format'] == 'jpeg'
    assert image['source']['bytes'] == (tmp_path / 'page0.jpg').read_bytes()
    assert 'Source attachment: page0.jpg' in [block.get('text') for block in blocks]


@pytest.mark.parametrize('failure', ['too_many', 'too_large', 'corrupt', 'hash', 'path', 'unsupported', 'dimensions'])
def test_unusable_source_assets_are_refused_without_truncation(tmp_path, failure):
    if failure == 'dimensions':
        from PIL import Image
        buffer = BytesIO()
        Image.new('RGB', (8001, 1), 'white').save(buffer, format='JPEG')
        request = image_request(tmp_path, raw=buffer.getvalue())
    else:
        raw = b'x' * 3_750_001 if failure == 'too_large' else b'not image' if failure == 'corrupt' else None
        request = image_request(tmp_path, count=21 if failure == 'too_many' else 1, raw=raw)
    doc = request['documents'][0]
    if failure == 'hash':
        doc['sha256'] = '0' * 64
    elif failure == 'path':
        doc['path'] = '../outside.jpg'
    elif failure == 'unsupported':
        doc['content_type'] = 'application/pdf'
    with pytest.raises(ReviewError):
        bedrock.content_blocks(request, tmp_path)


def test_price_estimation_accounts_for_cache_and_long_context(bedrock_config):
    config, _ = load_config(bedrock_config)
    prices = config['pricing']
    assert bedrock.estimate_cost({'inputTokens': 1000, 'outputTokens': 100}, prices) == '0.000165'
    assert Decimal(bedrock.estimate_cost({'inputTokens': 1_000_000, 'outputTokens': 1_000_000}, prices)) == Decimal('1.045')
    assert bedrock.estimate_cost({'inputTokens': 0, 'outputTokens': 0, 'cacheReadInputTokens': 1000,
                                  'cacheWriteInputTokens': 1000}, prices) == '0.0001485'
    assert bedrock.estimate_cost({}, prices) is None
    assert bedrock.estimate_cost({'inputTokens': -1, 'outputTokens': 0}, prices) is None
    assert bedrock.estimate_cost({'inputTokens': 1000, 'outputTokens': 100}, None) is None


@pytest.mark.parametrize('changes', [dict(region=''), dict(command=['oops']), dict(aws_profile=''),
                                    dict(settings={'max_output_tokens': True}), dict(settings={'temperature': 0}),
                                    dict(pricing={})])
def test_provider_configuration_is_validated(bedrock_config, changes):
    save_json(bedrock_config, read_json(bedrock_config) | changes)
    with pytest.raises(ReviewError):
        load_config(bedrock_config)


def test_sdk_request_matches_official_boto3_schema(bedrock_config, tmp_path):
    """Stubber checks the SDK request and response shapes, with no AWS access."""
    import boto3
    from botocore.stub import Stubber

    config, prompt = load_config(bedrock_config)
    request = image_request(tmp_path)
    request.update(prompt=prompt, label_schema={'type': 'object'})
    save_json(tmp_path / 'request.json', request)
    client = boto3.client('bedrock-runtime', region_name='us-east-1',
                          aws_access_key_id='synthetic', aws_secret_access_key='synthetic')
    adapter = bedrock.BedrockExtractor.__new__(bedrock.BedrockExtractor)
    adapter.config, adapter.client = config, client
    with Stubber(client) as stub:
        stub.add_response('converse', native_response())
        raw, duration, error = adapter.invoke(tmp_path / 'request.json', tmp_path, tmp_path / 'response.json')
        assert error is None and duration >= 0
        stub.assert_no_pending_responses()


def test_nova_config_retains_shared_prompt_and_uses_its_own_rates():
    from finbot_filing_evals.evaluation.scoring import policy_for

    root = Path(__file__).parents[1]
    nova, prompt = load_config(root / 'configs/bedrock-nova-2-lite.json')
    luna, luna_prompt = load_config(root / 'configs/bedrock-luna.json')
    assert nova['provider'] == luna['provider'] == 'bedrock'
    assert nova['model'] == 'us.amazon.nova-2-lite-v1:0'
    assert luna['model'] == 'us.openai.gpt-6-luna'
    assert nova['region'] == luna['region'] == 'us-east-1'
    assert nova['settings'] == {'max_output_tokens': 4096, 'output_mode': 'tool'}
    assert luna['settings'] == {'max_output_tokens': 4096}
    assert nova['name'] != luna['name']
    assert prompt == luna_prompt
    assert nova['label_contract'] == luna['label_contract'] == FISCAL_CONTRACT
    assert policy_for(FISCAL_CONTRACT)['version'] == 'eps_fiscal_exact.v2'
    assert Decimal(bedrock.estimate_cost({'inputTokens': 1000, 'outputTokens': 100}, nova['pricing'])) == Decimal('0.000605')
    # Nova's rate table must not inherit Luna's long-context surcharge.
    assert Decimal(bedrock.estimate_cost({'inputTokens': 300000, 'outputTokens': 100}, nova['pricing'])) == Decimal('0.099275')
    assert Decimal(bedrock.estimate_cost({'inputTokens': 1000, 'outputTokens': 0,
                                        'cacheReadInputTokens': 1000, 'cacheWriteInputTokens': 1000}, nova['pricing'])) == Decimal('0.0004125')


@pytest.mark.parametrize('html_input', ['plain_text', 'raw_html', 'cleaned_html'])
def test_nova_text_and_image_request_with_official_sdk_stubber(tmp_path, html_input):
    import boto3
    from botocore.stub import Stubber
    from finbot_filing_evals.evaluation.extractor import response

    config, prompt = load_config(Path(__file__).parents[1] / 'configs/bedrock-nova-2-lite.json')
    config['html_input'] = html_input
    request = image_request(tmp_path)
    html = b'<html><body><table><tr><td>Diluted EPS</td><td>4.60</td></tr></table></body></html>'
    (tmp_path / 'release.htm').write_bytes(html)
    request['documents'].insert(0, dict(path='release.htm', filename='release.htm',
                                       sha256=digest(html), content_type='text/html'))
    request.update(prompt=prompt, label_schema=load_schema(FISCAL_CONTRACT))
    save_json(tmp_path / 'request.json', request)
    expected = dict(
        modelId='us.amazon.nova-2-lite-v1:0',
        system=[{'text': prompt + '\n\nRequired JSON schema:\n' + json.dumps(load_schema(FISCAL_CONTRACT))
                        + '\n\nSubmit the EPS payload as the input to submit_eps. Call it exactly once; do not return a text response.'}],
        messages=[{'role': 'user', 'content': bedrock.content_blocks(request, tmp_path, html_input=html_input)}],
        inferenceConfig={'maxTokens': 4096},
        toolConfig={
            'tools': [{'toolSpec': {'name': 'submit_eps',
                       'description': 'Submit the reported and adjusted diluted EPS observations from this filing package.',
                       'inputSchema': {'json': load_schema(FISCAL_CONTRACT)}}}],
            'toolChoice': {'tool': {'name': 'submit_eps'}},
        },
    )
    client = boto3.client('bedrock-runtime', region_name='us-east-1',
                          aws_access_key_id='synthetic', aws_secret_access_key='synthetic')
    adapter = bedrock.BedrockExtractor.__new__(bedrock.BedrockExtractor)
    adapter.config, adapter.client = config, client
    payload, _ = project_labels(labels(observation()))
    result = native_response()
    result['stopReason'] = 'tool_use'
    result['output']['message']['content'] = [{'toolUse': {'toolUseId': 'synthetic-call', 'name': 'submit_eps', 'input': payload}}]
    with Stubber(client) as stub:
        stub.add_response('converse', result, expected)
        raw, _, error = adapter.invoke(tmp_path / 'request.json', tmp_path, tmp_path / 'response.json')
        assert error is None
        normalized, cost, usage = response(json.loads(raw), contract=FISCAL_CONTRACT)
        assert normalized == payload
        assert Decimal(cost) == Decimal('0.000605')
        assert usage['inputTokens'] == 1000
        stub.assert_no_pending_responses()


def test_nova_saved_predictions_use_the_existing_scoring_and_report_pipeline(reviewed, tmp_path):
    config = Path(__file__).parents[1] / 'configs/bedrock-nova-2-lite.json'
    path = predictions(reviewed, tmp_path / 'predictions.json')
    records = read_json(path)
    for record in records.values():
        record['labels'], _ = project_labels(record['labels'])
    save_json(path, dict(schema_version='eps_predictions.v2', label_contract=FISCAL_CONTRACT, cases=records))
    before = all_hashes(reviewed)
    manifest, results = runner.run(reviewed, tmp_path / 'nova', config, predictions=path)
    assert manifest['extractor']['model'] == 'us.amazon.nova-2-lite-v1:0'
    assert results['summary']['exact_cases'] == 2
    assert results['summary']['extraction_errors'] == 0
    assert 'nova-2-lite-bedrock-baseline-v2' in (tmp_path / 'nova/REPORT.md').read_text()
    assert all_hashes(reviewed) == before


@pytest.mark.parametrize('failure', ['text_only', 'wrong_tool', 'multiple_tools', 'missing_input', 'invalid_labels', 'truncated'])
def test_nova_tool_output_still_requires_valid_eps(reviewed, tmp_path, monkeypatch, failure):
    config = Path(__file__).parents[1] / 'configs/bedrock-nova-2-lite.json'

    def converse(**parameters):
        assert parameters['toolConfig']['toolChoice'] == {'tool': {'name': 'submit_eps'}}
        result = native_response()
        result['stopReason'] = 'tool_use'
        tool = {'name': 'submit_eps', 'toolUseId': 'synthetic-call', 'input': labels()}
        result['output']['message']['content'] = [{'toolUse': tool}]
        if failure == 'text_only':
            result['stopReason'] = 'end_turn'
            result['output']['message']['content'] = [{'text': json.dumps(labels())}]
        elif failure == 'wrong_tool':
            tool['name'] = 'unexpected'
        elif failure == 'multiple_tools':
            result['output']['message']['content'].append({'toolUse': dict(tool)})
        elif failure == 'missing_input':
            tool.pop('input')
        elif failure == 'invalid_labels':
            tool['input'] = labels(observation(value=4.60))
        elif failure == 'truncated':
            result['stopReason'] = 'max_tokens'
        return result

    monkeypatch.setattr(bedrock, 'make_client', lambda config: SimpleNamespace(converse=converse))
    _, results = runner.run(reviewed, tmp_path / failure, config)
    assert results['summary']['extraction_errors'] == 2
    assert results['summary']['missing'] == 3
    assert results['summary']['cost_complete']
    assert all(case['prediction'] is None for case in results['cases'])


@pytest.mark.parametrize('mode', ['unexpected', [], None])
def test_invalid_output_modes_are_configuration_errors(bedrock_config, mode):
    config = read_json(bedrock_config)
    config['settings']['output_mode'] = mode
    save_json(bedrock_config, config)
    with pytest.raises(ReviewError, match='output_mode'):
        load_config(bedrock_config)
