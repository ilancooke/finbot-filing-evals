"""Document inspection, filing-wide editing and durable local saves."""

from collections.abc import Sequence
from hashlib import sha256

from .config import parse_dataset_root
from .dataset import ReviewDataset, load_dataset
from .editor import COLUMNS, METRIC_NAMES, validate_rows
from .errors import ReviewError
from .persistence import confirm_case, save_changes, retry_synchronization, synchronization_pending
from .session import EditorDraft, NavigationGuard, adjacent_case
from .viewer import initial_attachment, plain_text_preview, viewer_frame


def _navigation(namespace: str) -> NavigationGuard:
    import streamlit as st

    key = f"{namespace}:navigation"
    if key not in st.session_state:
        st.session_state[key] = NavigationGuard()
    return st.session_state[key]


def _request_filing(namespace: str, target: str, root=None) -> None:
    import streamlit as st

    active_key = f"{namespace}:active_filing"
    active = st.session_state[active_key]
    draft = st.session_state.get(f"{namespace}:{active}:draft")
    if draft is not None:
        editor_key = f"{namespace}:{active}:editor:{draft.generation}"
        if editor_key in st.session_state:
            draft.capture_widget_changes(st.session_state[editor_key])
    # Capture edits arriving in the same event as a selection or navigation click.
    try:
        pending = synchronization_pending(root) if root is not None else st.session_state.get(f"{namespace}:pending", False)
        selected = _navigation(namespace).request(
            active, target, dirty=draft is not None and draft.dirty, pending=pending,
        )
    except ReviewError as error:
        st.session_state[f"{namespace}:save_error"] = str(error)
        selected = active
    st.session_state[active_key] = selected
    st.session_state[f"{namespace}:filing"] = selected


def _change_filing(namespace: str, root=None) -> None:
    import streamlit as st

    _request_filing(namespace, st.session_state[f"{namespace}:filing"], root)


def _discard(namespace: str, root, case_id: str, target: str | None = None) -> None:
    import streamlit as st

    try:
        if synchronization_pending(root):
            raise ReviewError("Synchronization pending. Retry before discarding or navigating.")
        # Read at click time, including saves made by another session.
        current = next(case for case in load_dataset(root).cases if case.case_id == case_id)
        st.session_state[f"{namespace}:{case_id}:draft"].accept_saved(
            current.to_dict()["labels"], current.fingerprint,
        )
        _navigation(namespace).stay()
        if target is not None:
            st.session_state[f"{namespace}:active_filing"] = target
    except ReviewError as error:
        st.session_state[f"{namespace}:save_error"] = str(error)


def _persist(dataset, case, draft, labels, namespace, *, confirm=False, target=None) -> None:
    import streamlit as st

    try:
        action = confirm_case if confirm else save_changes
        saved = action(dataset.root, case.case_id, draft.opened_fingerprint, labels)
        current = next(item for item in saved.dataset.cases if item.case_id == case.case_id)
        draft.accept_saved(current.to_dict()["labels"], current.fingerprint)
        if confirm:
            notice = "Filing confirmed and exports synchronized."
            if target is None:
                notice += " End of filing list — review of the last filing is complete."
        else:
            notice = "Labels saved and exports synchronized. Saved review status: " + current.review_status.replace('_', ' ') + "."
        st.session_state[f"{namespace}:save_notice"] = notice
        _navigation(namespace).stay()
        if target is not None:
            st.session_state[f"{namespace}:active_filing"] = target
        st.rerun()
    except ReviewError as error:
        st.error(str(error))
        if synchronization_pending(dataset.root):
            st.session_state[f"{namespace}:save_error"] = str(error)
            st.rerun()


def _show_dataset(dataset: ReviewDataset, *, pending: bool = False) -> None:
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
    # A successful button action may have moved the active case on the prior run.
    # Set the selector before instantiating its widget, never afterward.
    st.session_state[f"{namespace}:filing"] = case.case_id
    navigation = _navigation(namespace)
    draft_key = f"{namespace}:{case.case_id}:draft"
    if draft_key not in st.session_state:
        st.session_state[draft_key] = EditorDraft(case.to_dict()["labels"], case.fingerprint)
    draft = st.session_state[draft_key]
    if not draft.dirty and draft.opened_fingerprint != case.fingerprint:
        draft.accept_saved(case.to_dict()["labels"], case.fingerprint)
    editor_key = f"{namespace}:{case.case_id}:editor:{draft.generation}"
    if draft.dirty and editor_key not in st.session_state:
        # Switching dataset paths can remove hidden widgets. Keep the independent
        # draft, including partial rows, rather than replacing it with saved input.
        draft.resume()
    st.subheader(f"{case.ticker} · {case.form_type}")
    st.caption(f"{case.filing_id} · Saved review status: {case.review_status.replace('_', ' ').title()}")
    if case.to_dict()['review'].get('reviewed_at_utc'):
        st.caption(f"Confirmed at (UTC): {case.to_dict()['review']['reviewed_at_utc']}")
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
            st.warning("Unsaved changes — leaving this filing will offer Save, Discard or Stay.")
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
    # Callbacks capture editor deltas before resolving navigation requests.
    st.sidebar.selectbox(
        "Filing", options=list(cases), index=list(cases).index(case.case_id),
        key=f"{namespace}:filing", disabled=pending,
        on_change=_change_filing, args=(namespace, dataset.root),
        format_func=lambda key: (
            f"{cases[key].ticker} · {cases[key].form_type} · "
            f"{cases[key].review_status.replace('_', ' ').title()} · {cases[key].filing_id}"
        ),
    )
    st.sidebar.button(
        "Discard changes", disabled=pending or not draft.dirty,
        on_click=_discard, args=(namespace, dataset.root, case.case_id),
        key=f"{namespace}:{case.case_id}:discard",
        help="Restore the current saved labels and clear pending editor changes.",
    )
    if st.sidebar.button(
        "Save changes", disabled=pending or bool(result.errors) or not draft.dirty,
        key=f"{namespace}:{case.case_id}:save",
        help="Save valid corrections without confirming the filing.",
    ):
        _persist(dataset, case, draft, result.labels, namespace)
    previous = adjacent_case(list(cases), case.case_id, -1)
    following = adjacent_case(list(cases), case.case_id, 1)
    st.sidebar.caption(
        "Confirm the entire filing package, including absent metrics. "
        "Empty arrays and explicitly retained unknown start dates are allowed."
    )
    if st.sidebar.button(
        "Confirm and next", disabled=pending or bool(result.errors) or navigation.target is not None,
        key=f"{namespace}:{case.case_id}:confirm",
    ):
        _persist(dataset, case, draft, result.labels, namespace, confirm=True, target=following)
    for label, target in (("Previous", previous), ("Next", following)):
        st.sidebar.button(
            label, disabled=pending or target is None,
            on_click=_request_filing, args=(namespace, target, dataset.root),
            key=f"{namespace}:{case.case_id}:{label.lower()}",
        )
    if navigation.target is not None:
        target = navigation.target
        st.sidebar.warning(f"Leave {case.ticker} for {cases[target].ticker}? Save, Discard or Stay.")
        if st.sidebar.button("Save", disabled=pending or bool(result.errors), key=f"{namespace}:leave_save"):
            _persist(dataset, case, draft, result.labels, namespace, target=target)
        st.sidebar.button(
            "Discard", disabled=pending, on_click=_discard,
            args=(namespace, dataset.root, case.case_id, target), key=f"{namespace}:leave_discard",
        )
        st.sidebar.button("Stay", on_click=navigation.stay, key=f"{namespace}:leave_stay")


def main(argv: Sequence[str] | None = None) -> None:
    import streamlit as st

    st.set_page_config(page_title="EPS dataset review", layout="wide")
    st.title("EPS dataset review")
    st.info(
        "Save changes persists corrections and synchronizes exports. Saving does not confirm a filing. "
        "Confirm and next saves and confirms the whole filing. Unsaved edits are lost when the session ends."
    )
    try:
        root = parse_dataset_root(argv)
        namespace = sha256(str(root.resolve()).encode()).hexdigest()[:16]
        pending = synchronization_pending(root)
        st.session_state[f"{namespace}:pending"] = pending
        save_error = st.session_state.pop(f"{namespace}:save_error", None)
        if save_error:
            st.error(save_error)
        if pending:
            st.warning("Synchronization pending. A save may have committed labels; exports are not yet verified. Retry before further saves or navigation.")
            if st.button("Retry synchronization"):
                try:
                    recovered = retry_synchronization(root)
                    current = next(case for case in recovered.dataset.cases if case.case_id == recovered.case_id)
                    draft = st.session_state.get(f"{namespace}:{current.case_id}:draft")
                    if draft is not None and validate_rows(draft.rows).labels == current.to_dict()["labels"]:
                        draft.accept_saved(current.to_dict()["labels"], current.fingerprint)
                    st.session_state[f"{namespace}:save_notice"] = "Labels saved and exports synchronized."
                    st.rerun()
                except ReviewError as error:
                    st.error(str(error))
        notice = st.session_state.pop(f"{namespace}:save_notice", None)
        if notice:
            st.success(notice)
        _show_dataset(load_dataset(root, validate_counts=not pending), pending=pending)
    except ReviewError as error:
        st.error(str(error))
