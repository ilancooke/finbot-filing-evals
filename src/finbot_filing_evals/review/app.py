"""Step 1 inspection shell: no editing, saving, confirmation or active HTML."""

from collections.abc import Sequence
from hashlib import sha256
from html.parser import HTMLParser

from .config import parse_dataset_root
from .dataset import ReviewDataset, load_dataset
from .errors import ReviewError
from .validation import METRICS

_METRIC_NAMES = {
    "reported_diluted_eps": "Reported diluted EPS",
    "adjusted_diluted_eps": "Adjusted diluted EPS",
}


class _PreviewText(HTMLParser):
    """Extract plain text only; original markup is never sent to an HTML renderer."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"head", "script", "style", "ix:header"}:
            self.ignored.append(tag)
        elif not self.ignored and tag in {"p", "div", "tr", "br", "h1", "h2", "h3", "section"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self.ignored:
            if tag == self.ignored[-1]:
                self.ignored.pop()
        elif tag in {"p", "div", "tr", "h1", "h2", "h3", "section"}:
            self.parts.append("\n")
        elif tag in {"td", "th"}:
            self.parts.append(" | ")

    def handle_data(self, data: str) -> None:
        if not self.ignored and data.strip():
            self.parts.append(data.strip() + " ")


def plain_text_preview(raw: bytes) -> str:
    """Best-effort readable text, never code/HTML execution or external loading."""
    parser = _PreviewText()
    parser.feed(raw.decode("utf-8", errors="replace"))
    return "\n".join(
        " ".join(line.split()) for line in "".join(parser.parts).splitlines() if line.strip()
    )


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
    selected_id = st.sidebar.selectbox(
        "Filing", options=list(cases), key=f"{namespace}:filing",
        format_func=lambda key: (
            f"{cases[key].ticker} · {cases[key].form_type} · "
            f"{cases[key].review_status.replace('_', ' ').title()} · {cases[key].filing_id}"
        ),
    )
    case = cases[selected_id]
    st.subheader(f"{case.ticker} · {case.form_type}")
    st.caption(f"{case.filing_id} · Saved review status: {case.review_status.replace('_', ' ').title()}")
    left, right = st.columns([3, 2])
    with left:
        st.subheader("Document")
        documents = {document.artifact_id: document for document in case.documents}
        artifact_id = st.selectbox(
            "Attachment", options=list(documents), key=f"{namespace}:{case.case_id}:attachment",
            format_func=lambda key: f"{documents[key].document_type or 'Document'} · {documents[key].filename}",
        )
        document = documents[artifact_id]
        st.caption("Plain text preview. Formatted document display is planned for Step 2.")
        text = plain_text_preview(document.read_bytes())
        if text:
            st.code(text, language=None, wrap_lines=True, height=620)
        else:
            st.info("No readable text was found in this document.")
    with right:
        st.subheader("Filing EPS values")
        st.caption("These saved labels cover all attachments in the selected filing.")
        rows = [
            {
                "EPS type": _METRIC_NAMES[metric], "Value": item.value,
                "Currency": item.currency, "Period": item.period,
                "Start": item.period_start or "Unknown", "End": item.period_end,
            }
            for metric in METRICS for item in case.labels[metric]
        ]
        if rows:
            st.table(pd.DataFrame(rows, dtype="string"))
        for metric in METRICS:
            if not case.labels[metric]:
                st.info(f"{_METRIC_NAMES[metric]}: no qualifying observation is currently labeled.")
        missing_starts = sum(item.period_start is None for metric in METRICS for item in case.labels[metric])
        if missing_starts:
            st.warning(f"{missing_starts} observations have an unknown start date. No date has been filled in.")
        if case.notes:
            st.subheader("Review notes")
            for note in case.notes:
                st.text(note)


def main(argv: Sequence[str] | None = None) -> None:
    import streamlit as st

    st.set_page_config(page_title="EPS dataset review", layout="wide")
    st.title("EPS dataset review")
    st.info("Read-only inspection. Editing, saving and confirmation are planned for later steps.")
    try:
        _show_dataset(load_dataset(parse_dataset_root(argv)))
    except ReviewError as error:
        st.error(str(error))
