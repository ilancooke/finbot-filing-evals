# Document EPS Review UI Roadmap

## Purpose and current state

Build a local Streamlit app in `finbot-filing-evals` for a person to inspect
original SEC documents, correct EPS labels, and confirm each filing package.
Read this file and README.md before starting a step; no previous chat is needed.

The draft dataset already exists at:

```text
$FINBOT_DATA_ROOT/filing-evals/golden/earnings-eps-v1/
```

Initially it contains 13 filing packages, 27 HTML documents, and 34 observations
(25 reported and 9 adjusted). Forms: eight 8-Ks, two 6-Ks, two 10-Qs, one 10-K.
Counts are an initial reference, not constants: edits can add/delete observations.
The previous screenshot pipeline has been removed without an archive. Step 1 is
complete, and Step 2 adds formatted viewing, readable text and original downloads.
Step 3 adds a session-only editor, row validation and explicit discard before
changing filings with pending edits. Dataset validation/models, the Streamlit
shell, launch script, `review` dependency extra and offline tests exist. The core
dependency is `jsonschema`. Persistence and confirmation remain future steps.

## Cleanup baseline

The user explicitly requested removal without preserving the old work. Cleanup
removed `golden_dataset/`, its tests and fixtures, frozen resources, provider
adapters, the extraction console command, provider extras, unused dependencies,
obsolete environment examples, and stale build artifacts. The namespace
`finbot_filing_evals`, version 0.1.0, src-layout packaging, pytest dev extra and
empty `tests/` directory remain. Shared datasets were not changed.

Cleanup handoff (2026-10-21 UTC): complete. Source/config/docs updated and the
repo-local Python 3.14 environment rebuilt. Editable install, compileall, package
import/version and wheel-content checks passed; the old CLI and runtime/provider
dependencies are absent. Pytest collected no tests (exit 5), as expected after
removing the old suite. Shared dataset integrity was verified unchanged. Next
implementation work is Step 1. Do not recreate the deleted screenshot code.

## How to execute and hand off a step

1. Read README.md, this roadmap, applicable AGENTS.md instructions, and git
   status. Preserve unrelated existing changes, including untracked files.
2. Work on the first incomplete step after all its prerequisites are complete.
   Mark it in progress. Implement only that step unless the user requests more.
3. Inspect predecessor code/tests and use the contracts below. If a predecessor
   is incomplete, report the concrete gap rather than silently implementing later
   features. Resolve routine implementation details without reopening agreed scope.
4. Add focused tests with the step. Run its acceptance checks and the full package
   checks in README.md. All new write tests use temporary datasets and fake clocks.
5. Mark a step complete only when every acceptance item passes. Update README.md
   with commands/features that now actually work, and replace that step's handoff
   line with date, changed files, checks/results, and remaining limitations.
6. Leave unfinished checkboxes unchecked and record the exact next action. A
   handoff must not rely on a conversation, an agent's memory, or a `/tmp` script.

| Step | Deliverable | Prerequisite | Status |
| --- | --- | --- | --- |
| 1 | Dataset foundation and read-only app shell | Existing draft dataset | Complete |
| 2 | Document viewer | Step 1 | Complete |
| 3 | Editable labels and validation | Step 2 | Complete |
| 4 | Durable saves and synchronized exports | Step 3 | Pending |
| 5 | Confirmation and guarded navigation | Step 4 | Pending |
| 6 | Progress and catalog refresh | Step 5 | Pending |
| 7 | End-to-end verification and operating docs | Step 6 | Pending |

Tests belong in every step; Step 7 integrates and exercises the completed flow.
Until Step 4, the app must not write to the dataset. Confirmation stays disabled
until Step 5. Early steps should show their current capabilities honestly.

## Agreed dataset and label contract

### Files and ownership

- `dataset.json` lists case paths in navigation order, schema version
  `earnings_eps.v1`, policy, counts, and dataset review state.
- `cases/<case_id>/case.json` is authoritative for that filing's labels and
  review state. Its keys are `case_id`, `filing`, `documents`, `labels`, `review`.
- `filing` holds upstream identity/context, including ticker, form, filing ID,
  snapshot ID, primary artifact ID, and the complete selected `artifacts` list.
- `documents` maps each artifact ID to `path` and `sha256`. Paths are relative
  to the dataset root, not the case directory. Every selected artifact is present.
- Original HTML is in `cases/<case_id>/documents/`. Per-case `provenance.json`
  and `filing-ready.json` preserve acquisition history. Nine original event
  manifests were reconstructed upstream; four additions retain saved events.
- Optional `review-text/` files are display aids, not authoritative documents.
- `labels.schema.json` defines the label payload. `labels.json`, `labels.parquet`,
  `labels.metadata.json`, and `REVIEW.md` are derived label/review exports.
  The flat `labels.json` list and Parquet rows have the same fields and values;
  they are not shaped like the two-array `case.labels` object.
- `documents.parquet` and `documents.metadata.json` describe the source files.
  `source-inventory.json` and `source-records.json` are acquisition snapshots.
- `integrity.json` records SHA-256 and byte size for bundle files other than
  itself. Initial hashes already exist; label edits require refreshed hashes.
- The older source sample under `data/earnings/evaluations/corpora/golden-s3-v1`
  belongs to a separate workflow. This app reads/writes the new `filing-evals`
  bundle only; it does not synchronize edits back to that older sample.

### Extraction targets

`case.labels` has exactly two arrays: `reported_diluted_eps` and
`adjusted_diluted_eps`. Each observation has exactly these fields:

```json
{
  "value": "4.60",
  "currency": "USD",
  "period": "Q3 2026",
  "period_start": "2026-07-01",
  "period_end": "2026-09-30"
}
```

- Keep values as signed decimal strings, including trailing zeroes. The current
  schema requires a decimal point; validate with Decimal, never a float round trip.
- Currency is three uppercase letters. Preserve reported currencies without
  conversion. Period is a nonblank descriptive label; do not infer dates from it.
- Dates are ISO `YYYY-MM-DD`. `period_start` may be null; `period_end` is required.
  When both are present, start must not follow end. Blank start inputs map to null.
- An empty array means no qualifying figure was identified, never zero. Do not
  create placeholder observations. Dedupe repeated values across attachments.
- Reject duplicate observations within a metric/currency/known date interval,
  even if their period labels differ. For null starts, use normalized period
  label plus end date so quarterly and cumulative observations stay distinct.
- Scope is the latest reported quarter and current fiscal year-to-date results,
  or the latest fiscal year for a 10-K. Exclude historical comparison quarters/
  years, guidance, basic EPS, adjustment components, and calculated EPS.
- Use the primary explicitly reported adjusted figure; exclude operational or
  constant-currency variants. Reported EPS accommodates foreign reporting standards.
- No share-unit, accounting-basis, evidence, or extra financial metrics belong
  in extraction targets. Preserve source provenance and separate review notes.

Known review questions must remain visible, not be silently resolved in code:
JNJ ends September 27, 2026 and has four null start dates; ASML/DPZ start-date
interpretations need review; TSM has TWD 29.43 and USD 4.60, with the USD amount
presented per ADR; JNJ operationally adjusted figures are excluded. These are
annotation questions, not permission to fetch more documents or alter labels.

### Review and save semantics

- Existing cases start with `review.status = "unreviewed"` and `review.notes`
  as a list of strings. Preserve notes; show them separately from editable labels.
- Add nullable `review.reviewed_at_utc` when review persistence is implemented;
  it is absent in initial files and readers must tolerate that. A confirmed case
  has status `human_reviewed` and an explicit UTC confirmation timestamp.
- Save changes persists valid labels without confirming an unreviewed case.
  Changing labels of a confirmed case resets status to unreviewed and clears its
  confirmation timestamp. A no-op save preserves existing confirmation.
- Confirm and next validates/saves the current labels, sets human_reviewed and
  the confirmation timestamp, then moves to the next case in manifest order.
  At the last case, stay on the case and show completion. Empty arrays are valid.
- Null start dates are permitted by the agreed schema. Highlight them and let
  the reviewer retain them; never force an invented date to enable confirmation.
- Dataset review_status is unreviewed when none are confirmed, in_progress when
  some are confirmed, and human_reviewed when all are confirmed. Only the last
  state sets human_reviewed true and label_source human_reviewed. Otherwise the
  dataset remains agent_draft. All counts are derived from current cases.
- Label sidecar metadata follows the dataset's review state; its `partial` flag
  stays true until all cases are confirmed. Source-document metadata is about
  acquisition, not the authority for label review state.
- Confirming a filing means checking the entire selected package, including
  completeness and absent metrics; it does not require adding per-value evidence.

## Implementation layout and launch contract

New code belongs in `src/finbot_filing_evals/review/`. Modules below define
ownership; adjust names only if the README/roadmap handoff is updated to match
actual files.

Use `scripts/review_eps.py` as the thin Streamlit entry point. The optional
`review` extra installs Streamlit, pandas and PyArrow; add HTML display tooling
when Step 2 needs it. The core loader uses `jsonschema`; keep the pytest dev
extra. Keep persistence/export code independent of Streamlit so it can be tested
without a running server.

Working commands (run from this repository root; session-only edits, no dataset writes):

```bash
.venv/bin/python -m pip install -e '.[dev,review]'
export FINBOT_DATA_ROOT=/Users/ilan/workspace/finbot/data
.venv/bin/python -m streamlit run scripts/review_eps.py --server.address 127.0.0.1
# Explicit dataset override, including a disposable local copy:
.venv/bin/python -m streamlit run scripts/review_eps.py --server.address 127.0.0.1 -- --dataset-root /path/to/copy
```

Explicit `--dataset-root` takes precedence over FINBOT_DATA_ROOT. Without an
explicit path, require FINBOT_DATA_ROOT and append `filing-evals/golden/earnings-eps-v1`.
Do not load `.env`, create an empty dataset, or choose another corpus silently.
No AWS credentials, provider SDKs, external requests, or sibling package imports
are needed. Use the repo's own environment; verify its interpreter exists and is
Python >=3.12. A broken/stale virtualenv is an environment issue to fix locally,
not a reason to borrow another package's environment or rewrite dependencies.

## Step 1 — Dataset foundation and read-only app shell

Prerequisite: existing draft bundle or synthetic temporary fixtures matching the
contract above. No earlier UI code is assumed.

Deliver `review/config.py`, `dataset.py`, the thin app/launch script, optional
review dependencies, and the first dataset fixtures/tests. Add a maintained
document label schema as needed; no previous schema loader or validator remains.

- [x] Resolve the dataset path and load manifest/cases in listed order.
- [x] Validate schema version, nonempty/unique case membership, case identities,
  label shape, complete document membership, source hashes/sizes, and paths
  confined to the dataset root,
  including symlinks. Missing/bad input produces an actionable app error.
- [x] Establish dataset/case models and a per-case disk fingerprint for later
  stale-edit detection. Preserve unknown upstream metadata when round-tripping.
- [x] Show a wide two-pane shell, filing/attachment selectors, filing-level
  values, notes, and saved review status. Use plain text/filename preview until
  Step 2; do not render active filing HTML or offer write controls yet.
- [x] Add README setup/launch instructions marked as read-only at this stage.

Acceptance: temporary fixtures load without credentials or network; malformed
paths, unsupported versions and changed source bytes fail clearly; empty metrics
and null starts survive loading; new tests and scaffold checks pass. If the real
bundle is available, read-only smoke inspection finds the initial 13/27/34 baseline
without requiring it in normal tests. Run the documented launch command successfully.

Handoff (2026-10-20): complete. Implementation:

- `review/config.py`: explicit `--dataset-root` precedence and environment fallback;
  no dotenv, directory creation or corpus substitution.
- `review/dataset.py`: `load_dataset(root)`, immutable public models, ordered cases,
  complete artifact/hash/size/path checks, and canonical upstream snapshot checks.
  `ReviewCase.fingerprint` / `ReviewDataset.fingerprint` hash exact file bytes;
  `to_dict()` preserves unknown metadata in an independent copy. Source access
  through `SourceDocument.read_bytes()` revalidates confinement and content.
- `review/validation.py`, `errors.py`, `schemas/earnings_eps_v1.schema.json`:
  packaged label schema and `validate_labels(labels, location=...)`; schema, date,
  duplicate and loading failures use `ReviewError`. The local dataset schema must
  match the packaged contract; untrusted schema references are never resolved.
- `review/app.py`, `scripts/review_eps.py`: wide read-only shell with dataset/case
  namespaced selectors, saved labels, status and notes. `plain_text_preview(raw)`
  strips markup/scripts/styles and is rendered with `st.code`, never active HTML.
- `tests/conftest.py` and `test_review_{config,dataset,validation,app}.py`: synthetic
  temporary bundles, network guard, malformed input/source tests, precision/null
  preservation, metadata round trips and Streamlit AppTest navigation checks.

Checks: editable `.[dev,review]` installation; compileall; 81 passing tests;
wheel build with packaged schema/import verification. Read-only real-bundle smoke
loaded 13 filings / 27 documents / 34 observations and extracted preview text from
all originals. Real bundle integrity hashes/sizes remained unchanged. AppTest
visited every filing on a disposable copy without changing any file. The launch
command above started on localhost (QA used port 8511, headless mode, usage stats
disabled and an explicit temporary dataset copy). Browser automation was unavailable
in this session, so no visual browser inspection is claimed.

Next action: Step 2, `review/viewer.py`, using `ReviewCase.documents` and source
metadata. The shell currently defaults to the first manifest attachment; Step 2
must prefer EX-99.1 and retain attachment selection. Formatted viewing/downloads,
editing, saving, confirmation and catalog refresh are not implemented. The loader
reads authoritative manifest/cases/schema/documents; validating/synchronizing all
derived exports and `integrity.json` during saves belongs to Step 4.

## Step 2 — Document viewer

Prerequisite: Step 1 loader and app shell. Deliver `review/viewer.py` and viewer
checks; use the loader's source paths and artifact metadata.

- [x] Render the selected original HTML in an isolated display-only viewer,
  preserving tables and useful inline formatting without changing source bytes.
- [x] Prevent filing scripts and external asset/network loads from executing.
  Do not pass raw SEC HTML into an embedding mode that executes it by default.
- [x] Keep filing-wide labels visible while switching attachments; do not imply
  every value appears in whichever attachment is currently selected.
- [x] Offer readable text fallback and original-file download. Upstream selection
  omitted images/stylesheets: missing assets must not trigger downloads or hide
  accessible text. Do not promise pixel-identical rendering.
- [x] Use EX-99.1 as the initial attachment when available, otherwise the first
  manifest artifact; preserve a user's selected attachment within the filing.

Acceptance: representative synthetic nested tables and script-containing HTML
render without executing scripts or contacting external services; text fallback
works when no precomputed review text exists. Manually inspect ASML and TSM
releases plus CMC/RTX/GM long reports if the sample is available. Source hashes
remain unchanged. App remains read-only.

Handoff (2026-10-20): complete. Implementation:

- `review/viewer.py`: HTML5 byte parsing (including encoding declarations),
  Bleach element/attribute allowlists and tinycss2 inline-style filtering preserve
  nested tables, spans, typography, alignment and table borders. Active subtrees,
  resource attributes, event handlers, links and unsafe/hiding CSS are removed.
  Images retain available alt text. No asset fetching or source rewriting occurs.
- `sanitized_html(raw)` creates a display derivative with a restrictive CSP:
  default/script sources, forms and base URLs are blocked; safe inline styles are
  permitted. `viewer_frame(raw)` escapes that derivative into an iframe with an
  empty sandbox and no-referrer policy. Only the generated wrapper is passed to
  `st.iframe` (or the older components API when unavailable), never raw SEC HTML.
- `plain_text_preview(raw)` reads original bytes without precomputed review text,
  retaining text/table separators and omitting active/hidden XBRL headers.
  `initial_attachment(documents)` prefers EX-99.1, otherwise manifest order.
- `review/app.py`: formatted/text view selection, exact original-file download,
  filing-wide labels/notes alongside the document, and separate non-widget
  attachment state keyed by dataset/case so choices survive filing switches.
- `pyproject.toml`, README and `tests/test_review_{viewer,app}.py`: optional HTML
  dependencies, operating/display-limit docs, nested/malformed/hostile markup and
  CSS checks, encoding/alt-text fallback, both Streamlit embedding paths, original
  download bytes, attachment retention and read-only navigation checks.

Checks: Python 3.14.8 repo-local environment; editable `.[dev,review]` installation;
compileall; import/version; 112 passing tests with network connections blocked;
`pip check`; wheel build and packaged viewer/schema checks. A sandboxed pip build
initially could not resolve PyPI; rerunning installation/build with network access
succeeded without changing build requirements.

Read-only sample smoke rendered/extracted all 27 documents across 13 filings and
34 observations. Firefox inspection used a disposable bundle copy and Streamlit
on localhost port 8512: ASML and TSM releases, CMC annual report, RTX/GM quarterly
reports, document scrolling and GM text fallback were inspected. ASML financial
tables and TSM original-currency text remained readable; long-report covers and
inline formatting rendered. A separate localhost browser probe rendered a nested
table plus hostile scripts, event handlers, frames, stylesheet/image/CSS loads.
No script marker executed and no forbidden endpoint was requested. An additional
QA-only frame deliberately bypassed sanitization to verify CSP/sandbox blocking;
it also made no asset/script requests. The probe log contained only its page and
favicon requests. All real-bundle and QA-copy file hashes remained unchanged.
Normal tests use synthetic fixtures and never depend on this sample or probe.

Limitations: rendering is not pixel-identical. Images/stylesheets/fonts are not
loaded; safe inline styles only are retained; source links (including a report's
table of contents) are inert. Wide tables may need horizontal scrolling, source
font sizes can be small, and text fallback linearizes layout. Attachment choices
are session-only; no edits, dataset saves, confirmation or catalog writes exist.
Original downloads do not inherit the app's viewer protections.

Next action: Step 3, editable filing-wide labels and validation/session state,
with no disk writes. Keep the viewer and attachment selection behavior intact.

## Step 3 — Editable labels and validation

Prerequisite: Step 2 working viewer. Deliver `review/editor.py`, validation and
session-state helpers, and focused tests; no disk writes yet.

- [x] Present one dynamic table: EPS type, value, currency, period, start/end.
  Convert to/from the two arrays without adding UI fields to saved observations.
- [x] Support additions, deletions, empty arrays and an initially empty table.
  Treat an entirely blank new row as unused; reject partially populated rows.
- [x] Preserve decimal strings/negative signs/trailing zeroes and null starts.
  Apply the contract's schema, calendar-date, ordering and duplicate checks.
- [x] Show row-specific errors and distinguish unsaved changes from saved values.
  Render current annotation notes and highlight missing dates without filling them.
- [x] Keep pending edits through reruns and attachment switches. Until Step 5
  provides the full navigation guard, prevent a filing change from losing edits
  by requiring explicit discard. Clearly label edits as unsaved; no working Save
  or Confirm button is claimed before their implementation steps.

Acceptance: round trips preserve 4.60, negative EPS, two currencies, quarter/YTD
pairs sharing an end date, and unknown dates; bad dates/duplicates/partial rows
report useful errors. Adding/deleting the final row preserves the right empty
array. Disk files remain unchanged, and UI smoke tests retain attachment edits.

Handoff (2026-10-20): complete. Implementation:

- `review/editor.py`: `labels_to_rows()` and `rows_to_labels()` convert one mixed
  table to/from the two metric arrays, retaining exact decimal/date strings and
  null starts. `validate_rows()` returns `EditorResult(labels, errors,
  missing_starts)`: invalid rows have one-based table positions, and any error
  withholds the payload. It reuses `validate_labels()` for schema, date-order and
  duplicate checks. Entirely blank rows are unused; partial additions are invalid.
- `review/session.py`: `EditorDraft` keeps independent saved labels, the opened
  case fingerprint, stable base rows, pending rows and a widget generation.
  `dirty` includes invalid rows and ignores unused blank rows. `discard()` restores
  the opened labels and increments the generation to clear old widget deltas.
  `capture_widget_changes()` reads the latest public edit/add/delete delta before
  a navigation callback, including edits arriving with the selector event.
- `review/app.py`: dynamic table with EPS-type selection and string columns for
  values/currencies/periods/dates, per-row errors, unknown-start warnings, separate
  notes/saved status and explicit session-only messaging. The editor always gets
  stable base input so repeated reruns do not apply additions/deletions twice.
  The filing selector is disabled while dirty; Discard changes unlocks it. A
  selector callback also guards delayed events. Save/Confirm are absent.
- Session namespace is the first 16 hex characters of SHA-256 of the resolved
  dataset root. Non-widget keys are `<namespace>:active_filing` and
  `<namespace>:<case_id>:draft`; selector key is `<namespace>:filing`. Editor keys
  are `<namespace>:<case_id>:editor:<generation>`. Attachment keys from Step 2
  remain unchanged. Helpers have no Streamlit dependency or filesystem writes.
- `tests/test_review_editor.py`, `tests/test_review_app.py`, README and roadmap:
  round-trip precision/sign/currency/quarter/YTD/null tests, row validation,
  duplicate row mapping, add/delete/initially-empty tables, stable draft/discard,
  AppTest edit retention across attachment/view/reruns, invalid-row navigation
  lock, delayed-event guard, restart and dataset-path isolation checks. Temporary
  bundle file hashes agree before/after editing, discard and navigation.

Checks: predecessor baseline 112 tests passed; final 140 tests passed with network
connections blocked; Python 3.14.8 repo-local compileall, import/version and
`pip check` passed. The documented isolated wheel build passed with the new
editor/session modules and packaged schema. The documented Streamlit command
started on localhost port 8513 and returned HTTP 200 / `ok` from its health endpoint
against a disposable synthetic dataset (headless, usage stats disabled).
The sandbox initially blocked binding localhost; the authorized local smoke run
succeeded outside the sandbox. Browser automation reported no available browser,
so visual inspection is not claimed; Streamlit AppTest exercised the real editor
using its edit/add/delete widget state. No real shared dataset was changed.

Limitations/next action: Step 4, durable saves and synchronized exports. All edits
remain session-only and are lost on session end. Filing navigation currently
requires explicit discard (or manually reverting all edits); Save/Discard/Stay,
confirmation and catalog refresh remain later steps. The table can require
horizontal scrolling beside wide documents.

## Step 4 — Durable saves and synchronized exports

Prerequisite: Step 3 validated editor output. Deliver `review/persistence.py` and
`exports.py`, wire Save changes, and test failure/recovery paths.

- [ ] Serialize writes with a dataset-level local writer lock; inside the lock
  compare the case's current fingerprint with the opened version. A conflict
  preserves pending edits and refuses to overwrite the external change.
- [ ] Revalidate source integrity and proposed labels, back up the prior case,
  and atomically replace case.json. Preserve filing/documents/provenance fields.
  Implement the agreed invalidation/no-op semantics for previously reviewed cases.
- [ ] From authoritative case files, rebuild labels.json/Parquet, label metadata,
  observation/review counts and state in dataset.json, and REVIEW.md. Maintain
  original creation time and acquisition facts; update modification metadata.
- [ ] Refresh integrity.json last. Verify source manifests/hashes, but do not
  rewrite source documents, provenance, acquisition snapshots or label schema.
  Label exports retain case_id, ticker, filing_id, form_type, metric, the five
  observation fields, and review_status; reviewed/unreviewed rows remain distinct.
  Preserve values and dates as strings (nullable start dates), matching the
  initial flat export schema. Do not introduce floating-point EPS columns.
- [ ] Keep backups, writer lock and recovery state under `.review/`, excluded
  explicitly from current-bundle integrity hashing. Make a durable pending marker
  before committing a case, recording its expected replacement fingerprint.
- [ ] Stage/validate derived files before replacement where possible. Individual
  atomic writes are not a multi-file transaction: an interrupted save must be
  recognized as synchronization pending, not a healthy complete save.
- [ ] Retry/recover from authoritative cases under the writer lock; accept an
  interrupted case change only when it matches the pending marker. Unexpected
  integrity mismatches still fail. Clear the marker only after all exports/hashes
  agree. Distinguish “labels saved, exports need retry” from “nothing saved.”

Acceptance: save/reopen preserves edits and notes; source bytes are unchanged;
JSON/Parquet/manifest/review counts agree; backup exists; stale second sessions
cannot overwrite; injected failures before/after the case commit and during an
export are recoverable after restart without losing labels or claiming success.
Do not test this writer on the real review dataset. Catalog wiring waits for 6.

Handoff: Pending. Record on-disk recovery format, save/export APIs, and fault tests.

## Step 5 — Confirmation and guarded navigation

Prerequisite: Step 4 save/export service. Deliver confirmation/navigation in the
app and session-state helpers, using that same persistence path.

- [ ] Implement Save changes and Confirm and next with distinct review semantics.
  Confirmation timestamps come from an injectable UTC clock, not UI-supplied dates.
- [ ] Add previous/next and direct filing selection in manifest order. Only move
  after a successful requested save/confirmation; pending recovery keeps the user
  on the current case. Last-case confirmation shows completion without wrapping.
- [ ] When leaving with edits, offer Save, Discard or Stay. Discard restores the
  last saved case and clears its stale editor widget state. Attachment switching
  preserves pending labels and requires no extra confirmation.
- [ ] Restore saved labels/status on restart and prevent state leaking between
  filings or dataset paths. Session-only editing never counts as a durable review.
- [ ] Allow confirmation of valid empty arrays or explicitly retained null starts;
  keep their meaning and current review notes visible.

Acceptance: complete Save/Confirm flows persist different states; a failed save
never advances; Save of changed reviewed labels invalidates confirmation; a no-op
save preserves it. Save/Discard/Stay and last-case navigation behave correctly;
restart restores saved state. Use temporary data and deterministic timestamps.

Handoff: Pending. Record navigation/state behavior and confirmation checks.

## Step 6 — Progress and catalog refresh

Prerequisite: Step 5 complete persisted review flow. Deliver progress UI and a
small catalog-command adapter; dataset aggregate/export semantics already exist
from Step 4 and must not be deferred until here.

- [ ] Show saved reviewed/unreviewed counts, filing statuses and overall state;
  derive them from cases rather than initial constants or unsaved session flags.
- [ ] Verify aggregate flags and per-row export states for no/some/all reviewed
  cases, including reverting a previously complete dataset after a label edit.
- [ ] After successful synchronized saves to the canonical shared dataset, invoke
  the sibling finbot-catalog CLI as a subprocess argument list, not a shell string
  or sibling Python import. Default to its repo-local interpreter and
  `scripts/build_catalog.py --data-root <FINBOT_DATA_ROOT>`; allow a documented
  `--catalog-repo` override. No catalog source changes are required.
- [ ] Disable automatic catalog refresh for explicit noncanonical dataset copies,
  including temporary fixtures. Missing/broken catalog tooling or a failed refresh
  must not undo saved labels or hide the failure; show catalog refresh pending and
  let the user retry. Do not claim catalog freshness before success.

Acceptance: progress survives restart and label edits; all-reviewed flags are
accurate; catalog adapter has mocked success/failure tests and never runs in normal
UI/unit tests. Temporary-copy use performs no shared catalog writes. Confirm the
real catalog integration only after an explicitly requested real review save.

Handoff: Pending. Record CLI configuration, retry behavior and progress checks.

## Step 7 — End-to-end verification and operating docs

Prerequisite: Steps 1–6 complete, with tests and handoffs already recorded.

- [ ] Exercise a disposable dataset copy in a real browser: view attachments,
  edit/add/delete observations, Save, Confirm, navigate, restart, and check outputs.
  Include empty adjusted EPS, JNJ null starts, TSM two currencies and a long report.
- [ ] Verify source hashes remain unchanged, decimals survive, review state is
  accurate, exports/integrity agree, and stale-write/recovery scenarios still work.
- [ ] Run compileall, the full package test suite, and the review UI tests with
  the repo-local environment. New tests must not require the shared dataset.
- [ ] Finalize README setup, launch, dataset override, review meanings, backup/
  recovery and catalog troubleshooting. Document known HTML limitations and the
  working document-review commands without restoring removed legacy workflows.
- [ ] Record validation evidence and remaining limitations in this roadmap; mark
  complete only when the user can perform the entire review without editing JSON.

Acceptance: the documented launch works from a clean repo-local installation;
the temporary-copy browser workflow and all package checks pass; saved labels,
review progress, exports and integrity agree after restart. No real review data
was changed during QA, and the handoff identifies any remaining display limits.

Handoff: Pending. Record full commands/results, browser checks and remaining work.

## Boundaries for every step

Keep all implementation in this repository and all generated data outside Git.
The app is a local single-user workflow, with stale-session protection; do not add
a hosted service, authentication, a database, model inference, AWS operations,
new downloads, analyst expectations or automatic EPS calculations. Do not expand
the schema with the fields intentionally omitted above. No cross-repo imports or
changes to the read-only finbot-dashboard are part of this roadmap. Tests write
only temporary fixtures; browser QA also uses copies. Preserve unrelated working
changes and the original draft/source data throughout implementation.
