"""Real SDK serialization against synthetic HTTP transports, never provider APIs."""

from base64 import b64decode
from copy import deepcopy
from decimal import Decimal
from importlib import import_module
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest

from conftest import save_json
from finbot_filing_evals.evaluation import direct, runner
from finbot_filing_evals.evaluation.bedrock import estimate_cost
from finbot_filing_evals.evaluation.contracts import FISCAL_CONTRACT, load_schema, project_labels, validate_labels
from finbot_filing_evals.evaluation.extractor import load_config
from finbot_filing_evals.evaluation.files import digest, load_run, read_json
from finbot_filing_evals.evaluation.reports import compare
from finbot_filing_evals.review.dataset import load_dataset
from finbot_filing_evals.review.errors import ReviewError

from test_evaluation import reviewed, all_hashes

pytest.importorskip('openai')
pytest.importorskip('anthropic')
pytest.importorskip('PIL')

ROOT = Path(__file__).parents[1]
CONFIGS = {'openai': 'openai-luna-6-prompt-v4.json', 'anthropic': 'anthropic-haiku-5-5-prompt-v4.json'}


def config_for(provider):
    return load_config(ROOT / 'configs' / CONFIGS[provider])[0]


def payload():
    return dict(reported_diluted_eps=[dict(value='-4.60', currency='USD', period_type='quarterly',
                                         fiscal_year=2026, fiscal_quarter=3)], adjusted_diluted_eps=[])


def native(provider, labels=None):
    text = json.dumps(payload() if labels is None else labels)
    if provider == 'openai':
        return dict(id='resp_synthetic', object='response', created_at=1, status='completed',
                    error=None, incomplete_details=None, model='gpt-6-luna',
                    output=[{'type': 'reasoning', 'id': 'rs_synthetic', 'summary': []},
                            {'type': 'message', 'id': 'msg_synthetic', 'role': 'assistant', 'status': 'completed',
                             'content': [{'type': 'output_text', 'text': text, 'annotations': []}]}],
                    usage={'input_tokens': 1000, 'output_tokens': 100, 'total_tokens': 1100,
                           'input_tokens_details': {'cached_tokens': 100, 'cache_write_tokens': 200},
                           'output_tokens_details': {'reasoning_tokens': 50}})
    return dict(id='msg_synthetic', type='message', role='assistant', model='claude-haiku-5-5',
                content=[{'type': 'thinking', 'thinking': '', 'signature': 'synthetic'}, {'type': 'text', 'text': text}],
                stop_reason='end_turn', stop_sequence=None,
                usage={'input_tokens': 700, 'output_tokens': 100,
                       'cache_read_input_tokens': 100, 'cache_creation_input_tokens': 200,
                       'cache_creation': {'ephemeral_5m_input_tokens': 200, 'ephemeral_1h_input_tokens': 0},
                       'output_tokens_details': {'thinking_tokens': 50}})


def sdk_client(provider, handler):
    sdk = import_module(provider)
    http = import_module('httpx' if provider == 'openai' else 'httpx2')
    def transport(request):
        status, body = handler(request)
        return http.Response(status, json=body)
    client = http.Client(transport=http.MockTransport(transport))
    return (sdk.OpenAI if provider == 'openai' else sdk.Anthropic)(
        api_key='synthetic-key', base_url=direct.ENDPOINTS[provider], http_client=client,
        timeout=1, max_retries=0)


def frozen_request(tmp_path, provider):
    from PIL import Image
    buffer = BytesIO()
    Image.new('RGB', (20, 20), 'white').save(buffer, format='JPEG')
    images = buffer.getvalue()
    html = b'<table><tr><td>Diluted EPS</td><td>-4.60</td></tr></table><script>forbidden()</script>'
    docs = []
    for filename, raw, mime in [('release.htm', html, 'text/html'), ('page.jpg', images, 'image/jpeg')]:
        (tmp_path / filename).write_bytes(raw)
        docs.append(dict(path=filename, filename=filename, sha256=digest(raw), content_type=mime))
    config, prompt = load_config(ROOT / 'configs' / CONFIGS[provider])
    schema = load_schema(FISCAL_CONTRACT)
    request = dict(filing={'ticker': 'SYNTHETIC'}, documents=docs, prompt=prompt, label_schema=schema,
                   output_schema=direct.output_schema(schema, provider))
    path = tmp_path / 'request.json'
    save_json(path, request)
    return path, images


@pytest.mark.parametrize('provider', CONFIGS)
def test_actual_sdk_sends_verified_text_images_and_native_schema(tmp_path, monkeypatch, provider):
    request_path, image = frozen_request(tmp_path, provider)
    calls = []
    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        assert str(request.url) == direct.ENDPOINTS[provider] + ('/responses' if provider == 'openai' else '/v1/messages')
        field = 'input' if provider == 'openai' else 'messages'
        blocks = body[field][0]['content']
        text = '\n'.join(b['text'] for b in blocks if 'text' in b)
        assert '-4.60' in text and 'forbidden()' not in text
        assert 'review' not in text.lower() and str(tmp_path) not in text
        if provider == 'openai':
            assert body['model'] == 'gpt-6-luna' and body['max_output_tokens'] == 4096
            assert body['store'] is False and body['truncation'] == 'disabled'
            assert body['reasoning'] == {'effort': 'medium'} and body['service_tier'] == 'default'
            assert body['prompt_cache_options'] == {'mode': 'implicit', 'ttl': '30m'}
            assert body['text']['format']['strict'] is True
            sent_schema = body['text']['format']['schema']
            raw = next(b['image_url'] for b in blocks if b['type'] == 'input_image').split(',', 1)[1]
        else:
            assert body['model'] == 'claude-haiku-5-5' and body['max_tokens'] == 4096
            assert body['thinking'] == {'type': 'adaptive'}
            assert body['output_config']['effort'] == 'medium'
            assert body['service_tier'] == 'standard_only' and body['inference_geo'] == 'global'
            assert 'speed' not in body  # Haiku 5.5 rejects even speed="standard".
            sent_schema = body['output_config']['format']['schema']
            raw = next(b['source']['data'] for b in blocks if b['type'] == 'image')
        assert sent_schema == read_json(request_path)['output_schema']
        assert b64decode(raw) == image
        return 200, native(provider)
    client = sdk_client(provider, handler)
    monkeypatch.setattr(direct, 'make_client', lambda _: client)
    adapter = direct.DirectExtractor(config_for(provider))
    try:
        raw, _, error = adapter.invoke(request_path, tmp_path, tmp_path / 'response.json')
    finally:
        adapter.close()
    assert error is None and len(calls) == 1
    result = json.loads(raw)
    assert result['labels'] == payload()
    assert result['usage']['inputTokens'] == 700
    assert result['usage']['outputTokens'] == 100  # Includes the 50 reasoning tokens, once.
    assert result['usage']['cacheReadInputTokens'] == 100
    assert result['usage']['cacheWriteInputTokens'] == 200
    assert Decimal(result['cost_usd']) == Decimal('0.000146')
    assert (tmp_path / 'response.provider.json').is_file()
    assert 'synthetic-key' not in (tmp_path / 'response.provider.json').read_text()


@pytest.mark.parametrize('provider', CONFIGS)
def test_schema_compilation_preserves_period_rules_and_local_validation(provider):
    original = load_schema(FISCAL_CONTRACT)
    before = deepcopy(original)
    schema = direct.output_schema(original, provider)
    jsonschema.Draft202012Validator.check_schema(schema)
    assert original == before
    jsonschema.validate(payload(), schema)
    annual = payload()
    annual['reported_diluted_eps'][0].update(period_type='annual', fiscal_quarter=None)
    jsonschema.validate(annual, schema)
    for period, quarter in [('annual', 4), ('quarterly', None), ('quarterly', 9)]:
        invalid = payload()
        invalid['reported_diluted_eps'][0].update(period_type=period, fiscal_quarter=quarter)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)
    invalid = payload()
    invalid['reported_diluted_eps'][0]['fiscal_year'] = 999
    with pytest.raises(ReviewError):
        validate_labels(invalid, location='prediction', contract=FISCAL_CONTRACT)


def test_direct_runs_freeze_schema_reuse_client_compare_and_preserve_golden(reviewed, tmp_path, monkeypatch):
    targets = {case.ticker: project_labels(case.to_dict()['labels'])[0] for case in load_dataset(reviewed).cases}
    before = all_hashes(reviewed)
    opened = []
    def client(config):
        provider = config['provider']
        def handler(request):
            body = json.loads(request.content)
            field = 'input' if provider == 'openai' else 'messages'
            context = json.loads(body[field][0]['content'][0]['text'].removeprefix('Filing context: '))
            return 200, native(provider, targets[context['ticker']])
        result = sdk_client(provider, handler)
        opened.append(result)
        return result
    monkeypatch.setattr(direct, 'make_client', client)
    for provider in CONFIGS:
        output = tmp_path / provider
        manifest, result = runner.run(reviewed, output, ROOT / 'configs' / CONFIGS[provider])
        assert manifest['mode'] == provider
        assert result['summary']['exact_cases'] == 2
        assert result['summary']['cost_complete']
        assert Decimal(result['summary']['known_cost_usd']) == Decimal('0.000292')
        assert len(list((output / 'responses').glob('*.provider.json'))) == 2
        for case in load_dataset(reviewed).cases:
            request = read_json(output / 'inputs' / case.case_id / 'request.json')
            assert request['output_schema'] == direct.output_schema(request['label_schema'], provider)
            assert request['output_schema_version'] == 'eps_fiscal_structured.v1'
            assert 'notes' not in request and 'labels' not in request
        assert load_run(output) == (manifest, result)
        assert all('synthetic-key' not in p.read_text() for p in output.rglob('*.json'))
    assert len(opened) == 2 and all(c.is_closed() for c in opened)
    assert 'unchanged' in compare(tmp_path / 'openai', tmp_path / 'anthropic')
    assert all_hashes(reviewed) == before


@pytest.mark.parametrize('provider', CONFIGS)
@pytest.mark.parametrize('failure', ['truncated', 'refusal', 'fenced', 'duplicate_json', 'bad_labels', 'http_error'])
def test_direct_failures_stay_visible_and_keep_usage(reviewed, tmp_path, monkeypatch, provider, failure):
    def handler(request):
        if failure == 'http_error':
            return 401, {'type': 'error', 'error': {'type': 'authentication_error', 'message': 'SENSITIVE_DO_NOT_LOG'}}
        result = native(provider)
        block = result['output'][-1]['content'][0] if provider == 'openai' else result['content'][-1]
        if failure == 'truncated':
            if provider == 'openai':
                result.update(status='incomplete', incomplete_details={'reason': 'max_output_tokens'})
            else:
                result['stop_reason'] = 'max_tokens'
        elif failure == 'refusal':
            if provider == 'openai':
                block.clear()
                block.update(type='refusal', refusal='not accepted')
            else:
                result['stop_details'] = {'type': 'refusal', 'category': 'other'}
        elif failure == 'fenced':
            block['text'] = '```json\n' + block['text'] + '\n```'
        elif failure == 'duplicate_json':
            block['text'] = '{"reported_diluted_eps":[],"reported_diluted_eps":[],"adjusted_diluted_eps":[]}'
        elif failure == 'bad_labels':
            value = payload()
            value['reported_diluted_eps'][0]['fiscal_quarter'] = 9
            block['text'] = json.dumps(value)
        return 200, result
    monkeypatch.setattr(direct, 'make_client', lambda _: sdk_client(provider, handler))
    output = tmp_path / 'failed'
    _, result = runner.run(reviewed, output, ROOT / 'configs' / CONFIGS[provider])
    assert result['summary']['extraction_errors'] == 2
    assert result['summary']['missing'] == 3 and result['summary']['exact_cases'] == 0
    assert result['summary']['cost_complete'] == (failure != 'http_error')
    assert all('SENSITIVE_DO_NOT_LOG' not in p.read_text() for p in output.rglob('*.json'))


@pytest.mark.parametrize('provider', CONFIGS)
def test_saved_predictions_never_read_keys_or_initialize_provider(reviewed, tmp_path, monkeypatch, provider):
    variable = direct.KEY_VARIABLES[provider]
    monkeypatch.delenv(variable, raising=False)
    def forbidden(*args):
        raise AssertionError('Offline rescoring must not construct an SDK client')
    monkeypatch.setattr(direct, 'make_client', forbidden)
    cases = {case.case_id: {'labels': project_labels(case.to_dict()['labels'])[0]}
             for case in load_dataset(reviewed).cases}
    path = tmp_path / 'predictions.json'
    save_json(path, dict(schema_version='eps_predictions.v2', label_contract=FISCAL_CONTRACT, cases=cases))
    _, results = runner.run(reviewed, tmp_path / 'offline', ROOT / 'configs' / CONFIGS[provider], predictions=path)
    assert results['summary']['exact_cases'] == 2


@pytest.mark.parametrize('provider', CONFIGS)
def test_sdk_setup_requires_env_key_ignores_dotenv_and_pins_endpoint(tmp_path, monkeypatch, provider):
    variable = direct.KEY_VARIABLES[provider]
    monkeypatch.chdir(tmp_path)
    (tmp_path / '.env').write_text(f'{variable}=ignored-synthetic-key\n')
    monkeypatch.delenv(variable, raising=False)
    config = config_for(provider)
    with pytest.raises(ReviewError, match=variable):
        direct.make_client(config)
    monkeypatch.setenv(variable, 'synthetic-key')
    monkeypatch.setenv(provider.upper() + '_BASE_URL', 'https://must-not-receive-keys.invalid')
    monkeypatch.setenv('ANTHROPIC_WORKSPACE_ID', 'workspace-synthetic')
    calls = []
    sdk = import_module(provider)
    monkeypatch.setattr(sdk, 'OpenAI' if provider == 'openai' else 'Anthropic', lambda **kwargs: calls.append(kwargs))
    direct.make_client(config)
    assert calls[0]['api_key'] == 'synthetic-key'
    assert calls[0]['base_url'] == direct.ENDPOINTS[provider]
    assert calls[0]['max_retries'] == 1 and calls[0]['timeout'] == 120
    if provider == 'anthropic':
        assert calls[0]['default_headers'] == {'anthropic-workspace-id': 'workspace-synthetic'}


@pytest.mark.parametrize('provider', CONFIGS)
@pytest.mark.parametrize('changes', [dict(region='us-east-1'), dict(aws_profile='fake'), dict(command=['fake']),
                                    dict(label_contract='earnings_eps.v1'), dict(api_key='must-not-persist'),
                                    dict(settings={'max_output_tokens': True}), dict(settings={'max_output_tokens': 15}),
                                    dict(settings={'temperature': 0}), dict(settings={'effort': 'unexpected', 'reasoning_effort': 'unexpected'})])
def test_invalid_direct_config_is_refused_before_sdk_use(tmp_path, provider, changes):
    record = read_json(ROOT / 'configs' / CONFIGS[provider]) | changes
    record['prompt_file'] = str(ROOT / 'prompts/eps-v4.txt')
    path = tmp_path / 'config.json'
    save_json(path, record)
    with pytest.raises(ReviewError):
        load_config(path)


@pytest.mark.parametrize('provider,threshold,input_multiplier,output_multiplier', [
    ('openai', 272000, '2', '1.5'), ('anthropic', 100000, '5', '5')])
def test_direct_prices_use_per_request_total_prompt_threshold(provider, threshold, input_multiplier, output_multiplier):
    pricing = config_for(provider)['pricing']
    below = dict(inputTokens=threshold - 100, cacheReadInputTokens=100, outputTokens=100)
    base = (Decimal(threshold - 100) * Decimal('.10') + Decimal(100) * Decimal('.01')
            + Decimal(100) * Decimal('.50')) / Decimal(1000000)
    assert Decimal(estimate_cost(below, pricing)) == base
    above = dict(below, cacheReadInputTokens=101)
    expected = ((Decimal(threshold - 100) * Decimal('.10') + Decimal(101) * Decimal('.01')) * Decimal(input_multiplier)
                + Decimal(100) * Decimal('.50') * Decimal(output_multiplier)) / Decimal(1000000)
    assert Decimal(estimate_cost(above, pricing)) == expected


@pytest.mark.parametrize('provider', CONFIGS)
@pytest.mark.parametrize('change', ['schema', 'source'])
def test_changed_frozen_schema_or_source_refuses_provider_call(tmp_path, monkeypatch, provider, change):
    request_path, _ = frozen_request(tmp_path, provider)
    if change == 'schema':
        request = read_json(request_path)
        request['output_schema']['properties'] = {}
        save_json(request_path, request)
    else:
        (tmp_path / 'page.jpg').write_bytes(b'changed')
    def forbidden(request):
        raise AssertionError('Changed inputs must fail before an API request')
    monkeypatch.setattr(direct, 'make_client', lambda _: sdk_client(provider, forbidden))
    adapter = direct.DirectExtractor(config_for(provider))
    try:
        raw, _, error = adapter.invoke(request_path, tmp_path, tmp_path / 'refused.json')
    finally:
        adapter.close()
    assert error and json.loads(raw)['labels'] is None
    assert not (tmp_path / 'refused.provider.json').exists()


@pytest.mark.parametrize('provider', CONFIGS)
def test_missing_or_invalid_usage_never_becomes_free_inference(provider):
    config = config_for(provider)
    for usage in (None, {}, {'input_tokens': True, 'output_tokens': 100},
                  {'input_tokens': 1000, 'output_tokens': -1}):
        normalized = direct.normalized_usage({'usage': usage}, provider)
        assert 'inputTokens' not in normalized
        assert estimate_cost(normalized, config['pricing']) is None
    if provider == 'openai':
        value = native(provider)
        value['usage']['input_tokens_details']['cached_tokens'] = 1001
        assert 'inputTokens' not in direct.normalized_usage(value, provider)


@pytest.mark.parametrize('message,expected', [
    ("'claude-haiku-5-5' does not support the `speed` parameter. SENSITIVE_DO_NOT_LOG", 'omit it'),
    ('This API key is not scoped to a workspace. SENSITIVE_DO_NOT_LOG', 'ANTHROPIC_WORKSPACE_ID'),
    ('anthropic-workspace-id header must be a valid workspace ID. SENSITIVE_DO_NOT_LOG', 'ANTHROPIC_WORKSPACE_ID'),
    ('Your credit balance is too low. SENSITIVE_DO_NOT_LOG', 'API credit balance'),
    ('Unknown provider problem. SENSITIVE_DO_NOT_LOG', 'Check credentials'),
])
def test_provider_diagnostics_use_static_hints_and_never_echo_messages(message, expected):
    error = SimpleNamespace(status_code=400, body={'error': {'message': message}}, request_id='req_synthetic123')
    result = direct.request_error('anthropic', error)
    assert expected in result and 'req_synthetic123' in result
    assert 'SENSITIVE_DO_NOT_LOG' not in result
    assert 'HTTP status 400' in result


def test_provider_diagnostics_refuse_arbitrary_request_ids_and_error_bodies():
    error = SimpleNamespace(status_code=400, body='SENSITIVE_DO_NOT_LOG', request_id='Bearer SENSITIVE_DO_NOT_LOG')
    result = direct.request_error('openai', error)
    assert 'SENSITIVE_DO_NOT_LOG' not in result and 'Request ID' not in result
