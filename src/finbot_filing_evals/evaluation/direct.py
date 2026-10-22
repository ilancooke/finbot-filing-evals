"""Direct OpenAI Responses and Anthropic Messages extraction, one call per filing.

SDKs and credentials are loaded only when constructing a live extractor. Shared
source preparation, local contract validation and scoring remain provider-neutral.
"""

from base64 import b64encode
from copy import deepcopy
from importlib import import_module
import json
import os
import re
import time

from ..review.errors import ReviewError
from .bedrock import content_blocks, estimate_cost, require_html_input, validate_pricing
from .contracts import FISCAL_CONTRACT, load_schema
from .files import decode, write_json

KEY_VARIABLES = {'openai': 'OPENAI_API_KEY', 'anthropic': 'ANTHROPIC_API_KEY'}
ENDPOINTS = {'openai': 'https://api.openai.com/v1', 'anthropic': 'https://api.anthropic.com'}


def validate_config(config):
    if any(key in config for key in ('command', 'region', 'aws_profile')):
        raise ReviewError('Direct providers must not specify command, region or aws_profile.')
    if config.get('label_contract') != FISCAL_CONTRACT:
        raise ReviewError('Direct providers require the explicit earnings_eps.fiscal.v2 contract.')
    require_html_input(config.get('html_input', 'plain_text'))
    field = 'reasoning_effort' if config['provider'] == 'openai' else 'effort'
    settings = config.get('settings', {})
    if not isinstance(settings, dict) or set(settings) - {'max_output_tokens', field}:
        raise ReviewError(f'Direct {config["provider"]} settings support max_output_tokens and {field} only.')
    tokens = settings.get('max_output_tokens', 4096)
    if type(tokens) is not int or not 16 <= tokens <= 128000:
        raise ReviewError('max_output_tokens must be an integer from 16 to 128000.')
    efforts = {'low', 'medium', 'high', 'xhigh', 'max'}
    if field == 'reasoning_effort':
        efforts.add('none')
    effort = settings.get(field, 'medium')
    if not isinstance(effort, str) or effort not in efforts:
        raise ReviewError(f'Invalid {field} for direct {config["provider"]}.')
    validate_pricing(config.get('pricing'))


def output_schema(schema, provider):
    """Compile fiscal quarter/year conditionals into provider-supported unions.

    Anthropic does not support numerical bounds; retain the fiscal-year rule in
    its description and enforce it with the full original local schema afterward.
    Quarter bounds remain enforced remotely through an explicit enum.
    """
    if schema != load_schema(FISCAL_CONTRACT):
        raise ReviewError('Direct extraction requires the unchanged fiscal v2 source schema.')
    result = deepcopy(schema)
    result.pop('$schema', None)
    original = result['$defs']['observation']
    original.pop('allOf')
    if provider == 'anthropic':
        year = original['properties']['fiscal_year']
        year.pop('minimum')
        year.pop('maximum')
        year['description'] = 'Issuer fiscal year, an integer from 1000 through 9999.'
    variants = []
    for period in ('quarterly', 'annual'):
        variant = deepcopy(original)
        variant['properties']['period_type'] = {'type': 'string', 'enum': [period]}
        variant['properties']['fiscal_quarter'] = (
            {'type': 'integer', 'enum': [1, 2, 3, 4]} if period == 'quarterly' else {'type': 'null'})
        variants.append(variant)
    result['$defs']['observation'] = {'anyOf': variants}
    return result


def make_client(config):
    provider = config['provider']
    variable = KEY_VARIABLES[provider]
    key = os.environ.get(variable, '').strip()
    if not key:
        raise ReviewError(f'Set {variable} in the environment; .env files are not loaded automatically.')
    try:
        sdk = import_module(provider)
    except ImportError as exc:
        raise ReviewError(f'Install the {provider} extra to use this direct provider.') from exc
    options = dict(api_key=key, base_url=ENDPOINTS[provider],
                   timeout=config.get('timeout_seconds', 120), max_retries=1)
    if provider == 'anthropic':
        workspace = os.environ.get('ANTHROPIC_WORKSPACE_ID', '').strip()
        if workspace:
            options['default_headers'] = {'anthropic-workspace-id': workspace}
    try:
        return (sdk.OpenAI if provider == 'openai' else sdk.Anthropic)(**options)
    except (ValueError, sdk.APIError) as exc:
        raise ReviewError(f'Direct {provider} client setup failed ({type(exc).__name__}).') from exc


def contents(request, workdir, provider, mode):
    """Translate the same verified text/image sequence without fetching assets."""
    result = []
    for block in content_blocks(request, workdir, html_input=mode):
        if 'text' in block:
            result.append({'type': 'input_text' if provider == 'openai' else 'text', 'text': block['text']})
        else:
            image = block['image']
            media_type = 'image/' + image['format']
            data = b64encode(image['source']['bytes']).decode('ascii')
            if provider == 'openai':
                result.append({'type': 'input_image', 'image_url': f'data:{media_type};base64,{data}', 'detail': 'high'})
            else:
                result.append({'type': 'image', 'source': {'type': 'base64', 'media_type': media_type, 'data': data}})
    return result


def normalized_usage(native, provider):
    usage = native.get('usage')
    if not isinstance(usage, dict):
        return {}
    if any(type(usage.get(k)) is not int or usage[k] < 0 for k in ('input_tokens', 'output_tokens')):
        return {'providerUsage': usage}
    details = usage.get('input_tokens_details') or {}
    read = details.get('cached_tokens', 0) if provider == 'openai' else usage.get('cache_read_input_tokens', 0)
    write = details.get('cache_write_tokens', 0) if provider == 'openai' else usage.get('cache_creation_input_tokens', 0)
    if any(type(n) is not int or n < 0 for n in (read, write)):
        return {'providerUsage': usage}
    ordinary = usage['input_tokens'] - read - write if provider == 'openai' else usage['input_tokens']
    if ordinary < 0:
        return {'providerUsage': usage}
    return dict(inputTokens=ordinary, outputTokens=usage['output_tokens'],
                cacheReadInputTokens=read, cacheWriteInputTokens=write,
                totalTokens=ordinary + read + write + usage['output_tokens'], providerUsage=usage)


def extraction_text(native, provider):
    if provider == 'openai':
        if native.get('status') != 'completed' or native.get('error') or native.get('incomplete_details'):
            raise ReviewError('OpenAI response was incomplete or failed; output was not accepted.')
        messages = [item for item in native.get('output', []) if item.get('type') == 'message']
        if (len(messages) != 1 or messages[0].get('status') != 'completed' or messages[0].get('role') != 'assistant'
                or any(item.get('type') not in {'message', 'reasoning'} for item in native.get('output', []))):
            raise ReviewError('Expected one complete OpenAI assistant message without tool calls.')
        blocks = messages[0].get('content', [])
        kind = 'output_text'
        if any(block.get('type') not in {'output_text', 'refusal'} for block in blocks):
            raise ReviewError('Unexpected OpenAI response block; output was not accepted.')
    else:
        if native.get('stop_reason') != 'end_turn' or (native.get('stop_details') or {}).get('type') == 'refusal':
            raise ReviewError('Anthropic response stopped early or was refused; output was not accepted.')
        blocks = native.get('content', [])
        kind = 'text'
        if any(block.get('type') not in {'text', 'thinking', 'redacted_thinking'} for block in blocks):
            raise ReviewError('Unexpected Anthropic response block; output was not accepted.')
    texts = [block['text'] for block in blocks if block.get('type') == kind and isinstance(block.get('text'), str)]
    if len(texts) != 1 or any(block.get('type') == 'refusal' for block in blocks):
        raise ReviewError('Expected one JSON text block; refusal or unexpected output was not accepted.')
    return texts[0]


def request_error(provider, error):
    """Retain only static diagnostic hints and a confined provider request ID.

    Error messages can echo request values or credentials. Inspect them in memory
    to recognize a small set of actionable failures; never persist their text.
    """
    status = getattr(error, 'status_code', None)
    status = status if type(status) is int else 'unavailable'
    result = f'{provider} request failed ({type(error).__name__}, HTTP status {status}).'
    body = getattr(error, 'body', None)
    item = body.get('error', body) if isinstance(body, dict) else None
    message = item.get('message', '') if isinstance(item, dict) else ''
    hint = 'Check credentials, model access and input limits.'
    if isinstance(message, str) and provider == 'anthropic':
        if 'does not support the `speed` parameter' in message:
            hint = 'This model rejects the speed parameter; omit it and use the default speed.'
        elif 'not scoped to a workspace' in message or 'anthropic-workspace-id header must be' in message:
            hint = 'Set ANTHROPIC_WORKSPACE_ID to a valid workspace ID, or use a workspace-scoped key.'
        elif 'credit balance' in message.lower():
            hint = 'Check the Anthropic API credit balance and billing settings.'
    request_id = getattr(error, 'request_id', None)
    if isinstance(request_id, str) and re.fullmatch(r'req_[A-Za-z0-9]{8,80}', request_id):
        result += f' Request ID: {request_id}.'
    return result + ' ' + hint


class DirectExtractor:
    def __init__(self, config):
        self.config = config
        self.client = make_client(config)

    def close(self):
        self.client.close()

    def invoke(self, request_path, workdir, raw_path):
        provider = self.config['provider']
        sdk = import_module(provider)
        started = time.monotonic()
        envelope = {'labels': None, 'usage': {}, 'cost_usd': None}
        error = None
        try:
            request = decode(request_path.read_bytes())
            schema = output_schema(request['label_schema'], provider)
            if request.get('output_schema') != schema:
                raise ReviewError('Frozen direct-provider output schema mismatch.')
            content = contents(request, workdir, provider, self.config.get('html_input', 'plain_text'))
            settings = self.config.get('settings', {})
            system = request['prompt'] + '\n\nRequired JSON schema:\n' + json.dumps(request['label_schema'])
            if provider == 'openai':
                result = self.client.responses.create(
                    model=self.config['model'], instructions=system,
                    input=[{'role': 'user', 'content': content}],
                    text={'format': {'type': 'json_schema', 'name': 'earnings_eps', 'strict': True, 'schema': schema}},
                    max_output_tokens=settings.get('max_output_tokens', 4096),
                    reasoning={'effort': settings.get('reasoning_effort', 'medium')},
                    store=False, truncation='disabled', service_tier='default',
                    prompt_cache_options={'mode': 'implicit', 'ttl': '30m'},
                )
            else:
                result = self.client.messages.create(
                    model=self.config['model'], system=system,
                    messages=[{'role': 'user', 'content': content}],
                    max_tokens=settings.get('max_output_tokens', 4096), thinking={'type': 'adaptive'},
                    output_config={'format': {'type': 'json_schema', 'schema': schema},
                                   'effort': settings.get('effort', 'medium')},
                    service_tier='standard_only', inference_geo='global',
                )
            native = result.model_dump(mode='json')
            write_json(raw_path.with_suffix('.provider.json'), native)
            envelope['usage'] = normalized_usage(native, provider)
            envelope['cost_usd'] = estimate_cost(envelope['usage'], self.config.get('pricing'))
            envelope['labels'] = decode(extraction_text(native, provider))
        except sdk.APIError as exc:
            # Never persist SDK error messages, request headers, bodies or keys.
            error = request_error(provider, exc)
        except ReviewError as exc:
            error = str(exc)
        write_json(raw_path, envelope)
        return raw_path.read_bytes(), time.monotonic() - started, error
