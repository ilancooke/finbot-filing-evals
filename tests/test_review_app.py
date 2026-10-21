import hashlib
from pathlib import Path
import sys

import pytest

from finbot_filing_evals.review.viewer import plain_text_preview


def test_preview_extracts_table_text_without_scripts_or_styles():
    pytest.importorskip("html5lib")
    raw = b'''<html><head><title>Hidden title</title><style>hidden style</style></head>
    <body><h1>EPS &amp; periods</h1><table><tr><td>Q3</td><td>4.60</td></tr></table>
    <script src="https://example.invalid/script.js">hidden script</script>
    <img src="https://example.invalid/image.png"><p>Trailing text</p></body></html>'''
    preview = plain_text_preview(raw)
    assert "EPS & periods" in preview
    assert "Q3 | 4.60 |" in preview
    assert "Trailing text" in preview
    assert "hidden" not in preview.lower()
    assert "example.invalid" not in preview
    assert "<" not in preview


def _open_app(monkeypatch, root):
    testing = pytest.importorskip("streamlit.testing.v1")
    for dependency in ("html5lib", "bleach", "tinycss2"):
        pytest.importorskip(dependency)
    monkeypatch.setattr(sys, "argv", ["review_eps.py", "--dataset-root", str(root)])
    script = Path(__file__).resolve().parents[1] / "scripts/review_eps.py"
    return testing.AppTest.from_file(script, default_timeout=30).run()


def _bundle_hashes(root):
    return {p.relative_to(root): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def test_app_switches_filings_and_attachments_without_writes(monkeypatch, dataset_root):
    before = _bundle_hashes(dataset_root)
    app = _open_app(monkeypatch, dataset_root)
    assert not app.exception
    assert not app.error
    assert "2 filings · 3 documents · 4 EPS observations" in [item.value for item in app.caption]
    assert "DEMO release.htm" in app.get("iframe")[0].proto.srcdoc
    assert "sandbox=\"\"" in app.get("iframe")[0].proto.srcdoc
    table = app.table[0].value
    assert table["Value"].tolist() == ["4.60", "9.00", "29.43"]
    assert table["Start"].tolist() == ["Unknown", "2026-01-01", "Unknown"]
    assert any("no qualifying observation" in item.value for item in app.info)
    assert "Review note for DEMO." in [item.value for item in app.text]
    assert not app.button
    assert not app.get("data_editor")
    assert len(app.get("download_button")) == 1

    app.radio[0].set_value("Readable text").run()
    assert "DEMO release.htm" in app.code[0].value
    assert not app.get("iframe")

    attachment = app.selectbox[0]
    attachment.select(attachment.options[0]).run()
    assert not app.exception
    assert "DEMO primary.htm" in app.code[0].value
    assert app.table[0].value["Value"].tolist() == ["4.60", "9.00", "29.43"]

    filing = app.sidebar.selectbox[0]
    filing.select(filing.options[1]).run()
    assert not app.exception
    assert "NEXT quarter.htm" in app.code[0].value
    assert app.table[0].value["Value"].tolist() == ["-1.20"]
    assert "Review note for NEXT." in [item.value for item in app.text]

    # Returning after widget cleanup must restore the user's primary attachment,
    # rather than resetting to the EX-99.1 default.
    filing = app.sidebar.selectbox[0]
    filing.select(filing.options[0]).run()
    assert not app.exception
    assert "DEMO primary.htm" in app.code[0].value
    app.radio[0].set_value("Formatted HTML").run()
    assert "DEMO primary.htm" in app.get("iframe")[0].proto.srcdoc
    assert _bundle_hashes(dataset_root) == before


def test_download_offers_exact_original_bytes(monkeypatch, dataset_root):
    st = pytest.importorskip("streamlit")
    from finbot_filing_evals.review.dataset import load_dataset

    document = load_dataset(dataset_root).cases[0].documents[1]
    downloads = []
    original = st.download_button

    def capture(*args, **kwargs):
        downloads.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(st, "download_button", capture)
    app = _open_app(monkeypatch, dataset_root)
    assert not app.exception
    assert downloads[0]["data"] == document.read_bytes()
    assert downloads[0]["file_name"] == document.filename
    assert downloads[0]["mime"] == "text/html"
    assert downloads[0]["on_click"] == "ignore"


def test_legacy_component_also_embeds_only_the_sandbox_wrapper(monkeypatch, dataset_root):
    st = pytest.importorskip("streamlit")
    monkeypatch.delattr(st, "iframe", raising=False)
    app = _open_app(monkeypatch, dataset_root)
    assert not app.exception
    wrapper = app.get("iframe")[0].proto.srcdoc
    assert 'sandbox=""' in wrapper
    assert "DEMO release.htm" in wrapper
    assert "window.forbidden" not in wrapper


def test_app_renders_bad_dataset_as_actionable_error(monkeypatch, tmp_path):
    app = _open_app(monkeypatch, tmp_path / "missing")
    assert not app.exception
    assert "Dataset directory is unavailable" in app.error[0].value


def test_app_explains_missing_configuration(monkeypatch):
    testing = pytest.importorskip("streamlit.testing.v1")
    monkeypatch.setattr(sys, "argv", ["review_eps.py"])
    monkeypatch.delenv("FINBOT_DATA_ROOT", raising=False)
    script = Path(__file__).resolve().parents[1] / "scripts/review_eps.py"
    app = testing.AppTest.from_file(script).run()
    assert not app.exception
    assert "Set FINBOT_DATA_ROOT or pass --dataset-root" in app.error[0].value
