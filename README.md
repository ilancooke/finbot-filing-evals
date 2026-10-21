# finbot-filing-evals

This package is being repurposed to evaluate earnings extraction from original
SEC documents collected by `finbot-filings`. The immediate implementation target
is a local Streamlit UI for inspecting documents, correcting reported/adjusted
diluted EPS labels, and confirming a golden dataset for later evaluation.

**Current state:** Step 1 is implemented. A read-only Streamlit app loads and
validates the document EPS draft dataset, with filing/attachment selectors,
plain text document previews, saved EPS values, review notes and status.
Formatted document viewing is next; editing, saving and confirmation are not
implemented yet. The previous screenshot pipeline has been removed.

## Start a new implementation session

Read [ROADMAP.md](ROADMAP.md) for the agreed contracts, sequential steps,
prerequisites, acceptance checks and handoff records. Work on the first incomplete
step after verifying its predecessors. Each session must add focused tests,
run the package checks below, and update the roadmap's status and handoff before
stopping. Update this README as each new command or feature becomes available.
No earlier conversation or temporary build script is required.

Keep new app code under `src/finbot_filing_evals/review/`, with the thin
entry point `scripts/review_eps.py`. The former `golden_dataset/` package and
its tests, prompts, schemas and provider adapters have been removed. Preserve
unrelated uncommitted changes.
Use local files; no model calls, AWS access, downloads, sibling-package imports,
or changes to `finbot-dashboard` are needed for the review UI.

## Document EPS golden dataset

Default location:

```text
$FINBOT_DATA_ROOT/filing-evals/golden/earnings-eps-v1/
├── dataset.json
├── labels.schema.json
├── labels.json
├── labels.parquet
├── labels.metadata.json
├── documents.parquet
├── documents.metadata.json
├── integrity.json
├── REVIEW.md
└── cases/<case_id>/
    ├── case.json
    ├── filing-ready.json
    ├── provenance.json
    ├── documents/<original-filename>.htm
    └── review-text/                         # optional display aid
```

Initially: **13 filing packages, 27 HTML documents, 34 draft observations**
(25 reported and 9 adjusted), spanning 8-K, 6-K, 10-Q and 10-K forms.
These counts describe the initial draft; derive current counts from the files.
All labels currently await human review. Dataset files stay outside Git.

`dataset.json` defines case membership/order and policy. Per-filing `case.json`
files are the authoritative editable labels and review states. Their document
paths are relative to the dataset root, with hashes of unchanged originals.
JSON/Parquet labels, their sidecar metadata and the review guide are derived
exports; label edits require regeneration and integrity refresh. The source
sample in `data/earnings/evaluations/corpora/golden-s3-v1` is a separate workflow;
the review app operates on this new bundle only.

Each filing has separate `reported_diluted_eps` and `adjusted_diluted_eps`
arrays. Each observation contains:

| Field | Meaning |
| --- | --- |
| `value` | Signed decimal string; preserve precision such as `4.60`. |
| `currency` | Original three-letter currency code; no conversion. |
| `period` | Nonblank period label distinguishing quarter, cumulative or year. |
| `period_start` | ISO start date, or null when unresolved. |
| `period_end` | Required ISO end date. |

Include current quarterly and fiscal year-to-date results, or the latest fiscal
year in an annual report. Exclude historical comparisons, guidance, basic EPS,
adjustment components and calculated EPS. An empty metric array means no
qualifying reported figure was identified, not an EPS of zero. No share-unit,
accounting-basis or evidence field is required in extraction targets. Review
notes and source provenance remain separate from those targets.

Known review questions: JNJ's September 27 end date and null starts, ASML/DPZ
fiscal starts, TSM's two reported currencies (USD is per ADR), and excluding JNJ's
separate operationally adjusted variant. Preserve these notes for the reviewer.

If the real bundle is absent, normal development/tests use synthetic temporary
fixtures with this contract. Do not contact SEC/S3 to create test inputs or
silently substitute the earlier EPS corpus.

## Review workflow

The current read-only screen displays original document text beside filing-wide
labels. Select a filing in the sidebar and an attachment in the document pane.
Values remain decimal strings; unknown start dates and review notes stay visible.
The preview strips markup, scripts and styles; it does not preserve table layout.
Formatted, isolated HTML viewing belongs to Step 2.

The UI will show a document beside the filing-wide editable EPS table, with
attachment switching, add/delete rows, Save changes, and Confirm and next.
Saving corrections and confirming a filing are distinct actions. Confirmation
covers the complete package; changing a confirmed label reopens its review.
Saved progress must survive restart. The dataset becomes human-reviewed only
when all its filings have been confirmed.

The setup and launch commands below work now. Step 4 will enable durable
saves and export synchronization; Step 5 will enable confirmation; Step 6 will
add automatic catalog refresh for real shared-dataset saves. All write tests and
browser QA use disposable copies.

## Setup and launch

Python 3.12 or newer is required. Check the interpreter version before creating
the repo-local environment. If an existing `.venv` points to an interpreter
that is no longer installed, recreate that environment with a working Python
>=3.12; do not borrow another package's virtualenv.

```bash
python3 -m venv .venv
source .venv/bin/activate
.venv/bin/python -m pip install -e '.[dev,review]'
```

Set the shared finbot data root in your shell. A local `.env` may be used by
your shell tooling, but the package deliberately does not parse `.env` files
or depend on a dotenv library.

```bash
export FINBOT_DATA_ROOT=/Users/ilan/workspace/finbot/data
.venv/bin/python -m streamlit run scripts/review_eps.py --server.address 127.0.0.1
```

Open the localhost URL printed by Streamlit (normally `http://127.0.0.1:8501`).
From the repository root, override the dataset explicitly with:

```bash
.venv/bin/python -m streamlit run scripts/review_eps.py --server.address 127.0.0.1 -- --dataset-root /path/to/dataset-copy
```

`--dataset-root` takes precedence over `FINBOT_DATA_ROOT`. Otherwise the app
appends `filing-evals/golden/earnings-eps-v1` to the shared data root. Missing
configuration, unavailable files or failed validation show an error; the app
never creates a dataset or substitutes another corpus. It writes no dataset files.

## Dataset foundation

`review.config.resolve_dataset_root()` resolves configuration without side effects.
`review.dataset.load_dataset(root)` validates the manifest and cases in listed
order, the packaged `earnings_eps.v1` label contract, filing snapshots, complete
artifact membership, original document sizes/hashes and confined relative paths
(including symlinks). It reads authoritative inputs rather than derived exports;
full bundle/export synchronization checks belong to Step 4.

The immutable `ReviewDataset`, `ReviewCase`, `SourceDocument` and `Observation`
models retain original decimal strings and nullable dates. Dataset/case
`to_dict()` returns an independent copy preserving unknown metadata. Their
`fingerprint` is the SHA-256 of exact manifest/case bytes for later stale-edit
detection. `SourceDocument.read_bytes()` rechecks confinement and source integrity.
`review.validation.validate_labels()` provides UI-independent schema, date-order
and duplicate-period validation; failures raise `ReviewError` with context.

## Checks

The core loader requires `jsonschema`. The `dev` extra installs pytest; the
optional `review` extra installs Streamlit, pandas and PyArrow. Loading a dataset
does not import the UI dependencies. The former screenshot tests were removed;
the new tests cover the dataset contract, path/source validation and app shell.

Compile and verify the installed package:

```bash
.venv/bin/python -m compileall -q src tests
.venv/bin/python -c 'import finbot_filing_evals; print(finbot_filing_evals.__version__)'
```

Run the test suite for every step:

```bash
.venv/bin/python -m pytest
```

Tests use temporary synthetic fixtures, block network connections, and avoid
shared-data writes. Streamlit AppTest checks run when the `review` extra is
installed; install both extras to run the complete suite. Real-sample smoke checks
are separate so a missing shared bundle does not break normal tests.

To verify the installable distribution, build a wheel outside source control:

```bash
.venv/bin/python -m pip wheel --no-deps --wheel-dir /private/tmp/finbot-filing-evals-wheels .
```

No previous-work archive or backup was created during cleanup. The shared data
root, original documents and draft labels were not modified.
