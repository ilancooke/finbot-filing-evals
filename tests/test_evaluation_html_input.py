"""HTML input fidelity and comparable provider usage, without inference."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip('boto3')
pytest.importorskip('PIL')

from conftest import save_json
from test_evaluation import reviewed, config, all_hashes
from test_evaluation_bedrock import bedrock_config, image_request
from finbot_filing_evals.evaluation import bedrock, runner
from finbot_filing_evals.evaluation.contracts import project_labels
from finbot_filing_evals.evaluation.extractor import load_config
from finbot_filing_evals.evaluation.files import digest, read_json
from finbot_filing_evals.evaluation.html_input import cleaned_html
from finbot_filing_evals.evaluation.reports import compare, token_total
from finbot_filing_evals.review.dataset import load_dataset
from finbot_filing_evals.review.errors import ReviewError


@pytest.mark.parametrize('mode', ['plain_text', 'raw_html', 'cleaned_html'])
def test_html_modes_preserve_attachments_and_images_but_only_raw_keeps_markup(tmp_path, mode):
    request = image_request(tmp_path)
    html = ('<!DOCTYPE html>\r\n<html><head><style>.amount{color:blue}</style>'
            '<script>window.example=true;</script></head><body><!-- original comment -->'
            '<div hidden>hidden metadata</div><p>Amounts in €</p>'
            '<table><tr><th colspan="2">Quarter</th></tr>'
            '<tr><td rowspan="2">Diluted EPS</td><td>4.60</td></tr></table>'
            '</body></html>\r\n').encode('utf-8')
    (tmp_path / 'release.htm').write_bytes(html)
    request['documents'].insert(0, dict(path='release.htm', filename='release.htm',
                                       sha256=digest(html), content_type='text/html'))
    blocks = bedrock.content_blocks(request, tmp_path, html_input=mode)
    assert blocks[1] == {'text': 'Source attachment: release.htm'}
    text = blocks[2]['text']
    if mode == 'raw_html':
        assert text.encode('utf-8') == html
    elif mode == 'cleaned_html':
        assert '<table>' in text and '<th colspan="2">' in text and '<td rowspan="2">' in text
        assert 'Amounts in €' in text and '4.60' in text
        assert 'window.example' not in text and 'hidden metadata' not in text and 'original comment' not in text
    else:
        assert 'Diluted EPS' in text and '4.60' in text and '€' in text
        assert '<table>' not in text and 'window.example' not in text
    assert next(block['image']['source']['bytes'] for block in blocks if 'image' in block) == (tmp_path / 'page0.jpg').read_bytes()
    assert (tmp_path / 'release.htm').read_bytes() == html


@pytest.mark.parametrize('raw', [b'<html>\x80</html>', b'', b' \r\n '])
def test_raw_html_never_replaces_invalid_bytes_or_empty_documents(tmp_path, raw):
    path = tmp_path / 'release.htm'
    path.write_bytes(raw)
    request = dict(filing={}, documents=[dict(path=path.name, filename=path.name,
                   sha256=digest(raw), content_type='text/html')])
    with pytest.raises(ReviewError, match='nothing was replaced or omitted'):
        bedrock.content_blocks(request, tmp_path, html_input='raw_html')


@pytest.mark.parametrize('mode', ['unknown_html', '', None, True, [], {}])
def test_unknown_html_modes_are_rejected_before_model_initialization(bedrock_config, mode):
    record = read_json(bedrock_config) | {'html_input': mode}
    save_json(bedrock_config, record)
    with pytest.raises(ReviewError, match='html_input'):
        load_config(bedrock_config)


def test_command_adapter_does_not_silently_accept_bedrock_html_mode(config):
    save_json(config, read_json(config) | {'html_input': 'raw_html'})
    with pytest.raises(ReviewError, match='only by the Bedrock'):
        load_config(config)


def test_html_modes_keep_v4_prompt_and_scoring_and_report_usage(reviewed, tmp_path, monkeypatch):
    config_root = Path(__file__).parents[1] / 'configs'
    before = all_hashes(reviewed)
    targets = {case.ticker: project_labels(case.to_dict()['labels'])[0] for case in load_dataset(reviewed).cases}
    sources = {case.ticker: [doc.read_bytes().decode('utf-8') for doc in case.documents]
               for case in load_dataset(reviewed).cases}
    expected_mode = None
    expected_prompt = None

    def converse(**params):
        assert params['inferenceConfig'] == {'maxTokens': 4096}
        assert params['system'][0]['text'].startswith(expected_prompt)
        blocks = params['messages'][0]['content']
        context = json.loads(blocks[0]['text'].removeprefix('Filing context: '))
        if expected_mode == 'raw_html':
            assert [block['text'] for block in blocks[2::2]] == sources[context['ticker']]
        elif expected_mode == 'cleaned_html':
            texts = [block['text'] for block in blocks[2::2]]
            assert all('<h1>' in text and '<script>' not in text for text in texts)
            assert all('Diluted EPS: 4.60' in text for text in texts)
        else:
            assert all('<html>' not in block.get('text', '') for block in blocks)
        return dict(stopReason='tool_use', output={'message': {'content': [
            {'toolUse': {'name': 'submit_eps', 'input': targets[context['ticker']]}}
        ]}}, usage={'inputTokens': 2000 if expected_mode == 'raw_html' else 1000, 'outputTokens': 100})

    monkeypatch.setattr(bedrock, 'make_client', lambda _: SimpleNamespace(converse=converse))
    configs, manifests, outputs = [], [], []
    for mode, name in [('plain_text', 'bedrock-nova-2-lite-prompt-v4'),
                       ('raw_html', 'bedrock-nova-2-lite-prompt-v4-raw-html'),
                       ('cleaned_html', 'bedrock-nova-2-lite-prompt-v4-cleaned-html')]:
        expected_mode = mode
        config_path = config_root / f'{name}.json'
        record, expected_prompt = load_config(config_path)
        configs.append({key: value for key, value in record.items()
                        if key not in {'name', 'html_input', 'config_sha256'}})
        output = tmp_path / mode
        outputs.append(output)
        manifest, results = runner.run(reviewed, output, config_path)
        manifests.append(manifest)
        assert results['summary']['correct'] == 3 and results['summary']['exact_cases'] == 2
        assert (output / 'prompt.txt').read_text() == expected_prompt
        for case in load_dataset(reviewed).cases:
            assert read_json(output / 'inputs' / case.case_id / 'request.json')['html_input'] == mode
        report = (output / 'REPORT.md').read_text()
        assert f"inputTokens: {'4,000' if mode == 'raw_html' else '2,000'}" in report
        assert 'outputTokens: 200' in report
    assert all(record == configs[0] for record in configs)
    assert len({manifest['prompt_sha256'] for manifest in manifests}) == 1
    assert manifests[0]['preprocessing'] == 'review.plain_text_preview.v1 plus original manifest image bytes'
    assert manifests[1]['preprocessing'] == 'raw_html.utf8.v1 plus original manifest image bytes'
    assert manifests[2]['preprocessing'] == 'cleaned_html.html5.v1 plus original manifest image bytes'
    comparison = compare(*outputs[:2])
    assert '| inputTokens | 2,000 | 4,000 |' in comparison
    assert '| outputTokens | 200 | 200 |' in comparison
    assert 'known_cost_usd' in comparison and 'duration_seconds' in comparison
    assert 'unchanged' in compare(outputs[0], outputs[2])
    assert all_hashes(reviewed) == before


@pytest.mark.parametrize('usages,expected', [
    ([{'inputTokens': 1000}, {'inputTokens': 2000}], '3,000'),
    ([{'inputTokens': 0}, {'inputTokens': 0}], '0'),
    ([{'inputTokens': 1000}, {}], '1,000 (partial; 1/2 filings reported)'),
    ([{}, {}], 'n/a (partial; 0/2 filings reported)'),
    ([{'inputTokens': True}, {'inputTokens': -1}], 'n/a (partial; 0/2 filings reported)'),
])
def test_token_reporting_preserves_unknown_usage_including_legacy_runs(usages, expected):
    results = {'cases': [{'usage': usage} for usage in usages]}
    assert token_total(results, 'inputTokens') == expected
