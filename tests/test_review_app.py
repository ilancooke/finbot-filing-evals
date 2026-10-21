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


def _draft(app, root):
    namespace = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
    case_id = app.session_state[f"{namespace}:active_filing"]
    return namespace, case_id, app.session_state[f"{namespace}:{case_id}:draft"]


def _edit(app, root, *, edits=None, additions=None, deletions=None):
    # AppTest has no data-editor interaction API. Supply the widget's public
    # edit/add/delete state, exercising the real data_editor and its reruns.
    namespace, case_id, draft = _draft(app, root)
    key = f"{namespace}:{case_id}:editor:{draft.generation}"
    app.session_state[key] = {
        "edited_rows": edits or {}, "added_rows": additions or [],
        "deleted_rows": deletions or [],
    }
    return app.run()


def test_app_switches_filings_and_attachments_without_writes(monkeypatch, dataset_root):
    before = _bundle_hashes(dataset_root)
    app = _open_app(monkeypatch, dataset_root)
    assert not app.exception
    assert not app.error
    assert "2 filings · 3 documents · 4 EPS observations" in [item.value for item in app.caption]
    assert "DEMO release.htm" in app.get("iframe")[0].proto.srcdoc
    assert "sandbox=\"\"" in app.get("iframe")[0].proto.srcdoc
    table = app.dataframe[0].value
    assert table["Value"].tolist() == ["4.60", "9.00", "29.43"]
    assert table["Start"].fillna("Unknown").tolist() == ["Unknown", "2026-01-01", "Unknown"]
    assert any("no qualifying observation" in item.value for item in app.info)
    assert "Review note for DEMO." in [item.value for item in app.text]
    assert app.sidebar.button[0].label == "Discard changes"
    assert app.sidebar.button[0].disabled
    assert len(app.get("download_button")) == 1

    app.radio[0].set_value("Readable text").run()
    assert "DEMO release.htm" in app.code[0].value
    assert not app.get("iframe")

    attachment = app.selectbox[0]
    attachment.select(attachment.options[0]).run()
    assert not app.exception
    assert "DEMO primary.htm" in app.code[0].value
    assert app.dataframe[0].value["Value"].tolist() == ["4.60", "9.00", "29.43"]

    filing = app.sidebar.selectbox[0]
    filing.select(filing.options[1]).run()
    assert not app.exception
    assert "NEXT quarter.htm" in app.code[0].value
    assert app.dataframe[0].value["Value"].tolist() == ["-1.20"]
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


def test_pending_edits_survive_attachment_reruns_and_require_discard(monkeypatch, dataset_root):
    before = _bundle_hashes(dataset_root)
    app = _open_app(monkeypatch, dataset_root)
    _edit(app, dataset_root, edits={0: {"Value": "-4.60", "Start": ""}})
    assert not app.exception
    assert not app.error
    assert _draft(app, dataset_root)[2].rows[0]["Value"] == "-4.60"
    assert app.sidebar.selectbox[0].disabled
    assert any("Unsaved changes" in item.value for item in app.warning)
    app.selectbox[0].select(app.selectbox[0].options[0]).run()
    app.radio[0].set_value("Readable text").run()
    app.run()
    assert not app.exception
    assert "DEMO primary.htm" in app.code[0].value
    assert _draft(app, dataset_root)[2].rows[0]["Value"] == "-4.60"
    assert "Review note for DEMO." in [item.value for item in app.text]
    from streamlit.testing.v1.errors import AppTestError

    with pytest.raises(AppTestError, match="disabled"):
        app.sidebar.selectbox[0].select(app.sidebar.selectbox[0].options[1])
    assert "DEMO" in app.subheader[0].value
    assert _draft(app, dataset_root)[2].dirty
    app.sidebar.button[0].click().run()
    assert not app.exception
    assert not app.sidebar.selectbox[0].disabled
    assert not _draft(app, dataset_root)[2].dirty
    assert _draft(app, dataset_root)[2].rows[0]["Value"] == "4.60"
    app.sidebar.selectbox[0].select(app.sidebar.selectbox[0].options[1]).run()
    assert "NEXT" in app.subheader[0].value
    app.sidebar.selectbox[0].select(app.sidebar.selectbox[0].options[0]).run()
    assert _draft(app, dataset_root)[2].rows[0]["Value"] == "4.60"
    assert _bundle_hashes(dataset_root) == before


def test_partial_additions_errors_and_deleting_all_rows(monkeypatch, dataset_root):
    before = _bundle_hashes(dataset_root)
    app = _open_app(monkeypatch, dataset_root)
    _edit(app, dataset_root, additions=[{"Value": "4.60"}])
    assert not app.exception
    assert any("Row 4" in error.value for error in app.error)
    assert app.sidebar.selectbox[0].disabled
    app.sidebar.button[0].click().run()
    _edit(app, dataset_root, deletions=[0, 1, 2])
    assert not app.exception
    assert not app.error
    assert _draft(app, dataset_root)[2].rows == []
    assert sum("empty array" in item.value for item in app.info) == 2
    assert app.sidebar.selectbox[0].disabled
    app.radio[0].set_value("Readable text").run()
    assert _draft(app, dataset_root)[2].rows == []
    # Restart shows saved labels, not session-only changes.
    restarted = _open_app(monkeypatch, dataset_root)
    assert len(_draft(restarted, dataset_root)[2].rows) == 3
    assert _bundle_hashes(dataset_root) == before


def test_empty_table_can_add_and_remove_observation(monkeypatch, dataset_root, case_file):
    import json
    from conftest import save_json

    case = json.loads(case_file.read_text())
    case["labels"] = {"reported_diluted_eps": [], "adjusted_diluted_eps": []}
    save_json(case_file, case)
    manifest_path = dataset_root / "dataset.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["observation_count"] = 1
    save_json(manifest_path, manifest)
    before = _bundle_hashes(dataset_root)
    app = _open_app(monkeypatch, dataset_root)
    assert not app.exception
    assert app.dataframe[0].value.empty
    _edit(app, dataset_root, additions=[{
        "EPS type": "Adjusted diluted EPS", "Value": "-0.50", "Currency": "USD",
        "Period": "Q3 2026", "Start": None, "End": "2026-09-30",
    }])
    assert not app.exception
    assert not app.error
    assert _draft(app, dataset_root)[2].rows[0]["Value"] == "-0.50"
    app.radio[0].set_value("Readable text").run()
    assert _draft(app, dataset_root)[2].rows[0]["Value"] == "-0.50"
    _edit(app, dataset_root)  # deleting an added row removes its addition delta
    assert not app.exception
    assert not app.error
    assert not _draft(app, dataset_root)[2].dirty
    assert not app.sidebar.selectbox[0].disabled
    assert _bundle_hashes(dataset_root) == before


def test_drafts_are_isolated_between_dataset_paths(monkeypatch, make_dataset):
    first = make_dataset("first")
    second = make_dataset("second")
    app = _open_app(monkeypatch, first)
    _edit(app, first, edits={0: {"Value": "0.00"}})
    monkeypatch.setattr(sys, "argv", ["review_eps.py", "--dataset-root", str(second)])
    app.run()
    assert not app.exception
    assert _draft(app, second)[2].rows[0]["Value"] == "4.60"
    assert not _draft(app, second)[2].dirty


def test_delayed_filing_event_cannot_bypass_dirty_guard(monkeypatch, labels):
    st = pytest.importorskip("streamlit")
    from finbot_filing_evals.review.app import _change_filing
    from finbot_filing_evals.review.session import EditorDraft

    draft = EditorDraft(labels, "fingerprint")
    state = {"test:active_filing": "first", "test:filing": "second", "test:first:draft": draft}
    monkeypatch.setattr(st, "session_state", state)
    # Both events arrived together, before the script captured the editor return.
    state["test:first:editor:0"] = {
        "edited_rows": {0: {"Value": "unfinished"}}, "added_rows": [], "deleted_rows": [],
    }
    assert not draft.dirty
    _change_filing("test")
    assert state["test:active_filing"] == state["test:filing"] == "first"
    assert draft.dirty
    draft.discard()
    state["test:filing"] = "second"
    _change_filing("test")
    assert state["test:active_filing"] == "second"


def _button(app, label):
    return next(button for button in app.button if button.label == label)


def test_save_restarts_with_durable_labels_and_unlocked_navigation(monkeypatch, writable_dataset):
    import json
    from finbot_filing_evals.review.dataset import load_dataset
    from finbot_filing_evals.review.persistence import verify_bundle

    root = writable_dataset
    app = _open_app(monkeypatch, root)
    assert _button(app, 'Save changes').disabled
    _edit(app, root, edits={0: {'Value': '-4.60'}})
    assert not _button(app, 'Save changes').disabled
    _button(app, 'Save changes').click().run()
    assert not app.exception
    assert not app.error
    assert app.success
    assert not _draft(app, root)[2].dirty
    assert not app.sidebar.selectbox[0].disabled
    assert _draft(app, root)[2].rows[0]['Value'] == '-4.60'
    restarted = _open_app(monkeypatch, root)
    assert _draft(restarted, root)[2].rows[0]['Value'] == '-4.60'
    assert not _draft(restarted, root)[2].dirty
    dataset = load_dataset(root)
    assert dataset.cases[0].review_status == 'unreviewed'
    assert json.loads((root / 'labels.json').read_text())[0]['value'] == '-4.60'
    verify_bundle(dataset)


def test_save_rejects_invalid_rows_and_preserves_conflicting_draft(monkeypatch, writable_dataset):
    from finbot_filing_evals.review.persistence import save_changes
    from finbot_filing_evals.review.dataset import load_dataset

    root = writable_dataset
    app = _open_app(monkeypatch, root)
    _edit(app, root, additions=[{'Value': 'bad'}])
    assert _button(app, 'Save changes').disabled
    _button(app, 'Discard changes').click().run()
    _edit(app, root, edits={0: {'Value': '8.00'}})
    case = load_dataset(root).cases[0]
    labels = case.to_dict()['labels']
    labels['reported_diluted_eps'][0]['value'] = '7.00'
    save_changes(root, case.case_id, case.fingerprint, labels)
    _button(app, 'Save changes').click().run()
    assert not app.exception
    assert any('Pending edits retained' in error.value for error in app.error)
    assert _draft(app, root)[2].rows[0]['Value'] == '8.00'
    _button(app, 'Discard changes').click().run()
    assert _draft(app, root)[2].rows[0]['Value'] == '7.00'
    assert not _draft(app, root)[2].dirty


def test_pending_save_is_visible_after_restart_and_retry(monkeypatch, writable_dataset):
    from finbot_filing_evals.review import persistence as p

    root = writable_dataset
    app = _open_app(monkeypatch, root)
    _edit(app, root, deletions=[0, 1, 2])
    atomic = p._atomic
    def fail(root, name, raw):
        if name == 'labels.json': raise OSError('injected export failure')
        return atomic(root, name, raw)
    with monkeypatch.context() as m:
        m.setattr(p, '_atomic', fail)
        _button(app, 'Save changes').click().run()
    assert not app.exception
    assert any('Labels saved, exports need retry' in error.value for error in app.error)
    assert any('Synchronization pending' in item.value for item in app.warning)
    assert app.sidebar.selectbox[0].disabled
    assert _button(app, 'Save changes').disabled
    assert _draft(app, root)[2].dirty
    restarted = _open_app(monkeypatch, root)
    assert not restarted.exception
    assert restarted.sidebar.selectbox[0].disabled
    assert any('Synchronization pending' in item.value for item in restarted.warning)
    _button(app, 'Retry synchronization').click().run()
    assert not app.exception
    assert not app.error
    assert app.success
    assert not p.synchronization_pending(root)
    assert not _draft(app, root)[2].dirty
    assert not app.sidebar.selectbox[0].disabled
    assert _draft(app, root)[2].rows == []
