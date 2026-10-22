"""One filing per Bedrock Converse call, with text and verified page images."""

from decimal import Decimal, InvalidOperation
from io import BytesIO
import json
from pathlib import Path
import time
import warnings

from ..review.errors import ReviewError
from ..review.viewer import plain_text_preview
from .files import decode, digest, write_json

RATE_FIELDS = ('input_per_million', 'output_per_million', 'cache_read_per_million', 'cache_write_per_million')
MULTIPLIERS = ('long_context_input_multiplier', 'long_context_output_multiplier')
EPS_TOOL = 'submit_eps'
HTML_INPUTS = ('plain_text', 'raw_html', 'cleaned_html')


def require_html_input(mode):
    if not isinstance(mode, str) or mode not in HTML_INPUTS:
        raise ReviewError(f'html_input must be one of {HTML_INPUTS}.')
    return mode


def preprocessing_description(config):
    mode = require_html_input(config.get('html_input', 'plain_text'))
    text = {'plain_text': 'review.plain_text_preview.v1', 'raw_html': 'raw_html.utf8.v1',
            'cleaned_html': 'cleaned_html.html5.v1'}[mode]
    return text + ' plus original manifest image bytes'


def validate_config(config):
    require_html_input(config.get('html_input', 'plain_text'))
    if 'command' in config:
        raise ReviewError('A Bedrock config must not specify a command.')
    if not isinstance(config.get('region'), str) or not config['region'].strip():
        raise ReviewError('Bedrock config requires an explicit region.')
    if 'aws_profile' in config and (not isinstance(config['aws_profile'], str) or not config['aws_profile'].strip()):
        raise ReviewError('aws_profile must be a nonblank name when supplied.')
    settings = config.get('settings', {})
    if not isinstance(settings, dict) or set(settings) - {'max_output_tokens', 'output_mode'}:
        raise ReviewError('Bedrock settings support max_output_tokens and output_mode only.')
    mode = settings.get('output_mode', 'text')
    if not isinstance(mode, str) or mode not in {'text', 'tool'}:
        raise ReviewError('output_mode must be text or tool.')
    tokens = settings.get('max_output_tokens', 4096)
    if type(tokens) is not int or not 1 <= tokens <= 128000:
        raise ReviewError('max_output_tokens must be an integer from 1 to 128000.')
    validate_pricing(config.get('pricing'))


def validate_pricing(pricing):
    """Validate the shared, pinned token-rate table without loading a provider SDK."""
    if pricing is not None:
        if not isinstance(pricing, dict) or set(pricing) != {*RATE_FIELDS, *MULTIPLIERS, 'long_context_threshold', 'source_url', 'as_of'}:
            raise ReviewError('Pricing must include all documented rates, threshold, multipliers, source_url and as_of.')
        for key in (*RATE_FIELDS, *MULTIPLIERS):
            try:
                valid = isinstance(pricing[key], str) and Decimal(pricing[key]).is_finite() and Decimal(pricing[key]) >= 0
            except InvalidOperation:
                valid = False
            if not valid:
                raise ReviewError(f'Pricing {key} must be a nonnegative finite decimal string.')
        if type(pricing['long_context_threshold']) is not int or pricing['long_context_threshold'] <= 0:
            raise ReviewError('Pricing long_context_threshold must be a positive integer.')
        if any(not isinstance(pricing[key], str) or not pricing[key].strip() for key in ('source_url', 'as_of')):
            raise ReviewError('Pricing source_url and as_of must be nonblank strings.')


def make_client(config):
    import boto3
    from botocore.config import Config
    from botocore.exceptions import BotoCoreError

    try:
        session = boto3.Session(profile_name=config.get('aws_profile'), region_name=config['region'])
        return session.client('bedrock-runtime', config=Config(
            connect_timeout=10, read_timeout=config.get('timeout_seconds', 120),
            retries={'total_max_attempts': 2, 'mode': 'adaptive'},
        ))
    except BotoCoreError as exc:
        raise ReviewError(f'Bedrock client setup failed ({type(exc).__name__}); check the AWS profile and credentials.') from exc


def content_blocks(request, workdir, *, html_input='plain_text'):
    from PIL import Image

    require_html_input(html_input)
    blocks = [{'text': 'Filing context: ' + json.dumps(request['filing'], ensure_ascii=False)}]
    image_count = 0
    total_bytes = 0
    for document in request['documents']:
        path = (workdir / document['path']).resolve()
        if not path.is_relative_to(workdir.resolve()) or not path.is_file():
            raise ReviewError('Extractor document path escapes its frozen input directory.')
        raw = path.read_bytes()
        if digest(raw) != document['sha256']:
            raise ReviewError('Frozen extractor document hash mismatch.')
        total_bytes += len(raw)
        if total_bytes > 64 * 1024 * 1024:
            raise ReviewError('Filing source bytes exceed the 64 MiB extraction limit; nothing was truncated.')
        blocks.append({'text': 'Source attachment: ' + document['filename']})
        mime = (document['content_type'] or '').split(';')[0].strip().lower()
        if mime.startswith('image/'):
            image_count += 1
            if image_count > 20 or len(raw) > 3_750_000:
                raise ReviewError('Bedrock permits at most 20 images, each at most 3.75 MB; nothing was omitted.')
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter('error', Image.DecompressionBombWarning)
                    with Image.open(BytesIO(raw)) as image:
                        if (image.format not in {'JPEG', 'PNG', 'GIF', 'WEBP'} or getattr(image, 'n_frames', 1) != 1
                                or max(image.size) > 8000):
                            raise ValueError('unsupported raster')
                        image.verify()
                        format = image.format.lower()
            except (OSError, ValueError, Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
                raise ReviewError('Invalid or oversized extraction image.') from exc
            blocks.append({'image': {'format': format, 'source': {'bytes': raw}}})
        elif mime in {'text/html', 'application/xhtml+xml'} or path.suffix.lower() in {'.htm', '.html'}:
            if html_input == 'raw_html':
                try:
                    text = raw.decode('utf-8')
                except UnicodeDecodeError as exc:
                    raise ReviewError(f'Raw HTML input requires UTF-8 in {document["filename"]}; nothing was replaced or omitted.') from exc
                if not text.strip():
                    raise ReviewError('Raw HTML attachment is empty; nothing was replaced or omitted.')
            elif html_input == 'cleaned_html':
                from .html_input import cleaned_html
                text = cleaned_html(raw)
            else:
                text = plain_text_preview(raw) or '[No readable text in this attachment]'
            blocks.append({'text': text})
        else:
            raise ReviewError(f'Unsupported source attachment type: {document["filename"]}; nothing was omitted.')
    return blocks


def estimate_cost(usage, pricing):
    if pricing is None:
        return None
    keys = ('inputTokens', 'outputTokens', 'cacheReadInputTokens', 'cacheWriteInputTokens')
    if any(type(usage.get(key, 0)) is not int or usage.get(key, 0) < 0 for key in keys):
        return None
    if any(key not in usage for key in ('inputTokens', 'outputTokens')):
        return None
    input_tokens, output_tokens, cache_read, cache_write = (usage.get(key, 0) for key in keys)
    long = input_tokens + cache_read + cache_write > pricing['long_context_threshold']
    input_multiplier = Decimal(pricing['long_context_input_multiplier']) if long else Decimal(1)
    output_multiplier = Decimal(pricing['long_context_output_multiplier']) if long else Decimal(1)
    total = ((input_tokens * Decimal(pricing['input_per_million'])
              + cache_read * Decimal(pricing['cache_read_per_million'])
              + cache_write * Decimal(pricing['cache_write_per_million'])) * input_multiplier
             + output_tokens * Decimal(pricing['output_per_million']) * output_multiplier)
    return str(total / Decimal(1_000_000))


class BedrockExtractor:
    def __init__(self, config):
        self.config = config
        self.client = make_client(config)

    def invoke(self, request_path, workdir, raw_path):
        from botocore.exceptions import BotoCoreError, ClientError

        started = time.monotonic()
        error = None
        envelope = {'labels': None, 'usage': {}, 'cost_usd': None}
        try:
            request = decode(request_path.read_bytes())
            content = content_blocks(request, workdir, html_input=self.config.get('html_input', 'plain_text'))
            tool_mode = self.config.get('settings', {}).get('output_mode', 'text') == 'tool'
            system = request['prompt'] + '\n\nRequired JSON schema:\n' + json.dumps(request['label_schema'])
            parameters = dict(
                modelId=self.config['model'],
                system=[{'text': system}],
                messages=[{'role': 'user', 'content': content}],
                inferenceConfig={'maxTokens': self.config.get('settings', {}).get('max_output_tokens', 4096)},
            )
            if tool_mode:
                parameters['system'][0]['text'] += (
                    f'\n\nSubmit the EPS payload as the input to {EPS_TOOL}. Call it exactly once; do not return a text response.'
                )
                parameters['toolConfig'] = {
                    'tools': [{'toolSpec': {'name': EPS_TOOL,
                              'description': 'Submit the reported and adjusted diluted EPS observations from this filing package.',
                              'inputSchema': {'json': request['label_schema']}}}],
                    'toolChoice': {'tool': {'name': EPS_TOOL}},
                }
            result = self.client.converse(**parameters)
            # Preserve the native response as well as the normalized extraction envelope.
            write_json(raw_path.with_suffix('.provider.json'), result)
            envelope['usage'] = result.get('usage', {})
            envelope['cost_usd'] = estimate_cost(envelope['usage'], self.config.get('pricing'))
            expected_stop = 'tool_use' if tool_mode else 'end_turn'
            if result.get('stopReason') != expected_stop:
                error = f'Bedrock stopped with {result.get("stopReason", "unknown")}; output was not accepted.'
            else:
                blocks = result.get('output', {}).get('message', {}).get('content', [])
                if tool_mode:
                    tools = [block['toolUse'] for block in blocks if 'toolUse' in block]
                    if len(tools) != 1 or tools[0].get('name') != EPS_TOOL:
                        raise ReviewError('Expected exactly one submit_eps tool response.')
                    envelope['labels'] = tools[0].get('input')
                else:
                    text = ''.join(block['text'] for block in blocks if 'text' in block)
                    envelope['labels'] = decode(text)
        except ClientError as exc:
            # Do not expose SDK headers or arbitrary provider messages that could contain credentials.
            error = f'Bedrock request failed: {exc.response.get("Error", {}).get("Code", "unknown")}. Check model access, region and quotas.'
        except BotoCoreError as exc:
            error = f'Bedrock SDK failure ({type(exc).__name__}); check credentials and connectivity.'
        except ReviewError as exc:
            error = str(exc)
        write_json(raw_path, envelope)
        return raw_path.read_bytes(), time.monotonic() - started, error
