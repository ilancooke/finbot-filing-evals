from dataclasses import replace

import pytest

html5lib = pytest.importorskip("html5lib")
pytest.importorskip("bleach")
pytest.importorskip("tinycss2")

from finbot_filing_evals.review.dataset import load_dataset
from finbot_filing_evals.review.viewer import (
    initial_attachment, plain_text_preview, sanitized_html, viewer_frame,
)


def parse(html):
    return html5lib.parse(html, namespaceHTMLElements=False)


def test_nested_tables_and_inline_formatting_survive():
    raw = b'''<table width="100%" cellspacing="0"><tr><td colspan="2"
    style="text-align:right; border-bottom:1px solid black; font-weight:bold">
    EPS<table><tr><th>Quarter</th><td><b>4.60</b><sup>1</sup></td></tr></table>
    </td></tr></table><p>Following text</p>'''
    tree = parse(sanitized_html(raw))
    assert len(tree.findall(".//table")) == 2
    cell = tree.find(".//td")
    assert cell.attrib["colspan"] == "2"
    assert "text-align:right" in cell.attrib["style"]
    assert "border-bottom:1px solid black" in cell.attrib["style"]
    assert tree.find(".//b").text == "4.60"
    assert tree.find(".//sup").text == "1"
    assert "Following text" in "".join(tree.itertext())


@pytest.mark.parametrize("payload", [
    '<script src="https://blocked.invalid/a">SCRIPT_SENTINEL</script>',
    '<img src="//blocked.invalid/a" srcset="https://blocked.invalid/b 2x" onerror="alert(1)">',
    '<iframe srcdoc="<script>alert(1)</script>" src="https://blocked.invalid/a">FRAME_SENTINEL</iframe>',
    '<object data="https://blocked.invalid/a">OBJECT_SENTINEL</object><embed src="https://blocked.invalid/b">',
    '<svg><a href="https://blocked.invalid/a"><text>SVG_SENTINEL</text></a></svg>',
    '<math><mtext><img src="https://blocked.invalid/a" onerror="alert(1)"></mtext></math>',
    '<form action="https://blocked.invalid/a"><input autofocus onfocus="alert(1)"><button>Submit</button></form>',
    '<a href="javascript:alert(1)" ping="https://blocked.invalid/a" target="_top">Link text</a>',
    '<video poster="https://blocked.invalid/a"><source src="https://blocked.invalid/b"></video>',
    '<link rel="stylesheet" href="https://blocked.invalid/a"><base href="https://blocked.invalid/">',
    '<meta http-equiv="refresh" content="0;url=https://blocked.invalid/a">',
    '<style>@import "https://blocked.invalid/a"; body { display:none }</style>',
    '<noscript><img src="https://blocked.invalid/a"></noscript>',
    '<!--><img src=https://blocked.invalid/a onerror=alert(1)>-->',
    '<math><mtext><table><mglyph><style><!--</style><img title="--><img src=https://blocked.invalid/a onerror=alert(1)>">',
])
def test_active_elements_and_resource_attributes_are_removed(payload):
    tree = parse(sanitized_html(("<p>Visible start</p>" + payload + "<p>Visible end</p>").encode()))
    body = tree.find("body")
    forbidden = {"script", "style", "iframe", "object", "embed", "svg", "math", "img",
                 "input", "button", "form", "video", "source", "link", "base", "meta"}
    for element in body.iter():
        assert element.tag not in forbidden
        assert not any(key.lower().startswith("on") for key in element.attrib)
        assert not ({"href", "src", "srcset", "srcdoc", "action", "data", "ping", "id", "name"} & element.attrib.keys())
    text = "".join(body.itertext())
    assert "Visible start" in text
    assert not any(marker in text for marker in ("SCRIPT_SENTINEL", "FRAME_SENTINEL", "OBJECT_SENTINEL", "SVG_SENTINEL"))


@pytest.mark.parametrize("style", [
    "background-image:url(https://blocked.invalid/a)",
    r"color:u\72l(https://blocked.invalid/a)",
    'font-family:url("https://blocked.invalid/a")',
    'width:expression(alert(1))',
    'color:var(--external);--external:url(https://blocked.invalid/a)',
    'background:image-set(url(https://blocked.invalid/a) 1x)',
    '@import "https://blocked.invalid/a"',
    'display:none;visibility:hidden;position:fixed;opacity:0;content:"hidden"',
])
def test_css_removes_resource_loads_and_active_or_hidden_styling(style):
    raw = f'<p style=\'{style};text-align:right;color:rgb(1, 2, 3)\'>Visible</p>'.encode()
    value = parse(sanitized_html(raw)).find(".//p").attrib["style"]
    assert "text-align:right" in value
    assert "color:rgb(1, 2, 3)" in value
    assert "blocked.invalid" not in value
    assert "expression" not in value
    assert "display" not in value
    assert "visibility" not in value


def test_sandbox_and_csp_are_present_and_source_cannot_escape_srcdoc():
    raw = b'''</iframe><script>alert(1)</script><p title='" onload="alert(1)'>4.60</p>'''
    tree = parse(viewer_frame(raw))
    frames = tree.findall(".//iframe")
    assert len(frames) == 1
    assert frames[0].attrib["sandbox"] == ""
    assert frames[0].attrib["referrerpolicy"] == "no-referrer"
    assert tree.find(".//script") is None
    inner = parse(frames[0].attrib["srcdoc"])
    policy = inner.find('.//meta[@http-equiv="Content-Security-Policy"]').attrib["content"]
    for rule in ("default-src 'none'", "script-src 'none'", "form-action 'none'", "base-uri 'none'"):
        assert rule in policy
    assert inner.find(".//script") is None
    assert inner.find(".//p").text == "4.60"
    assert "onload" not in inner.find(".//p").attrib


def test_text_fallback_uses_original_and_preserves_missing_image_alt():
    raw = b'''<html><head><style>HIDDEN</style></head><body><ix:header>HIDDEN</ix:header>
    <p>Before <b>bold</b> after<img src="missing.jpg" alt="Revenue chart"></p>
    <table><tr><td>Quarter</td><td>4.60</td></tr></table>
    <script>HIDDEN</script>Following text</body></html>'''
    text = plain_text_preview(raw)
    assert "Before bold after [Image: Revenue chart]" in text
    assert "Quarter | 4.60 |" in text
    assert "Following text" in text
    assert "HIDDEN" not in text
    assert "Revenue chart" in sanitized_html(raw)
    assert plain_text_preview(b"<script>hidden</script>") == ""
    assert plain_text_preview(b"<table><tr><td> </td><td><br></td></tr></table>") == ""


def test_html_encoding_declarations_are_respected():
    raw = '<meta charset="windows-1252"><p>Profit \u2013 \u20ac4.60</p>'.encode("cp1252")
    assert "Profit \u2013 \u20ac4.60" in plain_text_preview(raw)
    assert "Profit \u2013 \u20ac4.60" in sanitized_html(raw)


def test_initial_attachment_prefers_exhibit_then_manifest_order(dataset_root):
    documents = load_dataset(dataset_root).cases[0].documents
    assert initial_attachment(documents) == documents[1].artifact_id
    assert initial_attachment([replace(doc, document_type="10-Q") for doc in documents]) == documents[0].artifact_id
    assert initial_attachment([replace(documents[0], document_type=" ex-99.1 "), documents[1]]) == documents[0].artifact_id


def test_viewing_all_sources_does_not_change_any_dataset_file(dataset_root):
    before = {p: p.read_bytes() for p in dataset_root.rglob("*") if p.is_file()}
    for case in load_dataset(dataset_root).cases:
        for document in case.documents:
            raw = document.read_bytes()
            assert viewer_frame(raw)
            assert plain_text_preview(raw)
    assert {p: p.read_bytes() for p in before} == before
