"""Content retention matters more than cosmetic serialization of cleaned HTML."""

import pytest

html5lib = pytest.importorskip('html5lib')

from finbot_filing_evals.evaluation.html_input import cleaned_html


def parse(source):
    return html5lib.parse(cleaned_html(source), namespaceHTMLElements=False)


def test_grouped_table_headers_empty_cells_and_currency_notes_remain_linked():
    raw = b'''<h2>Quarterly results</h2><p>Amounts in EUR, except per share.</p>
      <table summary="Earnings per ordinary share"><caption>Fiscal results</caption>
      <colgroup span="5"></colgroup><thead><tr><th rowspan="2"></th>
      <th id="q" colspan="2" scope="colgroup">Third Quarter</th>
      <th id="ytd" colspan="2">Three Fiscal Quarters</th></tr>
      <tr><th>2031</th><th>2030</th><th>2031</th><th>2030</th></tr></thead>
      <tbody><tr><th scope="row">Diluted EPS<sup>1</sup></th>
      <td headers="q">2.15</td><td>1.90</td><td headers="ytd">6.40</td><td>5.80</td>
      </tr></tbody></table><p>1: Diluted amounts per ordinary share.</p>'''
    root = parse(raw)
    table = next(root.iter('table'))
    assert table.get('summary') == 'Earnings per ordinary share'
    assert next(table.iter('caption')).text == 'Fiscal results'
    assert [cell.get('colspan') for cell in table.iter('th')][:3] == [None, '2', '2']
    assert next(table.iter('th')).get('rowspan') == '2'
    assert next(table.iter('th')).text is None  # Empty alignment cell survives.
    assert [cell.text for cell in table.iter('td')] == ['2.15', '1.90', '6.40', '5.80']
    assert [cell.get('headers') for cell in table.iter('td')] == ['q', None, 'ytd', None]
    assert 'Amounts in EUR' in ''.join(root.itertext())
    assert '1: Diluted amounts per ordinary share.' in ''.join(root.itertext())


def test_formatting_and_visible_ixbrl_wrappers_are_unwrapped_without_changing_numbers():
    raw = '''<html><body><font class="large" color="red">Currency: €.</font>
      <p>EPS <span>(</span><ix:nonfraction name="EPS" unitRef="EUR" scale="0">
      <span>12</span><span>.930</span></ix:nonfraction><span>)</span>
      <span aria-hidden="true">Visible financial text</span></p></body></html>'''.encode()
    result = cleaned_html(raw)
    assert 'Currency: €.' in result
    assert '12.930' in result and ')' in result and '(' in result
    assert 'Visible financial text' in result  # aria-hidden is not visual hiding.
    assert 'unitRef' not in result and 'ix:nonfraction' not in result
    assert '<font' not in result and '<span' not in result and 'class=' not in result


@pytest.mark.parametrize('hidden_open,hidden_close', [
    ('<div hidden>', '</div>'),
    ('<div style="DISPLAY : none !important">', '</div>'),
    ('<div style="color:red; visibility: hidden; font-size:12px">', '</div>'),
    ('<div style="display:/* metadata */none">', '</div>'),
    ('<ix:header>', '</ix:header>'),
    ('<ix:hidden>', '</ix:hidden>'),
    ('<nav>', '</nav>'),
])
def test_hidden_metadata_is_removed_without_losing_following_visible_text(hidden_open, hidden_close):
    raw = f'<p>Before</p>{hidden_open}<p>Metadata 999.99</p>{hidden_close}After <b>4.60</b>'
    result = cleaned_html(raw.encode())
    assert '999.99' not in result and 'Metadata' not in result
    assert 'Before' in result and 'After' in result and '4.60' in result


def test_scripts_styles_comments_links_and_data_images_do_not_bloat_the_input():
    raw = b'''<html><head><style>.p{font:Arial}</style><script>noise()</script></head>
      <body><!-- huge comment --><a href="https://example.invalid/">Footnote reference</a>
      <img src="data:image/png;base64,AAAAAAAA" alt="Sales chart">
      <img src="https://example.invalid/path/page%203.jpg?tracking=1" alt="EPS table">
      <p onclick="noise()" style="color:red" id="long-id">US$4.60 per ADR unit</p>
      <script>otherNoise()</script>Remaining text</body></html>'''
    result = cleaned_html(raw)
    assert 'noise' not in result.lower() and 'huge comment' not in result
    assert 'https:' not in result and 'base64' not in result and 'tracking' not in result
    assert 'style=' not in result and 'onclick=' not in result and 'long-id' not in result
    assert '<img alt="Sales chart">' in result
    assert '<img alt="page 3.jpg | EPS table">' in result
    assert 'Footnote reference' in result and 'US$4.60 per ADR unit' in result and 'Remaining text' in result


def test_nested_layout_tables_do_not_drop_inner_tables_or_empty_cells():
    root = parse(b'<table><tr><td></td><td><table><tr><td>EPS</td><td>3.50</td></tr></table></td></tr></table>')
    assert len(list(root.iter('table'))) == 2
    assert len(list(root.iter('td'))) == 4
    assert '3.50' in ''.join(root.itertext())


def test_declared_encoding_preformatted_text_and_imperfect_html_are_supported():
    raw = b'<meta charset="windows-1252"><p>Currency \x80</p><pre>EPS    4.60\nYTD   12.80</pre><table><tr><td>not closed'
    result = cleaned_html(raw)
    assert 'Currency €' in result
    assert 'EPS    4.60\nYTD   12.80' in result
    assert '<td>not closed</td>' in result
