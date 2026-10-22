# Document EPS Review and Evaluation Roadmap

## Purpose and current state

Build a local Streamlit app in `finbot-filing-evals` for a person to inspect
original SEC documents, correct EPS labels, and confirm each filing package.
Read this file and README.md before starting a step; no previous chat is needed.

The review bundle lives at:

```text
$FINBOT_DATA_ROOT/filing-evals/golden/earnings-eps-v1/
```

Initially it contains 13 filing packages, 27 HTML documents, and 34 observations
(25 reported and 9 adjusted). Forms: eight 8-Ks, two 6-Ks, two 10-Qs, one 10-K.
Counts are an initial reference, not constants: edits can add/delete observations.
The previous screenshot pipeline has been removed without an archive. Steps 1–7
are complete, including formatted viewing, readable text and original downloads.
Steps 1–3 provide dataset validation/models, document viewing and a validated
session editor. Step 4 adds durable Save changes, synchronized exports, backups,
stale-session checks and interrupted-save recovery. The Streamlit shell, launch
script, `review` extra and offline tests exist. The core dependency is `jsonschema`.
Step 5 adds durable confirmation, UTC timestamps, manifest-order navigation and
Save/Discard/Stay guards. Step 6 adds saved progress and canonical catalog refresh
with durable status and retry. Step 7 verifies the complete disposable-copy browser
workflow, restart, outputs and clean installation, and supplies operating docs.

## Current experiment findings — 2026-10-22

The [full experiment report](docs/MODEL_EXPERIMENT_REPORT.md) summarizes all
18 saved runs: 16 comparable fiscal v2 evaluations and two separate legacy runs.
Luna 6 through OpenAI is the leading candidate for broader testing: three runs
matched 20/20 observations and 13/13 filings, with identical predictions.
The first measured run cost $0.054453210; cache-hit repeats cost $0.00525418 and
$0.00529318. Sonnet, Kimi and Haiku each achieved one perfect full-bundle run.
The report documents latency, tokens, partial costs, post-hoc rates, integration
failures and the lack of held-out validation. Advance to newly reviewed coverage
using fixed v4 plain-text/image inputs; no config has been silently repointed.

The Nova findings below remain the historical prompt/input reference. The full
report supersedes their model-selection recommendation.

## Nova reference baseline — 2026-10-22

Use **Nova 2 Lite through Bedrock, prompt v4, plain-text HTML extraction plus
original images**. The recommended config is
`configs/bedrock-nova-2-lite-prompt-v4.json`; `prompts/eps-v4.txt` is unchanged.
The CLI requires an explicit config; the older `bedrock-nova-2-lite.json` still
references v2 and has not been repointed. The label contract remains
`earnings_eps.fiscal.v2`: 20 quarterly/annual targets projected from 34 reviewed
source observations, with 14 cumulative/YTD exclusions in the current sample.

Observed v4 results, with identical prompt, model settings and target revision:

| Input | F1 | Exact filings | Measured runtime | Known estimated run cost |
| --- | --- | --- | --- | --- |
| Plain text A | 97.6% | 12/13 | 48.52 s | $0.1349 |
| Plain text repeat B | 90.0% | 10/13 | 48.40 s | $0.1348 |
| Raw HTML | 65.0% | 4/13 | 339.73 s | $1.3816 (incomplete) |
| Cleaned HTML | 78.0% | 8/13 | 78.10 s | $0.3341 |

These are per-13-filing usage-based cost estimates, not AWS invoices. Raw usage
is available for 12/13 filings. The small sample was reused for prompt tuning;
two text runs and one run for each HTML mode are insufficient for broad accuracy
claims. Retain v4 text as the baseline, pause further prompt/input-format tuning
on this set, and favor repeatability checks and additional reviewed coverage.
Other prompts/input modes remain available for controlled reproduction.

See [docs/EVALUATION_EXPERIMENTS.md](docs/EVALUATION_EXPERIMENTS.md) for the seven Nova
run IDs, observed failures, tokens, costs, limitations and comparison commands.
The original reviewed bundle, old runs and strict scoring remain unchanged.
The Streamlit evaluation screen remains a future roadmap item, not part of the
implemented CLI workflow.

Dated handoffs below record implementation history and checks at that time.
This section and the experiment record supersede earlier pre-run instructions;
completed experiments do not need to be rerun merely because an old handoff
names a "next operator run".

## EPS extraction evaluation — complete

The review workflow above remains complete. A separate CLI evaluation workflow
freezes verified human-reviewed inputs, runs an extractor without golden labels,
scores predictions, saves reproducible reports and compares runs. Evaluation output
belongs under `data/filing-evals/runs/`; it never edits golden labels or refreshes
the shared catalog. GPT-6 Luna was the first selected model; the Nova maintenance
entry below supplies a working baseline while Luna account access is pending.

- [x] Implement reviewed-input snapshots, extractor execution and saved-prediction scoring.
- [x] Implement versioned scoring, filing diagnostics, JSON/Parquet reports and run comparison.
- [x] Add offline tests, update operating docs and run all package checks.
- [ ] Future: add a read-only Streamlit evaluation screen for scores, original
  documents, golden/predicted differences and side-by-side run comparison. This
  is deferred; the initial evaluation interface is the CLI and saved reports.

Handoff (2026-10-22): complete. New code lives under
`src/finbot_filing_evals/evaluation/`, separate from the completed review app.

- `cli.py`, `runner.py`, `files.py`: installed `finbot-eval-eps run/compare` and
  module entry point; explicit/shared-root path resolution; full human-review and
  existing bundle/export integrity requirements; detection of changes during
  snapshot creation. Run directories freeze original documents, manifest/cases,
  schema, prompt/config, source revision and implementation/dependency versions.
  Label-free requests whitelist public filing metadata. Inputs are rechecked after
  extraction; output publishes only after reports and run integrity are complete.
- `bedrock.py`, `configs/bedrock-luna.json`, `prompts/eps-v1.txt`: one filing per
  sequential Converse call, using `us.openai.gpt-6-luna` in `us-east-1`, a reused
  boto3 client and the normal credential chain. Readable text comes from the
  existing viewer helper; original verified rasters are sent as images. No
  screenshot pipeline, retrieval, downloads or AWS resource provisioning. Output
  tokens are explicitly bounded; SDK retries/timeouts are configured. Native
  responses, stop reasons, token usage and rate-table cost estimates are retained.
  Invalid/truncated/refused responses become visible errors without JSON repair.
- `extractor.py`: reusable trusted local command adapter and offline saved-response
  mode. Arguments are passed without a shell, stdin contains only the extraction
  request, shared-root variables are removed and raw stdout is retained/bounded.
  The command has ordinary OS access and must be trusted. No credentials are
  recorded. Saved predictions never initialize a provider client.
- `scoring.py`, `reports.py`: versioned `eps_exact.v1` matching by metric,
  currency and dates, with normalized period labels for null starts and exact
  Decimal comparison. Wrong values, missing and extra observations are distinct;
  wrong identities produce missing plus extra. Failed cases stay in results and
  can never be exact filings, including empty ones. Reports include micro
  precision/recall/F1, per-metric scores, exact-filing rate, errors, runtime and
  explicitly incomplete cost estimates. String-valued observation Parquet and
  per-case Parquet each have metadata sidecars. Comparisons verify run integrity
  and reject different dataset revisions or scoring policies.
- `pyproject.toml`, `.env.example`, README: console entry point, separate `eval`
  and `bedrock` extras, operating commands, provider configuration, scoring,
  input bounds, saved-prediction format, output layout and exit codes. Existing
  review code, golden labels, catalog behavior and sibling packages are unchanged.

Validation: predecessor baseline 266 passed; final full suite **328 passed**,
including 62 evaluation tests. Compileall, `pip check`, whitespace checks and the
isolated wheel build passed. The first wheel attempt could not resolve PyPI in
the sandbox; the unchanged build passed with network access. Tests use synthetic
temporary reviewed bundles, blocked network, mocked provider calls, and botocore
Stubber validation of actual SDK request/response shapes. A wheel extracted
outside the source tree successfully ran a real local synthetic extractor command,
saved-prediction rescoring and run comparison, with no AWS calls. The temporary
QA bundle, extractor script and extracted wheel were removed.

Read-only real-bundle QA froze 13 reviewed cases / 77 artifacts / 50 images into a
temporary snapshot and prepared every Bedrock request without initializing an AWS
client. All source assets passed limits (maximum 19 images in a filing; largest
text input 415,442 characters). All 261 canonical file hashes were unchanged and
the temporary snapshot was removed. No live inference, real evaluation run,
golden-label save or shared catalog refresh was performed.

Limitations/next action: run the documented Bedrock baseline when the operator is
ready to incur inference charges. Live account permissions, model access and
model accuracy remain unverified; no accuracy result is claimed by mocked tests.
Costs depend on the pinned rate table and reported usage, and may miss charges
from retries. This baseline uses provider-default reasoning, prompt-directed JSON
and a bounded output budget; it does not force structured decoding or repair
responses. One filing must fit the provider's text/image limits; nothing is
silently truncated. Interrupted runs have no resume feature. Direct OpenAI and
Nova baselines were not implemented at this original handoff (see the Nova
maintenance entry below). The Streamlit evaluation screen stays deferred
until requested; no UI work is part of this completed CLI milestone.

## Nova 2 Lite baseline — complete

Handoff (2026-10-22): complete. `configs/bedrock-nova-2-lite.json` selects
`us.amazon.nova-2-lite-v1:0` in `us-east-1`, a 4096-token output budget and
`settings.output_mode: "tool"`. The original Luna config and shared extraction
prompt are unchanged. Golden labels, scoring policy, review UI and sibling
packages are unchanged. The full golden evaluation remains an operator run:

```bash
.venv/bin/finbot-eval-eps run --config configs/bedrock-nova-2-lite.json
```

`evaluation/bedrock.py` adds optional `text` (default, preserves Luna behavior)
and `tool` response modes. Tool mode forces one `submit_eps` response with the
existing label schema, accepts only the `tool_use` stop reason and exactly one
correctly named tool block, and validates its input through the same label path.
It does not execute a tool or make a second model call. Invalid tool arguments,
missing/wrong/multiple tool responses and truncated/refused/text-only responses
remain errors; provider usage and original response bytes remain in the run.
No Markdown stripping, schema relaxation or observation repair was added.

The live smoke initially showed that Nova read the HTML and PNG accurately but
wrapped JSON in Markdown fences. A stronger text-only instruction still produced
fences. Following the Nova 2 tool-choice documentation, the final configuration
uses native tool arguments; the temporary wording change to the shared prompt was
reverted. Config and code hashes identify this response-mode difference in runs.
Comparisons describe complete extractor configurations, including their output
mode and provider-default reasoning, rather than isolating model quality alone.

Pricing was verified read-only using AWS Price List API `GetProducts`, catalog
version `20261016210806`, effective 2026-10-01 and published 2026-10-16. The pinned
US standard rates per million tokens are input `0.33`, output `2.75`, cache-read
`0.0825`, cache-write `0`. Nova uses no long-context rate multiplier throughout
its 1M-token context window. README records the four pricing SKUs, configuration,
run command, response modes and Luna account restriction; `.env.example` names
both model configurations. No dependency changes were needed.

Validation: predecessor suite 328 passed; final full suite **341 passed**, including
38 Bedrock tests. Compileall, `pip check` and whitespace checks passed. New tests
cover the shipped Nova config and rates, cache/long-context calculations, official
botocore Stubber text-plus-image requests and tool responses, shared-pipeline
rescoring, invalid response modes and malformed/missing/extra tool outputs.
Normal tests continue to block network and use synthetic temporary bundles.

The user-authorized live check used synthetic HTML containing reported EPS `1.23`
and a PNG containing adjusted EPS `0.85`, both USD for Q3 2026. Final tool-mode
Converse returned both exact observations with correct dates, valid against the
existing schema: 2161 input / 135 output tokens, estimated cost `$0.00108438`,
about 1.53 seconds. Four small networked probes were needed in total (three
text-format probes, one successful tool-format probe). The initial sandbox-only
attempt could not reach the endpoint; networked checks used the package's local
SDK and existing credentials. AWS MCP was used only for documentation, pricing
and read-only profile inspection. No AWS resource or account setting was changed.
Temporary smoke inputs, outputs and script were removed; no real golden labels,
evaluation outputs or catalog files were written.

Limitations: this demonstrates live access, text/image understanding and schema
compatibility on a tiny synthetic example, not golden-dataset accuracy. Run the
command above to measure that. Luna remains blocked by account-level model access
pending AWS intervention. The Streamlit evaluation screen remains a future item.

## Fiscal-period evaluation contract v2 — complete

Replace date/free-text matching in new evaluations with fiscal year, quarterly or
annual period type and fiscal quarter. Exclude cumulative/YTD observations from
the projected golden targets. Keep the reviewed source bundle, review app and
old runs intact. Version schemas, prompts, scoring, reports and saved predictions;
reject ambiguous source period descriptions and incompatible comparisons.

Handoff (2026-10-22): complete. Both shipped model configs explicitly select
`earnings_eps.fiscal.v2` and `prompts/eps-v2.txt`. The observation fields are
decimal-string `value`, ISO `currency`, `period_type` (`quarterly`/`annual`),
integer `fiscal_year`, and integer `fiscal_quarter` (1–4, null for annual).
There are no dates or free-text period fields in extraction targets, predictions,
scoring identities or v2 observation exports. Annual EPS and Q4 remain distinct;
no derived quarter or currency conversion is introduced.

- `contracts.py` and the packaged fiscal schema validate the new contract and
  project reviewed labels using explicit fiscal descriptions only. Unknown or
  ambiguous descriptions and duplicate projected identities stop before inference.
  Cumulative/YTD exclusions are explicit and recorded by case/metric/source row.
- `runner.py` freezes date-free targets in `golden.json`, preserves the original
  reviewed source in `source_snapshot.json`, and records `target_projection.json`.
  Versioned requests and the selected schema reach both command and Bedrock
  adapters without exposing labels. Existing source verification, immutable input
  checks and atomic publication still apply.
- `scoring.py`, `reports.py`, `files.py` and `extractor.py` select the versioned
  contract/policy. Fiscal scoring is exact on metric/currency/type/year/quarter
  and Decimal value. Reports show exclusions and canonical fiscal identifiers;
  Parquet year/quarter columns are nullable integers, including empty exports.
  Saved predictions require an `eps_predictions.v2` envelope and explicit contract.
- Legacy prompts/configs remain available under `prompts/eps-v1.txt` and
  `configs/legacy/`. Configs omitting `label_contract` preserve v1 behavior.
  Original v1 runs remain readable and comparable with compatible v1 runs;
  v1/v2 comparison and implicit legacy-prediction conversion are refused.

Validation: **407 tests passed**, including 141 evaluation tests. Compileall,
`pip check`, whitespace checks and the isolated wheel build passed. The built
wheel loads and validates the packaged fiscal schema outside the source tree.
Tests use synthetic temporary bundles and mocked provider calls; fiscal checks
cover projection, ambiguous labels, YTD-only/empty/annual cases, typed exports,
CLI rescoring/comparison, SDK tool schema and legacy isolation.

Read-only real-bundle QA verified 13 reviewed filings: **20 quarterly/annual
targets**, **14 cumulative/YTD exclusions**, and no ambiguous descriptions.
All 261 source files were hash-verified unchanged. The previous Nova v1 run was
successfully loaded, compared with itself and verified unchanged. Temporary QA
snapshots were removed. No live inference or shared output/catalog writes were
performed. The next operator action is a fresh run with the same command:

```bash
.venv/bin/finbot-eval-eps run --config configs/bedrock-nova-2-lite.json
```

The Streamlit evaluation screen remains a future roadmap item; the existing
review app and original human-reviewed source schema are unchanged.

## Extraction prompt v3 — implemented and evaluated

The fiscal v2 Nova run `20261022T182538Z-553cc644` completed without extraction
errors: 17 correct, 1 incorrect, 2 missing and 18 extra observations; 5/13 exact
filings. This is the baseline for a prompt-only experiment, with the same source
revision and strict fiscal scoring. The remaining errors include historical
comparisons, cumulative values mislabeled as annual or quarterly, misread table
columns, missed adjusted-EPS wording and omitted USD ADR amounts.

`prompts/eps-v3.txt` adds explicit period/column selection, excludes cumulative
figures without relabeling or arithmetic, recognizes adjusted EPS described as
excluding items, and retains explicitly stated local-currency and USD ADR/ADS
amounts. The rules contain no company names or golden answers.
`configs/bedrock-nova-2-lite-prompt-v3.json` changes only the extractor name and
prompt path from the existing Nova config. The baseline configs/prompts, model
settings, preprocessing, fiscal v2 contract and scoring remain unchanged.

Validation and handoff (2026-10-22): **407 tests passed**; compileall and whitespace
checks passed. The mocked Bedrock integration runs both Nova configs, verifies
the selected prompt reaches the provider and is frozen in the output, checks
matching model/settings/schema/pricing, and successfully compares their reports.
Read-only QA confirmed the unchanged baseline prompt matches the saved run and
the candidate config differs only in name/prompt path. No runtime code, dependency,
golden data, existing run or catalog changes were made, and no live inference was
performed. Run the new config and compare the resulting report with the fiscal
v2 baseline to measure accuracy; offline checks cannot establish prompt
improvement. The Streamlit evaluation screen remains deferred.

Operator result: `20261022T193052Z-e7a6a26a` used the same frozen dataset revision
and scored 16 correct, 0 incorrect, 4 missing and 2 extra; 9/13 exact filings,
F1 84.2% versus the v2 prompt's 60.7%. JPM and GM failed validation because their
responses contained conflicting duplicate fiscal identities, so all four expected
observations in those filings counted as missing. DPZ and RTX each emitted a
nine-month figure mislabeled as annual. Those two extras are the next focused
experiment; the duplicate-response behavior is deferred.

## Extraction prompt v4: exclude partial-year multiquarter aggregations

Implemented `prompts/eps-v4.txt` and the separate
`configs/bedrock-nova-2-lite-prompt-v4.json`. Relative to v3, period classification
distinguishes standalone quarters,
partial-year multiquarter aggregations and explicitly reported complete fiscal
years. Q1-Q2, Q1-Q3 and other partial-year cumulative/YTD totals are excluded
without relabeling them as quarterly or annual EPS. Complete-year results remain
eligible for a selected annual reporting period. A selected quarterly reporting
period permits no annual observations. A synthetic table illustrates omitting a
multiquarter total without using a particular company or aggregation length.
No company names or expected golden values are embedded in the prompt. Only the
prompt/name change; model, settings, pricing, preprocessing, fiscal v2 response
schema and scoring are fixed. The existing v2/v3 prompts and saved runs remain
available for comparison. No automatic filtering or duplicate repair is added.

Validation and handoff (2026-10-22): **407 tests passed**; compileall and whitespace
checks passed. After generalizing the wording, the mocked Bedrock integration
passed again with all three prompt configs, confirming prompt delivery, frozen
artifacts, unchanged settings and compatible comparisons. No live inference or
shared-data writes were performed. A fresh operator run with the v4 config must
establish whether DPZ/RTX extras disappear without regressions; compare against
`20261022T193052Z-e7a6a26a`. The Streamlit evaluation screen stays deferred.

Operator results: v4 run `20261022T200445Z-86cc5fd2` scored 20 correct, 0 missing,
1 extra and 12/13 exact filings (F1 97.6%). Repeat run
`20261022T200807Z-087b9cd4` scored 18 correct, 2 missing, 2 extra and 10/13 exact
filings (F1 90.0%). Both had no extraction errors and identical prompt/config,
dataset revision and implementation hashes. DPZ's cumulative-as-annual extra
persisted; the repeat also mislabeled ASML's EUR amount as USD and omitted TSMC's
USD ADR amount. These runs demonstrate variation, not a consistently solved set.

## Extraction prompt v5: source currency, ADR and period-heading evidence

Inspection of the frozen source documents, ASML's statement image, and the text
sent to Nova confirmed that the relevant evidence is present. ASML's statement
declares euros despite its US GAAP title. TSMC prints ordinary-share and USD ADR
EPS in the same sentence. DPZ distinguishes "Third Quarter" from "Three Fiscal
Quarters" in grouped headers; flattening makes their relationship less explicit,
but both headings survive in the model input.

Implemented `prompts/eps-v5.txt` and the separate
`configs/bedrock-nova-2-lite-prompt-v5.json`. The revision uses statement/table
currency declarations rather than accounting standards to establish currency,
retains explicitly reported parenthetical ADR/ADS amounts, distinguishes ordinal
quarters from quarter counts, and adds a final source currency/share-unit/complete
period-heading check. Rules are general and embed no company names or golden
answers. Relative to v4 only name/prompt change; model settings, pricing,
preprocessing, fiscal v2 response schema and strict scoring stay fixed.

Validation and handoff (2026-10-22): **407 tests passed**; compileall and whitespace
checks passed. The existing mocked Bedrock integration now exercises all four
fiscal prompt configs, verifies prompt delivery and frozen artifacts, checks
identical settings/schema/pricing and successfully compares the reports. Read-only
QA confirmed v4 still matches both saved v4 prompts and the v5 config changes
only name/prompt path. Existing prompts, reviewed data and saved runs are
preserved; no live inference or shared-data writes were performed during
implementation. The later operator result follows. The Streamlit evaluation
screen remains deferred.

Operator v5 result: `20261022T202959Z-f8208a78` scored 17 correct, 3 missing and
6 extra; 9/13 exact filings and F1 79.1%, with one extraction error. ASML currency
and DPZ cumulative misclassification persisted, JPM included historical quarters,
and GM used fiscal quarter 9 for nine-month amounts, invalidating that filing.
TSMC returned both currencies. This run did not demonstrate a v5 improvement;
the next experiment holds v4 fixed and varies input representation.

## Entire HTML input experiment — implemented and evaluated

Add top-level Bedrock `html_input` selection: `plain_text` (omitted/default,
preserving existing behavior) or `raw_html`. Raw mode sends the complete UTF-8
HTML in Converse text blocks with attachment names, without parsing, cleaning,
rendering or external fetches. Original image bytes, source verification, size
limits, model settings, output handling and fiscal scoring remain unchanged.
Invalid encoding/empty raw attachments fail explicitly; nothing is truncated or
replaced to fit a context limit.

`configs/bedrock-nova-2-lite-prompt-v4-raw-html.json` pins the v4 prompt and all
existing inference/pricing settings. Frozen requests/configs record the mode and
run metadata identifies the preprocessing version. Reports/comparisons show
provider input/output token totals alongside score, runtime and estimated cost,
with missing counts shown as partial/unavailable rather than zero. Existing
per-case native usage and cache-aware cost accounting are retained. Old runs are
read without modification and remain comparable under their original policy.

Read-only input preparation over all 13 frozen filings / 27 HTML attachments
produced 17,616,432 raw-HTML text characters versus 1,375,708 plain-text characters
(including context/attachment labels), a 12.81x character ratio. All attachments
decoded as UTF-8. This is not a token or cost estimate; provider usage from the
operator's raw run will establish token/cost changes. Large raw filings may
exceed provider context limits, which must remain visible in results.

Validation and handoff (2026-10-22): **426 tests passed**, including 160 evaluation
tests. Compileall, `pip check` and whitespace checks passed. Tests verify exact
raw HTML including scripts/styles/merged headers/whitespace, unchanged image
bytes, explicit invalid input handling, SDK request shapes for both modes,
v4 prompt/settings invariance, immutable source data, comparable run artifacts
and partial usage reporting. Read-only real-input preparation covered all 13
filings and 27 HTML attachments; an actual old-v4 comparison now displays
397,473 input tokens in each prior run without rewriting either run. AWS MCP
documentation confirmed the Converse text-block shape; integration checks use
mocked clients and SDK Stubber. No live inference or shared-data writes occurred.
The next operator run is:

```bash
.venv/bin/finbot-eval-eps run --config configs/bedrock-nova-2-lite-prompt-v4-raw-html.json
```

Compare the resulting run against a saved v4 plain-text run to assess accuracy,
usage, latency and estimated cost. After the raw baseline is measured, experiment
with cleaned HTML that preserves tables and grouped headers. The Streamlit
evaluation screen remains deferred.

Operator raw result: `20261022T204355Z-7411a967` scored 13 correct, 7 missing and
7 extra; 4/13 exact filings and F1 65.0%. It consumed 4,173,479 reported input
tokens and 1,593 output tokens across 12/13 filings, took 339.73 seconds and had
known estimated cost $1.38162882 (incomplete). JPM had a provider
ValidationException whose full cause was not retained, and GM failed duplicate
identity validation. This raw experiment was slower, more expensive and less
accurate than either v4 text run. The cleaned comparison is recorded below.

## Cleaned HTML input experiment — implemented and evaluated

Add `html_input: "cleaned_html"` and
`configs/bedrock-nova-2-lite-prompt-v4-cleaned-html.json`, holding the v4 prompt,
model/settings, original images, fiscal schema, scoring and pricing fixed.
`evaluation/html_input.py` parses source HTML5 into compact structural markup.
It retains headings, paragraphs, visible values, notes, lists, captions and
table/header/merged/empty-cell relationships, removing presentation attributes,
scripts/styles/comments, explicit navigation, explicit hidden content and inline
XBRL metadata headers. Visible formatting/XBRL wrappers are unwrapped without
interpreting financial facts. Link text and image filenames/alt text survive;
URLs and inline image data are removed. Source files are never rewritten or
fetched. The cleaner does not compute CSS layout, classify EPS, select target
rows or truncate to meet provider limits. No new dependency is introduced.

Frozen requests/configs record the mode, while `cleaned_html.html5.v1` and the
cleaner implementation hash identify preprocessing in the run. Existing plain
text/raw modes remain available. Report and comparison token/runtime/cost handling
is shared without changing strict fiscal scoring.

Read-only preparation over the same 13 filings / 27 HTML attachments measured
3,383,705 cleaned text characters versus 17,616,432 raw and 1,375,708 plain text,
including context/attachment names (about 81% smaller than raw). Targeted QA
confirmed ASML's euro declaration and diluted value, TSMC's parenthetical ADR
amount, and DPZ's grouped quarter/cumulative headings and merged cells survive.
Characters are not a token or cost estimate; live provider usage is still needed.

Validation and handoff (2026-10-22): **440 tests passed**, including 174 evaluation
tests. Compileall and whitespace checks passed. Offline tests cover text and
number retention, grouped/empty/nested tables, hidden-node tails, image references,
encodings, imperfect HTML, identical provider settings and prompt, original image
bytes, SDK shapes for all three modes and compatible reports. Read-only QA
prepared all real inputs and checked ASML/TSMC/DPZ evidence without modifying
original data or prior runs. No live inference or shared-data writes occurred.
The next operator run is:

```bash
.venv/bin/finbot-eval-eps run --config configs/bedrock-nova-2-lite-prompt-v4-cleaned-html.json
```

Compare against v4 plain text and raw HTML to measure whether retained structure
helps accuracy at lower input cost than raw HTML; character counts alone do not
establish this. The Streamlit evaluation screen remains deferred.

Operator cleaned result: `20261022T220153Z-ac6f92af` scored 16 correct, 0
incorrect, 4 missing and 5 extra; 8/13 exact filings, F1 78.0%, with two output
validation errors. All 13 filings reported usage: 997,809 input tokens, 1,754
output tokens, 78.10 seconds and $0.33410047 known estimated cost. ASML currency
persisted; DPZ assigned quarterly and cumulative values to the same identity;
GM used quarter 9; GS/RTX produced cumulative/reported amounts as adjusted EPS.
JPM, TSMC and CMC matched. Cleaning improved on raw HTML but did not outperform
either text run. The chosen baseline is v4 plain text as stated above.

## Documentation consolidation — complete

Handoff (2026-10-22): README quick start, config guide and offline-scoring/path
examples now use the recommended v4 plain-text config. Detailed experiment
history lives in `docs/EVALUATION_EXPERIMENTS.md`, including all measured runs,
failure modes, incomplete raw costs, repeat variation and the lack of held-out
validation. Removed stale README claims that the dataset is awaiting review and
that live HTML comparisons are pending. The environment example points to v4.
Existing configs/prompts, code, golden data, reports and future Streamlit scope
are preserved. Validation: **440 tests passed**; whitespace checks passed. Local
Markdown links and config references were checked; the seven saved run integrity
inventories and documented F1/exact-filing/cost/token figures were verified
read-only. The v4 prompt and inference settings align across input modes.
This handoff changed documentation and environment-example comments only;
no new tests, live inference, data/catalog writes or runtime changes were needed.

## Alternative model configurations — complete

Prepare four explicit v4 plain-text-plus-original-image configs for Claude
Sonnet 4.6, Kimi K3, Mistral Large 3 and Qwen3 VL 235B A22B. Preserve the Nova
baseline, golden source, prompt, fiscal v2 scoring and existing run artifacts.
No provider inference or AWS resource/account changes are part of preparation.

- [x] Verify current model IDs, account availability and documented Converse support.
- [x] Add configs, document response-mode differences and verified/unknown pricing.
- [x] Add offline text/image request and compatible-run comparison checks.
- [x] Run the full package checks and record the final handoff.

Handoff (2026-10-22): added `configs/bedrock-claude-sonnet-4-6-prompt-v4.json`,
`bedrock-kimi-k3-prompt-v4.json`, `bedrock-mistral-large-3-prompt-v4.json` and
`bedrock-qwen3-vl-235b-prompt-v4.json`. All select the unchanged v4 prompt,
plain-text HTML, original images, fiscal v2 labels, `us-east-1`, 4096 output tokens
and 120-second read timeout. Sonnet uses existing forced-tool mode; the other
three use strict JSON text mode because specific named forced-tool support was
not established. The shared adapter, schemas, scoring and baseline are unchanged.
Kimi retains provider-default reasoning (maximum effort); budget exhaustion stays
a visible error rather than triggering a retry with different settings.

Read-only AWS MCP calls verified account availability for all four and their
US profile/direct IDs. AWS model cards confirm Converse support. Kimi's full US
standard pricing was checked against its card and Price List catalog
`20261016210806` and pinned in its config. Sonnet/Mistral/Qwen omit optional
pricing: Sonnet's complete table was not established through Price List, while
the Mistral/Qwen input/output records do not establish complete cache rates.
Their cost stays unknown; README records this limitation rather than borrowing
Nova prices. README and `.env.example` list the new configs and explicit run
commands, response-mode differences, reasoning/input limits and comparison rules.

Validation: **445 tests passed**, including five new checks in
`tests/test_evaluation_model_configs.py`. Mocked requests verify text plus exact
original image bytes, unchanged prompt/schema, model IDs and response modes.
Full synthetic candidate runs freeze the same targets, preserve source hashes,
score correctly, retain known/unknown costs and compare with a synthetic Nova
run. Compileall, import/version, `pip check` and whitespace checks passed. The
documented isolated wheel build passed with network access for setuptools;
an initial offline build lacked setuptools and sandbox DNS blocked its download.
No runtime/dependency changes, live inference, golden-label or catalog writes,
AWS resource/account changes, or sibling-package changes were made. Live provider
compatibility, local invocation permissions and candidate accuracy remain to be
measured by the explicit paid run commands. The Streamlit evaluation screen
remains deferred.

## Direct OpenAI and Anthropic evaluation — complete

Add optional direct providers for GPT-6 Luna and Claude Haiku 5.5 using the same
v4 prompt, plain-text-plus-image inputs, immutable snapshots and fiscal v2 scoring.
Document environment credentials in the existing `.env.example`; do not read or
change real keys. Provider requests use native structured outputs, with the
original full contract still enforced locally. Test offline with mocked HTTP;
no live inference is part of implementation.

Handoff (2026-10-22): complete. `evaluation/direct.py` supplies direct OpenAI
Responses and Anthropic Messages adapters through `provider: "openai"` and
`provider: "anthropic"`. Optional SDK extras are OpenAI >=2.54,<3 and Anthropic
>=1.17,<2; the validated local versions are 2.54.0 and 1.17.0. Model configs are
`configs/openai-luna-6-prompt-v4.json` (`gpt-6-luna`) and
`configs/anthropic-haiku-5-5-prompt-v4.json` (`claude-haiku-5-5`). Both retain the
v4 prompt, plain-text HTML plus original manifest images, fiscal v2 scoring,
4096 output tokens, medium reasoning/effort and a 120-second per-attempt timeout.
OpenAI pins Standard, store false, disabled truncation and implicit 30-minute
caching. Anthropic pins global inference, Standard speed/tier and adaptive
thinking. Each SDK reuses one client with at most two attempts per filing, closes
it after the run, and never executes tools, repairs output or retries with a
different prompt/budget. Native endpoints are explicit and not overridden from
environment base URLs.

`extractor.py` validates new provider configs without SDK initialization;
`runner.py` freezes the exact provider-compatible output schema/version before
inference, dispatches the provider, records SDK/HTTP library versions and retains
existing source/input integrity checks and publication. OpenAI's unsupported
conditional schema keywords become quarter/annual unions; Anthropic's unsupported
fiscal-year numeric bounds remain described remotely and enforced by the original
full local schema. Other string/period rules remain in the transport schema.
Source schemas, golden labels and strict local validation/scoring are unchanged.
`bedrock.py` exposes its existing pricing validator for reuse without changing
Bedrock requests or rates. All HTML modes and conservative source bounds reuse
existing SDK-independent preparation; original image bytes are base64-encoded,
not resized or re-encoded.

Only the selected provider's OPENAI_API_KEY or ANTHROPIC_API_KEY is required;
optional ANTHROPIC_WORKSPACE_ID supports keys without workspace scope. The existing
`.env.example` documents these exact names and explicit shell export. The real
`.env` was neither read nor changed; automatic dotenv loading is still absent.
Secrets are never config fields, prompts, run metadata or SDK error messages.
Offline saved-prediction scoring requires neither credentials nor a client.
Successful native bodies remain in `.provider.json`; normalized usage retains
native `providerUsage`, separates OpenAI inclusive cache counts, retains Anthropic
separate cache counts, and counts reasoning output exactly once. Missing/invalid
usage leaves cost unknown. Billed usage survives invalid/refused/truncated output.
Both configs pin current global Standard rates; Luna has a 272K prompt threshold
with 2x input/cache and 1.5x output, Haiku a 100K threshold with 5x all rates.
README supplies installation, environment setup, run/compare commands, transport
schema semantics and operational limitations, with official pricing references.

Validation: predecessor suite 445 passed; final **492 tests passed**, including
47 new direct-provider checks. Real SDKs use synthetic HTTP transports with
network connections blocked. Tests cover text and exact image bytes, structured
request schemas/settings, cache/reasoning usage, per-request pricing thresholds,
malformed/fenced/duplicate JSON, invalid labels, refusal/truncation, sanitized
authentication errors, changed frozen schemas/sources, client reuse/closure,
input preservation, complete run inventories, comparable runs, missing keys,
no automatic dotenv loading, pinned endpoints and offline rescoring. Compileall,
import isolation, `pip check` and whitespace checks passed. The isolated wheel
built with network access for temporary build dependencies; its direct module
matches source, SDK extra constraints are included, and extracted-wheel imports
plus the fiscal schema passed outside the source tree without initializing any
provider SDK. Existing Bedrock/UI checks remain passing. No real data/catalog,
prior run, AWS resource, sibling repository or secret was modified. Live direct
account access and model accuracy still require explicit operator runs. Provider
request/context limits may be stricter than shared source bounds, and unknown
retry charges are not established by cost estimates. The evaluation UI stays
deferred.

## Direct Anthropic maintenance — Haiku rejects speed — complete

Operator run `20261022T232238Z-2ae9a23b` returned HTTP 400 on all 13 cases in
7.34 seconds, with no reported usage. A single replay of TSM into a temporary
directory reproduced the provider error: Haiku 5.5 does not support the `speed`
parameter. Remove `speed: "standard"` instead of changing credentials or the
prompt/schema. Add an HTTP-request regression and safe static error hints for
known unsupported-speed, workspace-scope and credit-balance failures.

Handoff (2026-10-22): `evaluation/direct.py` now omits `speed` from Anthropic
Messages requests; the provider default applies. No model/prompt/schema/pricing
or golden data changes were needed. `request_error()` retains only static
diagnostic hints and a confined provider request ID. Raw SDK messages, bodies,
headers and credentials are still never persisted. Unknown errors keep the
generic status/type message. `tests/test_evaluation_direct.py` asserts absence
of speed in the actual SDK-serialized request, tests known diagnostic categories,
and rejects arbitrary request IDs/error-body text. README documents the failure
and unchanged rerun command.

Validation: **498 tests passed**, including 53 direct-provider tests. Compileall,
`pip check`, whitespace checks and the isolated wheel build passed. One TSM replay
against Anthropic reproduced HTTP 400 and identified the unsupported speed field;
one replay after the fix completed in 3.06 seconds with TWD `29.43` and USD `4.60`
for FY2026 Q3 and an empty adjusted array, valid against the unchanged fiscal
schema. Provider usage: 5,972 input / 299 output tokens; known estimated cost
`$0.0007467`. Replays copied only frozen label-free inputs into temporary
directories, removed afterward. Diagnostic output redacted keys and did not
print headers. The failed and successful full operator run inventories were
verified unchanged; there was no full-job rerun, golden-label save or catalog
write. The original failed Haiku run remains historical evidence. A fresh full
Haiku run is the next operator action; the one-filing check does not establish
whole-sample accuracy. The operator's separate Luna run
`20261022T232136Z-eea4d640` already completed with all 20 targets correct and
13/13 exact filings, 51.45 seconds and `$0.054453210` known estimated cost.

## Experiment report consolidation — complete

Handoff (2026-10-22): added `docs/MODEL_EXPERIMENT_REPORT.md` at the user's request.
It covers all 18 saved full-bundle runs, separates legacy and fiscal contracts,
and includes performance, token/cache, cost-basis and exact run-ID tables.
Sonnet/Mistral/Qwen costs are explicit post-hoc calculations; missing request
usage remains unknown. Luna repeatability and caching, Haiku's CMC price threshold,
and provider/output failures are explained. README links/statuses and the earlier
Nova report now point to the complete record. No configs, prompts, runtime code,
golden data, saved run artifacts or catalog outputs were changed for this report.

Validation: all 18 run integrity inventories and fiscal revision/membership/policy
compatibility verified read-only; 36 metric rows, cost arithmetic, all run IDs
and local Markdown links checked against saved artifacts. **498 tests passed**;
`git diff --check` passed. This was a documentation-only change; no new tests
or live provider calls were needed.

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
| 4 | Durable saves and synchronized exports | Step 3 | Complete |
| 5 | Confirmation and guarded navigation | Step 4 | Complete |
| 6 | Progress and catalog refresh | Step 5 | Complete |
| 7 | End-to-end verification and operating docs | Step 6 | Complete |

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

Working commands (run from this repository root; Save/Retry write the selected bundle):

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

- [x] Serialize writes with a dataset-level local writer lock; inside the lock
  compare the case's current fingerprint with the opened version. A conflict
  preserves pending edits and refuses to overwrite the external change.
- [x] Revalidate source integrity and proposed labels, back up the prior case,
  and atomically replace case.json. Preserve filing/documents/provenance fields.
  Implement the agreed invalidation/no-op semantics for previously reviewed cases.
- [x] From authoritative case files, rebuild labels.json/Parquet, label metadata,
  observation/review counts and state in dataset.json, and REVIEW.md. Maintain
  original creation time and acquisition facts; update modification metadata.
- [x] Refresh integrity.json last. Verify source manifests/hashes, but do not
  rewrite source documents, provenance, acquisition snapshots or label schema.
  Label exports retain case_id, ticker, filing_id, form_type, metric, the five
  observation fields, and review_status; reviewed/unreviewed rows remain distinct.
  Preserve values and dates as strings (nullable start dates), matching the
  initial flat export schema. Do not introduce floating-point EPS columns.
- [x] Keep backups, writer lock and recovery state under `.review/`, excluded
  explicitly from current-bundle integrity hashing. Make a durable pending marker
  before committing a case, recording its expected replacement fingerprint.
- [x] Stage/validate derived files before replacement where possible. Individual
  atomic writes are not a multi-file transaction: an interrupted save must be
  recognized as synchronization pending, not a healthy complete save.
- [x] Retry/recover from authoritative cases under the writer lock; accept an
  interrupted case change only when it matches the pending marker. Unexpected
  integrity mismatches still fail. Clear the marker only after all exports/hashes
  agree. Distinguish “labels saved, exports need retry” from “nothing saved.”

Acceptance: save/reopen preserves edits and notes; source bytes are unchanged;
JSON/Parquet/manifest/review counts agree; backup exists; stale second sessions
cannot overwrite; injected failures before/after the case commit and during an
export are recoverable after restart without losing labels or claiming success.
Do not test this writer on the real review dataset. Catalog wiring waits for 6.

Handoff (2026-10-21 UTC): complete. Implementation:

- `review/persistence.py`: `save_changes(root, case_id, opened_fingerprint,
  labels, clock=...)`, `retry_synchronization(root)`, read-only
  `synchronization_pending(root)` and `verify_bundle(dataset)`. Returns
  `SaveResult(dataset, case_id, changed)` only after full export/integrity
  verification. `SaveConflict` refuses stale writes; `SynchronizationPending`
  exposes `committed` and distinguishes nothing saved from labels committed
  with exports needing retry. The injectable clock returns an explicit UTC datetime.
- A local dataset-level POSIX `flock` on `.review/writer.lock` serializes writers.
  A retained lock filename is not a stale lock; process exit releases ownership.
  Writer paths reject symlinks, including aliases inside the bundle. Preflight
  checks all bundle hashes/membership, source snapshots/documents, document
  inventory/metadata and flat JSON/Parquet labels against authoritative cases.
- Recovery format v1: `.review/pending.json` records `version`, a UUID transaction
  ID, `case_path`, `backup`, `backup_canonical`, UTC `timestamp`, full baseline
  file hashes/sizes, `integrity_before`, and ordered `replacements` hashes/sizes.
  `.review/<transaction-id>/case.before.json` retains exact prior case bytes;
  numbered files in that directory retain staged replacement bytes. Everything
  is flushed/fsynced before the durable marker is written and before case commit.
  State and backups remain outside bundle integrity scope; no automatic pruning.
- Replacements are atomic individually: case first, label exports/metadata,
  dataset manifest and review guide next, integrity last. Recovery accepts each
  bundle file only at its baseline or exact planned replacement hash; immutable
  sources must match baseline. It validates the backup and intended label/review
  transition, rebuilds staged exports from cases plus the journal's intended case,
  rechecks complete integrity, then durably clears the marker. This rolls forward
  pre-commit interruptions as well as post-commit/export interruptions. Marker
  cleanup failures retain recoverable state. No multi-file transaction is claimed.
- `review/exports.py`: lossless flat rows and explicit string-only PyArrow schema,
  including an entirely empty export; matching JSON/Parquet; observation, filing,
  reviewed/unreviewed counts and aggregate review state; label metadata, Parquet
  hash and REVIEW.md with current labels, source links, policy and review notes.
  Dataset creation time and upstream metadata remain intact. Label metadata
  preserves its initial generation as creation time and updates generation and
  modification timestamps. Source/acquisition files and schema are not rewritten.
- `review/app.py`, `session.py`, `dataset.py`: Save changes, saved-draft rebasing,
  current-disk Discard, conflict/error messages and Retry synchronization. The app
  detects pending recovery before loading aggregate counts, visibly blocks Save
  and filing navigation, and retains drafts through failures. The loader's
  `validate_counts=False` option permits pending stale aggregate counts while
  preserving source/label checks. Normal loading still validates counts.
- `tests/conftest.py`, `test_review_persistence.py`, `test_review_app.py`, README:
  complete synthetic bundles, fake clocks, independent legacy-format exports,
  precision/null/currency preservation, backups/source invariance, additions and
  empty outputs, no/some/all-reviewed states, reviewed no-op/invalidation, stale
  sessions, process locking/exit, symlink refusal and UI Save/restart/retry flows.
  Faults cover staging, marker preparation, before case commit, several export
  boundaries, integrity replacement, final verification and marker removal/fsync.
  Uncaught interruption retains the durable journal. Unexpected case/source/
  provenance/export/integrity/staging changes and new bundle files refuse recovery.

Checks: predecessor baseline 140 tests passed; final 184 tests passed with network
connections blocked. Python 3.14.8 repo-local compileall, import/version, `pip check`
and `git diff --check` passed. The documented isolated wheel build passed; extracted
wheel imports, new modules and packaged schema were verified. Streamlit started
on localhost port 8514 with an explicit disposable synthetic bundle (headless,
usage stats disabled); the health endpoint returned HTTP 200 / `ok`, then the
process and temporary data were removed. Sandbox DNS blocked the first isolated
build; an offline attempt lacked setuptools; the unchanged documented command
succeeded with network access. Sandbox localhost binding was initially blocked;
the authorized local startup check succeeded outside the sandbox. No real shared
dataset was written. UI validation used Streamlit AppTest; no visual browser
inspection is claimed for this step.

Limitations/next action: Step 5, confirmation and full Save/Discard/Stay navigation.
Step 4 supports label corrections only; Confirm and next and automatic catalog
refresh remain absent. Writer locking requires a local POSIX filesystem; staging
and backups are retained. Unexpected hash mismatches require restoring a known
consistent file set, not automatic acceptance or hash regeneration. Keep pending
`.review/` state with a copied bundle. Display limitations from Step 2 remain.

## Step 5 — Confirmation and guarded navigation

Prerequisite: Step 4 save/export service. Deliver confirmation/navigation in the
app and session-state helpers, using that same persistence path.

- [x] Implement Save changes and Confirm and next with distinct review semantics.
  Confirmation timestamps come from an injectable UTC clock, not UI-supplied dates.
- [x] Add previous/next and direct filing selection in manifest order. Only move
  after a successful requested save/confirmation; pending recovery keeps the user
  on the current case. Last-case confirmation shows completion without wrapping.
- [x] When leaving with edits, offer Save, Discard or Stay. Discard restores the
  last saved case and clears its stale editor widget state. Attachment switching
  preserves pending labels and requires no extra confirmation.
- [x] Restore saved labels/status on restart and prevent state leaking between
  filings or dataset paths. Session-only editing never counts as a durable review.
- [x] Allow confirmation of valid empty arrays or explicitly retained null starts;
  keep their meaning and current review notes visible.

Acceptance: complete Save/Confirm flows persist different states; a failed save
never advances; Save of changed reviewed labels invalidates confirmation; a no-op
save preserves it. Save/Discard/Stay and last-case navigation behave correctly;
restart restores saved state. Use temporary data and deterministic timestamps.

Handoff (2026-10-21 UTC): complete. Implementation:

- `review/persistence.py`: `confirm_case(root, case_id, opened_fingerprint,
  labels, clock=...)` shares the existing serialized save, backup, staged export,
  integrity and recovery path. It sets `human_reviewed` and an explicit UTC
  timestamp from the injectable writer clock, including when labels are unchanged.
  A fresh confirmation records a fresh clock value. Save changes still leaves
  unreviewed cases unreviewed, invalidates confirmation after changed labels and
  preserves confirmation on a no-op. `SaveResult.changed` includes review changes.
- Recovery journals remain v1, with an `action` of `save_changes` or `confirm`.
  Journals from Step 4 without an action default to label saves. Recovery validates
  the action's exact review transition against the original case and recorded UTC
  timestamp before writing; retries preserve that timestamp rather than calling
  the clock again. Unknown actions or inconsistent review transitions are refused.
- `review/app.py`: Confirm and next, Previous, Next and direct filing selection
  follow manifest order. Successful confirmation advances only after synchronized
  persistence; confirming the last case stays there with an end-of-list message,
  without claiming earlier cases were confirmed. Saved confirmation time/status,
  review notes, empty-metric explanations and null-start warnings remain visible.
- Leaving with edits keeps the current case and offers Save/Discard/Stay. Save
  persists valid labels before moving; Discard reloads the latest durable case at
  click time and clears old widget deltas before moving; Stay retains edits. Invalid
  rows disable Save/Confirm but still allow Discard/Stay. Standalone Save changes
  and Discard changes stay on the current filing. Attachment changes need no guard.
- `review/session.py`: `NavigationGuard` retains the requested destination and
  `adjacent_case()` avoids boundary wrapping. Navigation callbacks capture editor
  deltas arriving with the same event and check current on-disk pending state.
  A synchronization failure retains the current case, draft and session destination
  and blocks writes/navigation. Retry finishes synchronization without advancing;
  choose navigation again (or the guard's Save/Discard) afterward. Restart restores
  saved labels/status, starts at the first manifest case and drops session requests.
- Drafts, destinations, selectors and attachment choices remain namespaced by
  resolved dataset path and case. `EditorDraft.resume()` recreates a hidden widget
  from retained rows after switching dataset paths, including partial rows, while
  Discard still restores saved labels. No editor state crosses filing boundaries.
- `tests/test_review_{persistence,app,editor}.py`, README and roadmap: deterministic
  confirmation timestamps, unchanged/corrected/empty labels, null starts, review
  metadata preservation, no-op/invalidation, stale/invalid refusals, pre/post-commit
  confirmation recovery, legacy journals, all Save/Discard/Stay navigation routes,
  delayed events, new external pending saves, manifest order, last-case completion,
  widget cleanup, restart and dataset-path isolation.

Checks: predecessor baseline 184 tests passed; final 217 tests passed with network
connections blocked. Repo-local Python 3.14.8 compileall, import/version, `pip check`
and `git diff --check` passed. The documented isolated wheel build passed; imports
from the extracted wheel, confirmation/navigation helpers and packaged schema were
verified outside the source tree. Streamlit started on localhost port 8515 with an
explicit disposable synthetic bundle (headless, usage stats disabled), and its
health endpoint returned HTTP 200 / `ok`. The bundle bytes were unchanged; the
process and temporary files were removed. Sandbox DNS initially blocked the build
and localhost binding initially blocked startup; the same checks passed outside
the sandbox. AppTest exercised actual Streamlit editor and navigation state; no
visual browser inspection is claimed. No real shared dataset was changed.

Limitations/next action: Step 6, saved progress and catalog refresh. Automatic
catalog refresh remains absent. Navigation destinations, drafts and attachment
choices remain session-only. Existing local POSIX locking, retained backups and
HTML display limitations still apply. Full real-browser workflow QA remains Step 7.

## Step 6 — Progress and catalog refresh

Prerequisite: Step 5 complete persisted review flow. Deliver progress UI and a
small catalog-command adapter; dataset aggregate/export semantics already exist
from Step 4 and must not be deferred until here.

- [x] Show saved reviewed/unreviewed counts, filing statuses and overall state;
  derive them from cases rather than initial constants or unsaved session flags.
- [x] Verify aggregate flags and per-row export states for no/some/all reviewed
  cases, including reverting a previously complete dataset after a label edit.
- [x] After successful synchronized saves to the canonical shared dataset, invoke
  the sibling finbot-catalog CLI as a subprocess argument list, not a shell string
  or sibling Python import. Default to its repo-local interpreter and
  `scripts/build_catalog.py --data-root <FINBOT_DATA_ROOT>`; allow a documented
  `--catalog-repo` override. No catalog source changes are required.
- [x] Disable automatic catalog refresh for explicit noncanonical dataset copies,
  including temporary fixtures. Missing/broken catalog tooling or a failed refresh
  must not undo saved labels or hide the failure; show catalog refresh pending and
  let the user retry. Do not claim catalog freshness before success.

Acceptance: progress survives restart and label edits; all-reviewed flags are
accurate; catalog adapter has mocked success/failure tests and never runs in normal
UI/unit tests. Temporary-copy use performs no shared catalog writes. Confirm the
real catalog integration only after an explicitly requested real review save.

Handoff (2026-10-21 UTC): complete. Implementation:

- `review/app.py`: sidebar progress bar, saved reviewed/unreviewed counts and
  overall state, plus an expandable manifest-order filing-status table. Uses
  `exports.review_state()` on authoritative cases, never draft/editor flags or
  initial counts. Pending synchronization labels progress as saved case state
  with exports still pending. Existing filing selectors retain their statuses.
- `review/config.py`: `parse_config()` returns `ReviewConfig(dataset_root,
  data_root, catalog_repo)`. `--catalog-repo` defaults to the sibling repository;
  `parse_dataset_root()` remains compatible. Catalog enablement requires
  FINBOT_DATA_ROOT and exact resolved canonical-path equality, including an
  explicit canonical override. Copies and standalone overrides are disabled;
  changing the catalog repository cannot enable a noncanonical dataset.
- `review/catalog.py`: UI-independent `refresh_catalog(config)` invokes
  `<catalog-repo>/.venv/bin/python <catalog-repo>/scripts/build_catalog.py
  --data-root <FINBOT_DATA_ROOT>` as an argument list, with the catalog repo as
  cwd, checked exit status, captured output and a 60-second timeout. It verifies
  synchronized bundle inputs and holds the existing writer lock through the
  subprocess and receipt replacement. No sibling imports or catalog source
  changes. Missing tools, execution failures, timeouts and receipt errors become
  actionable review errors without changing labels or pretending refresh worked.
- `.review/catalog-refresh.json` is an atomic operational receipt outside bundle
  integrity: pending before a CLI attempt, successful only after a zero exit and
  durable receipt replacement. Success records the integrity SHA-256, shared-root
  path and UTC time. Read-only `refresh_status()` reports disabled/unknown/pending/
  current. A saved transaction without a matching receipt remains pending after
  restart, including interruption between saving and invoking the adapter. Moved
  bundles do not transfer freshness to a different shared root. A missing receipt
  with no review transactions reports unknown; malformed receipts report pending.
- The app refreshes after changed synchronized Save changes, navigation Save,
  Confirm and next, and successful Retry synchronization. Catalog failure retains
  successful save/confirmation/navigation, displays a separate pending warning,
  and offers Retry catalog refresh without saving drafts or navigating. Recovery
  must finish first. Opening, editing, discarding, ordinary navigation and no-op
  saves never launch the CLI. Opening pending catalog state does not auto-retry.
- `tests/test_review_catalog.py`, config/app/persistence tests and fixtures:
  mocked subprocess success, missing tooling, permission/nonzero/timeout failures,
  durable pending/retry, corrupt receipts, receipt-write failure, moved-root
  invalidation, source/export invariance, canonical path aliases and copies.
  AppTest covers progress through confirmation/restart/unsaved edits/invalidation,
  each save route, preserved navigation after catalog failure, restart/retry and
  recovery-before-refresh. A complete none/some/all-reviewed/invalidated sequence
  verifies manifest and metadata flags/counts plus every JSON/Parquet row state.
  An autouse guard blocks any unmocked catalog subprocess in normal tests.
- README and `.env.example`: current capabilities, catalog configuration/CLI,
  canonical-copy rules, progress meanings, separate retries, receipt semantics,
  timeout and troubleshooting. No new dependencies or sibling-package changes.

Checks: predecessor baseline 217 tests passed; final 243 tests passed with network
and unmocked catalog subprocesses blocked. Repo-local Python 3.14.8 compileall,
import/version, `pip check` and `git diff --check` passed. The documented isolated
wheel build passed; catalog/config/app imports and the packaged schema were
verified from the extracted wheel outside the source tree. Streamlit started on
localhost port 8516 with an explicit disposable synthetic bundle (headless, usage
stats disabled); the page returned HTTP 200 and health endpoint HTTP 200 / `ok`.
The synthetic bundle inventory was unchanged and no `.review/` was created; the
server and temporary bundle were removed. Sandbox DNS initially blocked the wheel
build, and sandbox localhost permissions blocked startup/health access; those
same checks passed outside the sandbox. UI checks used Streamlit AppTest; no
visual browser inspection is claimed. No real shared dataset or catalog outputs
were changed, and no real catalog command was invoked.

Limitations/next action: Step 7, full disposable-copy browser workflow and final
operating docs. Real catalog integration remains deliberately unexecuted until
an explicitly requested real review save. A receipt attests only to a successful
refresh of this saved bundle revision, not freshness of unrelated shared data or
external catalog changes. Catalog refresh may block a local review write for up
to 60 seconds while the CLI runs. Existing POSIX lock, retained backup and HTML
display limitations remain.

## Step 7 — End-to-end verification and operating docs

Prerequisite: Steps 1–6 complete, with tests and handoffs already recorded.

- [x] Exercise a disposable dataset copy in a real browser: view attachments,
  edit/add/delete observations, Save, Confirm, navigate, restart, and check outputs.
  Include empty adjusted EPS, JNJ null starts, TSM two currencies and a long report.
- [x] Verify source hashes remain unchanged, decimals survive, review state is
  accurate, exports/integrity agree, and stale-write/recovery scenarios still work.
- [x] Run compileall, the full package test suite, and the review UI tests with
  the repo-local environment. New tests must not require the shared dataset.
- [x] Finalize README setup, launch, dataset override, review meanings, backup/
  recovery and catalog troubleshooting. Document known HTML limitations and the
  working document-review commands without restoring removed legacy workflows.
- [x] Record validation evidence and remaining limitations in this roadmap; mark
  complete only when the user can perform the entire review without editing JSON.

Acceptance: the documented launch works from a clean repo-local installation;
the temporary-copy browser workflow and all package checks pass; saved labels,
review progress, exports and integrity agree after restart. No real review data
was changed during QA, and the handoff identifies any remaining display limits.

Handoff (2026-10-21 UTC): complete. Implementation and operating docs:

- `tests/test_review_app.py`: a complete synthetic-bundle workflow edits a signed
  decimal, adds/saves/deletes an adjusted observation, retains drafts across
  attachment/view changes, exercises guarded Stay/Save navigation, confirms an
  empty filing, completes all filings, restarts, then revises a confirmed filing
  and restarts again. It checks exact trailing zeroes, currencies, nullable starts,
  review state/timestamps, JSON/Parquet agreement, source/acquisition invariance,
  notes, full integrity and absence of catalog receipts/pending synchronization.
  Existing stale-session and fault-injection tests remain in the full suite.
- `review/app.py`: removed the redundant filing-selector index because the
  selected case is already assigned through session state before widget creation.
  This eliminates Streamlit's duplicate default/session-state log warning while
  preserving navigation. Full navigation/UI tests pass after the change.
- README and `docs/REVIEW_QA.md`: final setup/launch/restart commands, cell commit,
  fullscreen, add/delete row controls, complete-copy/backup instructions, browser
  checklist, read-only verification, synthetic recovery commands and practical
  troubleshooting. No JSON edits are needed for ordinary review or UI recovery.

Validation (Python 3.14.8):

```bash
.venv/bin/python -m compileall -q src tests
.venv/bin/python -m pytest
.venv/bin/python -m pytest tests/test_review_app.py
.venv/bin/python -m pip check
git diff --check
.venv/bin/python -m pip wheel --no-deps --wheel-dir /private/tmp/finbot-eps-step7-nj0igkx6/wheels .
```

Predecessor baseline: 243 passed. Final suite: 244 passed; explicit review UI
suite: 43 passed. Compileall, dependency checks and whitespace checks passed.
Normal tests blocked network connections and unmocked catalog subprocesses.
The isolated wheel built successfully. Sandbox DNS initially blocked fetching
setuptools; the same build succeeded with network access. A new isolated temporary
virtualenv, created by the repo's interpreter, installed `-e '.[dev,review]'` from
scratch; imports/version, `pip check` and all 244 tests passed (Streamlit 1.66.0,
PyArrow 26.0.0). The existing repo-local environment was retained.

Browser evidence: Firefox on localhost port 8517, with an explicit complete copy
at `/private/tmp/finbot-eps-step7-nj0igkx6/dataset-copy` and usage statistics off.
Launch commands used the repo-local interpreter initially and the clean temporary
interpreter for the final server restart:

```bash
.venv/bin/python -m streamlit run scripts/review_eps.py --server.address 127.0.0.1 --server.port 8517 --server.headless true --browser.gatherUsageStats false -- --dataset-root /private/tmp/finbot-eps-step7-nj0igkx6/dataset-copy
/private/tmp/finbot-eps-step7-nj0igkx6/clean-venv/bin/python -m streamlit run scripts/review_eps.py --server.address 127.0.0.1 --server.port 8517 --server.headless true --browser.gatherUsageStats false -- --dataset-root /private/tmp/finbot-eps-step7-nj0igkx6/dataset-copy
```

Localhost binding required sandbox escalation; both servers started successfully.
The observed workflow included:

- ASML formatted release, financial-statements attachment and readable text;
  editing to `-12.930`, adding/saving `-0.500` with a null start, deleting that
  saved adjusted row, fullscreen controls, guarded Stay and Save, return navigation
  and confirmation with an empty adjusted array. Exact saved strings were checked.
- JNJ's four unknown starts, September 27 end and operational-adjustment notes
  remained visible; confirmation retained all nulls. TSM displayed TWD `29.43`
  and USD `4.60`, the ADR note and formatted release without conversion.
- CMC's long annual-report cover, scrolling within the viewer and readable-text
  fallback were visually inspected. GM's last-case confirmation stayed at GM
  with an end-of-list message and accurate partial progress (4/13, In Progress).
- A controlled second-writer save on the copy caused a browser stale-save refusal;
  pending `5.25` was retained and Discard loaded the latest saved labels. An
  injected export failure on that copy left durable synchronization pending;
  browser writes/navigation were disabled, Retry synchronization recovered the
  recorded `4.60` value and stayed at TSM, then confirmation advanced normally.
- Stopping/restarting the server with the clean installation and reloading Firefox
  opened the first filing with saved `-12.930`, confirmation time and 4/13 progress.
  A complete hash comparison showed restart/viewing made no bundle changes.
  Saving a subsequent correction reset ASML to unreviewed, cleared its timestamp
  and reduced saved progress to 3/13. The full suite also verifies all-reviewed
  and empty-case progress, restart and invalidation independently of real inputs.

The real bundle's complete before/after inventory (105 files) was unchanged.
All 86 immutable input files in the QA copy, including original documents,
acquisition/provenance files, document exports and schema, matched their baseline
hashes. `load_dataset()` plus `verify_bundle()` checked labels/Parquet/metadata,
counts/review state and all integrity entries. No pending synchronization or
catalog receipt remained on the copy; no real catalog command was invoked.
QA servers, browser tab and temporary installation/copy were removed afterward.

Limitations: HTML remains a sanitized display derivative: no external assets,
inert source links, small source fonts, wide-table scrolling and linearized text
fallback. Long documents can take several seconds to render. Table fullscreen
helps expose all six columns. Writer locks require a local POSIX filesystem;
transactions/backups have no automatic pruning. Real catalog integration remains
deliberately unexecuted until an explicitly requested real review save; mocked
tests verify failures/retry and copies disable it. No roadmap implementation work
remains; the original labels still await the user's actual human review.

## Maintenance — Tiny text in image-based attachments

Handoff (2026-10-21): complete. Firefox inspection reproduced the blank-looking
ASML EX-99.3 attachment. Its original HTML references unavailable page images and
contains a white 1-point transcription, rather than HTML financial tables.

- `review/viewer.py` now exposes nonblank embedded text whose effective inline
  font size is at most 2px (including equivalent point sizes and zero). Only those
  elements receive readable 16px text, dark foreground, white background and
  normal line spacing. Inline importance/order is respected when detecting size;
  ordinary typography and source files are preserved. Sanitization, CSP and the
  empty iframe sandbox remain in place. A viewer notice explains the enlargement
  and missing-image/table-layout limitation. Text fallback is unchanged.
- `tests/test_review_viewer.py` adds synthetic image/transcript regressions for
  point/pixel/zero sizes, important declarations, white text, collapsed line
  spacing, ordinary typography, transcription values and unchanged text fallback.
- README documents this attachment behavior. No dependencies, label contracts,
  data files or sibling repositories changed.

Checks: 249 tests passed, including 34 focused viewer tests; compileall,
`pip check` and `git diff --check` passed. A temporary localhost preview of the
actual source derivative was visually inspected in Firefox: previously invisible
page transcriptions were readable. The existing Streamlit process still retained
the old imported viewer after opening a separate review session, so restart that
server to load the fix. No Save, Confirm or catalog action was performed.

Limitations: this exposes linear page transcriptions; missing image assets mean
the original financial-table alignment cannot be restored from this HTML alone.
The seven implementation steps above remain complete.

## Maintenance — README UI screenshot

Handoff (2026-10-22): complete. Added `docs/images/eps-review-ui.png` near the
top of README.md with descriptive alt text and a caption. Firefox's built-in
page screenshot captures the ASML filing viewer, EPS editor, review notes and
saved progress without browser chrome. Capture used a complete disposable copy
of the canonical bundle with catalog refresh disabled; no Save or Confirm action
was performed. The temporary server and screenshot tab were closed afterward.

Checks: visually inspected the saved PNG (3420 × 1733), verified the README image
target, and compared all 261 bundle file hashes before/after for both canonical
data and the copy; both were unchanged. Compileall, all 266 tests, dependency
and whitespace checks passed. No runtime behavior changed or new tests were needed.

## Boundaries for every step

The historical boundaries below govern the review UI. The separate evaluation
milestone above explicitly permits provider inference only through the evaluation
CLI; opening the review app still never invokes a provider. Its golden-data
editing and catalog behavior remain unchanged.

Maintenance (2026-10-21): supporting raster viewing is implemented alongside the
upstream selective-image change. `review/viewer.py` resolves only explicitly
supplied, hash-verified manifest rasters, validates them with Pillow, embeds
generated data-image URLs under `img-src data:` and retains the empty iframe
sandbox. Source resource URLs/events remain stripped. Page layout is preserved
by the image; a collected page's tiny transcript stays unobtrusive. Missing-page
text still receives the earlier enlargement fallback. `review/app.py` keeps
supporting assets out of attachment choices while preserving complete source
membership. README records bounds and the explicit source-refresh requirement.
Tests cover hostile/missing/corrupt images, partial page availability and a
complete synthetic image-bearing save/restart with unchanged source hashes.
Full suite: 253 passed; compileall, pip check and whitespace checks passed.
The image-bearing wrapper was also inspected in Firefox using a synthetic page
with EPS rows and quarterly/year-to-date columns; the raster preserved table
alignment and readable values. Temporary preview server/tab were removed.
Upstream recovery and migration of the real golden bundle were not performed at
that validation point; the subsequent maintenance entry below records staging.

Maintenance (2026-10-21): cloud recovery subsequently stored 50 supporting JPEGs
for ASML/BAC/UNH/CMC and published four complete snapshots. Added the offline
`review.image_refresh` operator importer. It requires local published manifests,
native acquisition records and hash-verified images; no AWS dependency, download
or sibling-package import enters the review UI. It writes only a new staged
bundle, preserving original source files, EPS values, notes and unrelated cases.
Changed packages need confirmation again; prior confirmation and provenance are
archived. Complete acquisition/source exports, Parquet sidecars and integrity are
regenerated and validated, with raster checks before publishing the staged path.
Tests cover label-save compatibility, retained history, invalid/altered manifests,
hashes, corrupt images, symlinks, pending saves and existing destinations.
The original 13-case/27-document/34-observation bundle was backed up whole with
matching file hashes. A separate staged bundle has 13 cases, 77 source artifacts
(27 unchanged HTML plus 50 JPEGs) and the same 34 observations. Canonical replacement
and catalog refresh remain separate from staging. Full package suite: 266 passed;
compileall, dependency and whitespace checks passed. Firefox inspection of the
staged ASML EX-99.3 confirmed that recovered pages and financial table columns are
visible in the sandbox. No labels were saved or confirmed during inspection.
Recovery inputs and verification evidence are retained under the shared data
root's `filing-evals/recovery/supporting-images-20261021` directory, with the
whole-bundle backup under `filing-evals/backups` and the new copy under
`filing-evals/staging`.

Keep all implementation in this repository and all generated data outside Git.
The app is a local single-user workflow, with stale-session protection; do not add
a hosted service, authentication, a database, model inference, AWS operations,
new downloads, analyst expectations or automatic EPS calculations. Do not expand
the schema with the fields intentionally omitted above. No cross-repo imports or
changes to the read-only finbot-dashboard are part of this roadmap. Tests write
only temporary fixtures; browser QA also uses copies. Preserve unrelated working
changes and the original draft/source data throughout implementation.
