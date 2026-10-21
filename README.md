# finbot-filing-evals

This package provides a local Streamlit UI for inspecting original SEC documents
collected by `finbot-filings`, correcting reported/adjusted diluted EPS labels,
and confirming a golden dataset for later extraction evaluation.

**Current state:** Steps 1–7 are complete. A local Streamlit app loads and
validates the document EPS draft dataset, with filing/attachment selectors,
isolated formatted HTML viewing, readable text fallback, original-file downloads,
EPS editing, row validation, review notes, saved status and **Save changes**.
Saves and confirmation include backups, synchronized exports, integrity refresh
and restart-safe recovery. **Confirm and next**, previous/next navigation and
Save/Discard/Stay guards are available. Saved review progress and automatic catalog
refresh for canonical saves are implemented, with durable pending status and retry.
The complete review workflow has been verified in Firefox on a disposable bundle
copy, including restart, stale-save refusal and interrupted-save recovery.
See [the operating checklist](docs/REVIEW_QA.md) for repeatable verification.
The previous screenshot pipeline has been removed.

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
or changes to `finbot-dashboard` are needed for the review UI. Catalog refresh
uses the sibling repository's CLI as a subprocess, without importing its code.

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

The current screen displays a formatted derivative of the original
HTML beside filing-wide labels. Select a filing in the sidebar and an attachment
in the document pane. The initial attachment is EX-99.1 when available, otherwise
the first manifest artifact. Attachment choices survive switching away and back
within the current session. Labels cover the entire filing package; they need
not appear in the currently selected attachment. Values remain decimal strings;
unknown start dates and review notes stay visible.

Edit the single **Filing EPS values** table to change EPS type, value, currency,
period or dates. Add a row at the bottom, or select rows to delete them. Both
metrics can be empty, including deleting the last observation. A wholly blank new
row is unused; partial rows show errors with their one-based table row number.
Use decimal strings such as `4.60` or `-0.50`, uppercase three-letter currencies
and ISO `YYYY-MM-DD` dates. Blank starts remain null and are highlighted; end dates
are required. Calendar dates, date order and duplicate periods are validated.

Edits survive app reruns, attachment changes and document view changes within the
session. **Unsaved changes** includes invalid/partial rows. Select a filing or use
**Previous**/**Next** to navigate in manifest order. When leaving with edits,
the app stays on the current filing and offers **Save**, **Discard** or **Stay**:
Save persists valid corrections, then moves; Discard reloads the latest saved
labels, clears the old editor state, then moves; Stay keeps the pending edits on
the current filing. Invalid rows disable Save until corrected, while Discard and
Stay remain available. Attachment changes preserve edits without a prompt.

**Save changes** and **Discard changes** also work without leaving the current
filing. Returning all values to their saved state clears the unsaved indicator.
Review notes and saved status are shown separately and are not edited by the
table. Drafts and navigation requests are isolated by dataset path and filing.
Restarting opens the first filing in manifest order with its saved labels/status;
unsaved edits and navigation requests are lost when the session ends.

Choose **Readable text** for text extracted directly from the original, without
requiring precomputed `review-text/` files. **Download original HTML** returns
the exact source bytes and filename. The app's viewer protections apply inside
the app; downloaded originals are unchanged.

The formatted viewer preserves nested tables, cell spans, typography, alignment,
and allowed inline CSS. HTML5 parsing and allowlist sanitization remove active
elements, resource attributes, event handlers and unsafe CSS. The result runs
inside an iframe with an empty sandbox and a Content Security Policy blocking
scripts, network resources, forms and base URLs. Only this generated wrapper,
never raw filing HTML, is passed to Streamlit's embedding API. Links are inert,
images show available alt text, and external stylesheets, images and fonts are
not fetched. Source bytes are never changed. Missing assets and removed styling
mean this is not a pixel-identical rendering; wide tables can require horizontal
scrolling. Use text fallback if a source layout is difficult to read.

**Save changes** persists corrections without confirming an unreviewed filing.
Changing labels of an already confirmed case resets it to unreviewed and clears
its confirmation timestamp. A service-level no-op save preserves confirmation;
the UI disables Save changes when nothing changed.

**Confirm and next** saves valid labels, sets the filing status to `human_reviewed`
and records the writer's current UTC timestamp. Confirmation covers the entire
selected filing package, including completeness and absent metrics. Valid empty
arrays and explicitly retained unknown start dates can be confirmed; their meaning
and review notes remain visible. A fresh confirmation updates the timestamp even
if the labels were already saved. On success, the app moves to the next filing in
manifest order. Confirming the last filing stays there and shows an end-of-list
completion message without wrapping or implying earlier filings were confirmed.
The saved status and confirmation timestamp are restored after restart.

Failed saves or confirmations retain the current filing and draft. Pending
synchronization blocks further writes and filing navigation. Retry synchronization
finishes the recorded action, including its original confirmation timestamp, and
stays on the current filing; navigation requires another explicit action. A
pending Save/Discard/Stay destination is retained within the session. After a
successful synchronized canonical save or retry, the app attempts catalog refresh.

## Saved progress and catalog refresh

The sidebar shows saved reviewed/unreviewed filing counts, a progress bar, overall
state and an expandable list of filing statuses in manifest order. These come
from authoritative saved cases, including filings with no observations. Unsaved
edits do not change progress. Confirmation increases progress; saving changed
labels on a confirmed filing makes it unreviewed again. Overall state is
Unreviewed, In Progress or Human Reviewed for none, some or all filings confirmed.
Progress survives restart. During interrupted saves it is labeled as saved case
progress with exports pending synchronization.

After **Save changes**, navigation's **Save**, **Confirm and next**, or successful
**Retry synchronization**, the app attempts catalog refresh for the canonical
`$FINBOT_DATA_ROOT/filing-evals/golden/earnings-eps-v1` bundle. No-op saves do not
launch it. Refresh is enabled only when FINBOT_DATA_ROOT is set and the resolved
dataset path equals that canonical path. An explicit `--dataset-root` pointing
there also qualifies; any other copy, including temporary fixtures, disables
refresh and its retry button. Setting `--catalog-repo` does not enable copies.

By default, the app uses the sibling `finbot-catalog` repository's
`.venv/bin/python` and `scripts/build_catalog.py --data-root <FINBOT_DATA_ROOT>`.
It passes an argument list without a shell, uses the catalog repository as its
working directory, and limits each attempt to 60 seconds. The catalog must have
its own working environment installed as described in its README. Override its
location when needed, including when launching from an installed wheel:

```bash
.venv/bin/python -m streamlit run scripts/review_eps.py --server.address 127.0.0.1 -- --catalog-repo /path/to/finbot-catalog
```

Opening, editing, discarding and ordinary navigation never launch the catalog.
Missing/broken tooling, nonzero exits, timeouts and receipt-write failures leave
saved labels intact and show **Catalog refresh pending**. Successful synchronized
saves still complete their requested navigation. Use **Retry catalog refresh**
after fixing the catalog environment; this neither saves edits nor navigates.
Dataset synchronization must finish first. For CLI diagnostics, run from the
catalog repository using its own environment:

```bash
.venv/bin/python scripts/build_catalog.py --data-root /path/to/finbot/data
```

Catalog state is separate from dataset synchronization. A receipt under
`.review/catalog-refresh.json` records a successful bundle integrity digest,
shared-root path and UTC refresh time, or a pending attempt. A moved bundle's
receipt does not establish freshness for a different shared root. A saved review
transaction without a
matching successful receipt remains pending after restart, including a process
exit between saving and starting refresh. A missing receipt with no review
transactions means freshness is unknown. The writer lock covers refresh and
receipt replacement so concurrent review saves cannot be acknowledged by mistake.
There is no automatic retry on app open. Success means this app refreshed that
saved bundle revision; it does not certify freshness of unrelated shared data.

## Durable saves, backups and recovery

Saving requires a complete bundle, including its existing integrity manifest,
source/acquisition snapshots and JSON/Parquet exports. Before writing, the app
checks all bundle hashes, source manifests, original documents and export agreement.
Unexpected changes are refused. A case fingerprint is checked under a local
dataset writer lock; a stale session keeps its pending edits and cannot overwrite
another save. Use Discard changes to reload the latest saved labels, then reapply
any desired corrections.

The writer stages and validates all replacements, preserves the prior case bytes,
records recovery state, atomically replaces the case and each derived file, then
refreshes `integrity.json` last. It rebuilds `labels.json`, `labels.parquet`,
`labels.metadata.json`, dataset counts/review state and `REVIEW.md`. Values and
dates remain strings, including null starts and trailing zeroes. Creation times,
upstream metadata, review notes and acquisition facts are retained; modification
and export-generation timestamps are updated. Original documents, source metadata,
provenance, acquisition snapshots and the label schema are never rewritten.

Operational files are retained under the dataset's `.review/` directory:

```text
.review/
├── writer.lock
├── pending.json                   # present only while synchronization is pending
├── catalog-refresh.json           # canonical catalog attempt/success receipt
└── <transaction-id>/
    ├── case.before.json           # exact prior case bytes
    └── 0, 1, ...                  # staged replacement bytes
```

`.review/` and `integrity.json` itself are explicitly excluded from current-bundle
integrity hashing. Locks use POSIX `flock` on the local filesystem (macOS/Linux),
release on process exit, and are separate from the retained lock filename.
Transaction directories and backups are retained without automatic pruning.

If saving fails, the app distinguishes **Nothing saved** from **Labels saved,
exports need retry**. A durable pending marker keeps saves and filing navigation
blocked, including after restart. Choose **Retry synchronization** to finish the
recorded save under the same lock. Recovery checks original and expected replacement
hashes, rebuilds exports from authoritative cases and the recorded intended case,
and clears the marker only after final agreement. It can finish a save interrupted
before the case commit as well as one interrupted afterward. Pending edits remain
in the current session; an uncommitted intended case also remains staged on disk.

Do not remove a pending marker or manually refresh hashes to bypass an error.
Unexpected source, case, export or staging changes cause recovery to refuse writes;
restore the affected files from a known consistent copy before retrying. Keep
`.review/` with a bundle copy if it has a pending save. Catalog refresh failures
have a separate retry and never require rolling back saved labels. All write
tests use synthetic temporary bundles and injectable clocks; browser QA uses
disposable copies with catalog refresh disabled.

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
never creates a dataset or substitutes another corpus. Opening/editing is read-only;
Save changes, navigation's Save, Confirm and next, and Retry synchronization
explicitly write to the selected bundle.

Stop the server with **Ctrl-C** in its terminal. Relaunch the same command and
reload the browser to start a fresh session with saved progress. A browser reload
also starts a new session: save first if you want to keep pending edits. To run
another local instance, add `--server.port 8517` before the `--` separator.

### Table controls and review order

Double-click a table cell, enter its replacement, then press **Enter** or **Tab**
to commit the cell edit. Check the unsaved indicator before saving. Hover over
the table to reveal **Fullscreen** when dates or other columns are offscreen;
close fullscreen to return to the filing and save controls. **Add row** inserts
a blank row; fill all required fields, choosing EPS type from its dropdown.
To delete, click the row's left gutter and then **Delete row(s)** in the table
toolbar. Deleting a cell's contents does not delete its observation.

For each filing, inspect every relevant attachment and the review notes, correct
the table, and resolve any row errors. Use **Save changes** for work in progress.
Use **Confirm and next** only after reviewing completeness across the entire
package, including empty metrics and retained unknown starts. Saved progress,
not an end-of-list message, tells you whether every filing is confirmed.

### Disposable-copy verification

The repeatable browser checklist and read-only output verification are in
[docs/REVIEW_QA.md](docs/REVIEW_QA.md). This exercises the complete review without
editing JSON or writing the real labels/catalog. Keep the entire bundle,
including `.review/`, when making a backup; stop review writers while copying.
Backups are retained, but there is no automatic undo or backup pruning. Restore
a known consistent whole bundle when needed, rather than replacing only one
case or export.

## Dataset foundation

`review.config.resolve_dataset_root()` resolves configuration without side effects.
`parse_config()` returns `ReviewConfig` with the dataset root, optional shared
data root and catalog repository; `catalog_enabled` compares resolved paths.
`review.dataset.load_dataset(root)` validates the manifest and cases in listed
order, the packaged `earnings_eps.v1` label contract, filing snapshots, complete
artifact membership, original document sizes/hashes and confined relative paths
(including symlinks). It reads authoritative inputs rather than derived exports.
The writer's `verify_bundle(dataset)` checks full integrity and export agreement.
`load_dataset(root, validate_counts=False)` is used during pending synchronization
because a committed case may temporarily disagree with stale manifest counts;
source and label validation remain enabled. Ordinary loading validates counts.

The immutable `ReviewDataset`, `ReviewCase`, `SourceDocument` and `Observation`
models retain original decimal strings and nullable dates. Dataset/case
`to_dict()` returns an independent copy preserving unknown metadata. Their
`fingerprint` is the SHA-256 of exact manifest/case bytes for later stale-edit
detection. `SourceDocument.read_bytes()` rechecks confinement and source integrity.
`review.validation.validate_labels()` provides UI-independent schema, date-order
and duplicate-period validation; failures raise `ReviewError` with context.

`review.editor.labels_to_rows()` / `rows_to_labels()` convert between the table
and the two-array extraction payload without numeric coercion or UI-only fields.
`validate_rows()` reports all invalid rows, unknown start row numbers and either
a valid payload or no payload. `review.session.EditorDraft` retains the opened
fingerprint, stable widget input, pending rows, dirty status and discard generation.
`EditorDraft.resume()` recreates a removed widget from retained pending rows;
Discard still restores saved labels. `NavigationGuard` retains a requested
destination for Save/Discard/Stay, and `adjacent_case()` finds manifest-order
neighbors without wrapping. These helpers do not import Streamlit or write files.

`review.persistence.save_changes(root, case_id, opened_fingerprint, labels,
clock=...)` and `review.persistence.confirm_case(...)` return
`SaveResult(dataset, case_id, changed)` after full verification; `changed` includes
changes to review state as well as labels. Confirmation shares the label writer's
lock, stale-session detection, backups, export validation and recovery path.
`SaveConflict` retains stale drafts; `SynchronizationPending.committed` distinguishes
whether the intended case bytes reached disk. `synchronization_pending(root)` is
read-only; `retry_synchronization(root)` finishes an interrupted save. The v1
`pending.json` records the baseline inventory, expected replacement digests/sizes,
prior integrity digest, case/backup paths, transaction ID, UTC modification time
and action (`save_changes` or `confirm`). Older v1 journals without an action are
recovered as label saves. Recovery checks the intended review transition as well
as label/export agreement; it never obtains a new confirmation time on retry.
`review.exports.build_exports()` is UI-independent and stages string-only Parquet
and matching JSON in memory. These services require the `review` extra's PyArrow.
`review.catalog.refresh_catalog(config)` verifies synchronized inputs under the
writer lock, invokes the catalog CLI and records its successful bundle revision.
`refresh_status(config)` is read-only and returns disabled, unknown, pending or
current. Noncanonical configurations never create a receipt or invoke tooling.

## Checks

The core loader requires `jsonschema`. The `dev` extra installs pytest; the
optional `review` extra installs Streamlit, pandas, PyArrow, Bleach, html5lib and
tinycss2. Install both extras for all UI and persistence checks. Loading a dataset
does not import the UI dependencies. The
former screenshot tests were removed; the new tests cover the dataset contract,
path/source validation, viewer isolation/sanitization, lossless editor conversion,
row validation, pending edits/discard, app navigation/downloads, saves, stale writes,
process locking, export agreement, confirmation timestamps/invalidation,
Save/Discard/Stay navigation, last-case completion, dataset isolation and injected
failure/restart recovery. Step 6 adds saved progress/restart/invalidation checks,
aggregate and per-row export transitions, mocked catalog success/failure/timeout,
durable receipt/retry and canonical-path/copy safeguards.
The full-workflow regression also covers edit/add/save/delete, guarded navigation,
empty-case confirmation, restart, and reopening a completed dataset after edits,
with exact decimal/currency/null preservation and unchanged source/acquisition files.

Compile and verify the installed package:

```bash
.venv/bin/python -m compileall -q src tests
.venv/bin/python -c 'import finbot_filing_evals; print(finbot_filing_evals.__version__)'
```

Run the test suite for every step:

```bash
.venv/bin/python -m pytest
```

Run the review UI checks separately when investigating browser behavior:

```bash
.venv/bin/python -m pytest tests/test_review_app.py
.venv/bin/python -m pip check
```

Tests use temporary synthetic fixtures, block network connections and unmocked
catalog subprocess calls, and avoid shared-data writes. Streamlit AppTest checks
run when the `review` extra is
installed; install both extras to run the complete suite. Real-sample smoke checks
are separate so a missing shared bundle does not break normal tests.

To verify the installable distribution, build a wheel outside source control:

```bash
.venv/bin/python -m pip wheel --no-deps --wheel-dir /private/tmp/finbot-filing-evals-wheels .
```

No previous-work archive or backup was created during cleanup. The shared data
root, original documents and draft labels were not modified.
