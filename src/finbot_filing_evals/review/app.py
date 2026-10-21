"""Document inspection and session-only filing-wide label editing."""

from collections.abc import Sequence
from hashlib import sha256

from .config import parse_dataset_root
from .dataset import ReviewDataset, load_dataset
from .editor import COLUMNS, METRIC_NAMES, validate_rows
from .errors import ReviewError
from .session import EditorDraft
from .viewer import initial_attachment, plain_text_preview, viewer_frame


def _change_filing(namespace: str) -> None:
    import streamlit as st

    active_key = f"{namespace}:active_filing"
    active = st.session_state[active_key]
    draft = st.session_state.get(f"{namespace}:{active}:draft")
    if draft is not None:
        editor_key = f"{namespace}:{active}:editor:{draft.generation}"
        if editor_key in st.session_state:
            draft.capture_widget_changes(st.session_state[editor_key])
    # Also guard delayed selector events arriving after a table edit.
    if draft is not None and draft.dirty:
        st.session_state[f"{namespace}:filing"] = active
    else:
        st.session_state[active_key] = st.session_state[f"{namespace}:filing"]


def _show_dataset(dataset: ReviewDataset) -> None:
    # UI dependencies stay optional: loading/validating a dataset does not need them.
    import pandas as pd
    import streamlit as st

    st.caption(
        f"{len(dataset.cases)} filings · {dataset.document_count} documents · "
        f"{dataset.observation_count} EPS observations"
    )
    namespace = sha256(str(dataset.root).encode()).hexdigest()[:16]
    cases = {case.case_id: case for case in dataset.cases}
    active_key = f"{namespace}:active_filing"
    if st.session_state.get(active_key) not in cases:
        st.session_state[active_key] = next(iter(cases))
    case = cases[st.session_state[active_key]]
    draft_key = f"{namespace}:{case.case_id}:draft"
    if draft_key not in st.session_state:
        st.session_state[draft_key] = EditorDraft(case.to_dict()["labels"], case.fingerprint)
    draft = st.session_state[draft_key]
    st.subheader(f"{case.ticker} · {case.form_type}")
    st.caption(f"{case.filing_id} · Saved review status: {case.review_status.replace('_', ' ').title()}")
    left, right = st.columns([3, 2])
    with left:
        st.subheader("Document")
        documents = {document.artifact_id: document for document in case.documents}
        # Keep a non-widget state key: Streamlit removes hidden widget state
        # when another filing is selected, even with case-specific widget keys.
        selection_key = f"{namespace}:{case.case_id}:selected_attachment"
        saved_attachment = st.session_state.get(selection_key, initial_attachment(case.documents))
        options = list(documents)
        artifact_id = st.selectbox(
            "Attachment", options=options,
            index=options.index(saved_attachment) if saved_attachment in documents else 0,
            key=f"{namespace}:{case.case_id}:attachment",
            format_func=lambda key: f"{documents[key].document_type or 'Document'} · {documents[key].filename}",
        )
        st.session_state[selection_key] = artifact_id
        document = documents[artifact_id]
        raw = document.read_bytes()
        st.caption(
            "Display-only HTML with tables and inline formatting. Scripts, links and external assets "
            "are disabled; images and stylesheets may be missing. Layout may differ from the original."
        )
        mode = st.radio(
            "Document view", ["Formatted HTML", "Readable text"], horizontal=True,
            key=f"{namespace}:document_view",
        )
        if mode == "Formatted HTML":
            # Embed only our wrapper, never raw source. The inner frame has no
            # sandbox permissions, independent of Streamlit's outer frame.
            if hasattr(st, "iframe"):
                st.iframe(viewer_frame(raw), height=700)
            else:  # Compatibility with the supported Streamlit 1.50 releases.
                import streamlit.components.v1 as components

                components.html(viewer_frame(raw), height=700, scrolling=False)
        else:
            text = plain_text_preview(raw)
            if text:
                st.code(text, language=None, wrap_lines=True, height=680)
            else:
                st.info("No readable text was found in this document.")
        st.download_button(
            "Download original HTML", data=raw, file_name=document.filename,
            mime="text/html", on_click="ignore",
            key=f"{namespace}:{case.case_id}:{artifact_id}:download",
            help="Unmodified source file. Viewer protections apply only inside this app.",
        )
    with right:
        st.subheader("Filing EPS values")
        st.caption(
            "These labels cover all attachments in the selected filing. Add rows at the bottom; "
            "select rows to delete them. Values are decimal strings; dates use YYYY-MM-DD. "
            "A blank start date is allowed. An entirely blank new row is unused."
        )
        # Keep the widget input stable: feeding its output back as input would
        # apply the same add/delete deltas twice or reset edits on later reruns.
        edited = st.data_editor(
            pd.DataFrame(draft.base_rows, columns=COLUMNS, dtype="string"),
            num_rows="dynamic", hide_index=True, width="stretch",
            column_config={
                "EPS type": st.column_config.SelectboxColumn(
                    "EPS type", options=list(METRIC_NAMES.values()), width="medium",
                ),
                **{column: st.column_config.TextColumn(column) for column in COLUMNS[1:]},
            },
            key=f"{namespace}:{case.case_id}:editor:{draft.generation}",
        )
        draft.rows = edited.to_dict("records")  # nullable string dtype exports blanks as None
        result = validate_rows(draft.rows)
        if draft.dirty:
            st.warning("Unsaved changes — session only. Discard changes before switching filings.")
        else:
            st.caption("No unsaved changes. Table values match the saved labels.")
        if draft.opened_fingerprint != case.fingerprint:
            st.warning("The saved case changed outside this session. This draft still uses the opened version.")
        for error in result.errors:
            st.error(error)
        if not result.errors:
            st.caption("Pending labels are valid.")
            for metric, name in METRIC_NAMES.items():
                if not result.labels[metric]:
                    st.info(f"{name}: no qualifying observation is currently labeled (empty array).")
        if result.missing_starts:
            numbers = ", ".join(map(str, result.missing_starts))
            st.warning(f"Unknown start date in row(s) {numbers}. You may retain these blanks; no date has been filled in.")
        if case.notes:
            st.subheader("Review notes")
            for note in case.notes:
                st.text(note)
    # Render after reading the editor so the selector is disabled in the very
    # same response that first shows unsaved changes, including invalid rows.
    st.sidebar.selectbox(
        "Filing", options=list(cases), index=list(cases).index(case.case_id),
        key=f"{namespace}:filing", disabled=draft.dirty,
        on_change=_change_filing, args=(namespace,),
        format_func=lambda key: (
            f"{cases[key].ticker} · {cases[key].form_type} · "
            f"{cases[key].review_status.replace('_', ' ').title()} · {cases[key].filing_id}"
        ),
    )
    st.sidebar.button(
        "Discard changes", disabled=not draft.dirty, on_click=draft.discard,
        key=f"{namespace}:{case.case_id}:discard",
        help="Restore the labels opened from disk. All edits in this session are temporary.",
    )
    if draft.dirty:
        st.sidebar.caption("Filing selection is locked until you explicitly discard pending changes.")


def main(argv: Sequence[str] | None = None) -> None:
    import streamlit as st

    st.set_page_config(page_title="EPS dataset review", layout="wide")
    st.title("EPS dataset review")
    st.info(
        "Session-only editing. Dataset files are unchanged; edits are lost when this session ends. "
        "Saving and confirmation are not available yet."
    )
    try:
        _show_dataset(load_dataset(parse_dataset_root(argv)))
    except ReviewError as error:
        st.error(str(error))
