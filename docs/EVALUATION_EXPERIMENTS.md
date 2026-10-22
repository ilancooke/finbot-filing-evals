# EPS evaluation experiments — 2026-10-22

This is the earlier **Nova prompt/input experiment record**. The later
[full experiment report](MODEL_EXPERIMENT_REPORT.md) covers all 18 saved runs,
including alternative Bedrock models, direct Luna/Haiku APIs and cached repeats.
Its model-selection findings supersede the Nova-only decision below.

## Current decision

Use **Nova 2 Lite through Bedrock, prompt v4, plain-text HTML extraction and
original images** as the current baseline:

```bash
export FINBOT_DATA_ROOT=/absolute/path/to/finbot/data
.venv/bin/finbot-eval-eps run --config configs/bedrock-nova-2-lite-prompt-v4.json
```

Run commands from the package root. The prompt is [eps-v4.txt](../prompts/eps-v4.txt)
and the config is [bedrock-nova-2-lite-prompt-v4.json](../configs/bedrock-nova-2-lite-prompt-v4.json).
`html_input` is omitted in that config, selecting the existing `plain_text`
default. All original collected images are still supplied. V4 is a prompt
version; the extraction contract remains `earnings_eps.fiscal.v2` and the scoring
policy remains `eps_fiscal_exact.v2`.

Plain text with v4 had the best observed accuracy/cost balance. V5 and the two
HTML input experiments did not outperform it. Keep those configs and saved runs
for reproducibility; no config alias or earlier prompt has been rewritten to
silently select a different experiment. In particular,
`configs/bedrock-nova-2-lite.json` still references prompt v2.

## Shared evaluation scope

All seven runs below use the same reviewed source revision and evaluation
targets:

- 13 human-reviewed filing packages, 27 HTML attachments and 50 original images.
- Source labels: 34 observations; fiscal projection: 20 quarterly/annual targets
  and 14 excluded partial-year cumulative/YTD observations.
- Frozen dataset revision:
  `fa4cdfb8c8f81f0d2e55c4ad135eed414b1afad35fc15d4975bb92e1a58094c9`.
- Model `us.amazon.nova-2-lite-v1:0`, region `us-east-1`, sequential Converse
  calls, forced `submit_eps` output, `max_output_tokens: 4096` and otherwise
  provider-default inference settings. The pinned pricing table is unchanged.
- Model requests contain source documents, public filing context, prompt and
  schema; human-reviewed target values and notes are not supplied to the model.

Each run is stored under `$FINBOT_DATA_ROOT/filing-evals/runs/<run_id>/`.
Its `run.json`, `results.json`, `REPORT.md` and integrity inventory are the
authoritative record. Results here were read from those artifacts; no provider
calls were made to prepare this document. Legacy v1 date-based runs use a
different contract and are excluded from these comparisons.

## Prompt outcomes

All rows here use plain-text HTML input plus the same original images.

| Prompt | Run ID | Correct | Incorrect | Missing | Extra | Exact filings | F1 | Extraction errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v2 | `20261022T182538Z-553cc644` | 17 | 1 | 2 | 18 | 5/13 | 60.7% | 0 |
| v3 | `20261022T193052Z-e7a6a26a` | 16 | 0 | 4 | 2 | 9/13 | 84.2% | 2 |
| v4, A | `20261022T200445Z-86cc5fd2` | 20 | 0 | 0 | 1 | 12/13 | 97.6% | 0 |
| v4, repeat B | `20261022T200807Z-087b9cd4` | 18 | 0 | 2 | 2 | 10/13 | 90.0% | 0 |
| v5 | `20261022T202959Z-f8208a78` | 17 | 0 | 3 | 6 | 9/13 | 79.1% | 1 |

V3 added explicit current-period/column selection, adjusted-EPS terminology and
multiple-currency/ADR instructions. V4 added explicit classification of partial-year
multiquarter aggregations and a synthetic omission example. V5 added source
currency, parenthetical ADR and ordinal-quarter versus quarter-count checks.
The v4 repeats had identical prompt/config, source revision and implementation
hashes but different answers. V5 did not demonstrate an improvement; these runs
do not prove that the wording alone caused the observed regression.

## Input representation outcomes with v4 fixed

The following runs share the exact v4 prompt hash, inference settings, target
revision, schema, pricing and original images. The HTML experiments change only
the input mode and extractor name in their configs. Their implementation hashes
also record the input-mode code introduced after the text baseline.

| Input | Run ID | F1 | Exact filings | Extraction errors |
| --- | --- | --- | --- | --- |
| Plain text A | `20261022T200445Z-86cc5fd2` | 97.6% | 12/13 | 0 |
| Plain text B | `20261022T200807Z-087b9cd4` | 90.0% | 10/13 | 0 |
| Raw HTML | `20261022T204355Z-7411a967` | 65.0% | 4/13 | 2 |
| Cleaned HTML | `20261022T220153Z-ac6f92af` | 78.0% | 8/13 | 2 |

| Input | Reported input tokens | Reported output tokens | Measured runtime | Known estimated cost |
| --- | --- | --- | --- | --- |
| Plain text A | 397,473 | 1,358 | 48.52 s | $0.13490059 |
| Plain text B | 397,473 | 1,318 | 48.40 s | $0.13479059 |
| Raw HTML | 4,173,479* | 1,593* | 339.73 s | $1.38162882* |
| Cleaned HTML | 997,809 | 1,754 | 78.10 s | $0.33410047 |

*Raw HTML usage and cost are incomplete: 12/13 filings reported usage. The other
rows have usage-based cost estimates for all 13 filings. Costs shown are totals
for each 13-filing evaluation, not per filing, and are estimates from provider
usage and the pinned pricing table rather than confirmed AWS billing. Failed-request or retry
charges may be unknown. Runtime is the recorded sum of extractor durations,
including local input preparation; it is not pure model latency or total CLI
wall-clock time. Token counts include successful API responses whose extraction
payload subsequently failed validation.

Cleaned HTML reduced the reported input-token count relative to raw HTML and
improved its observed accuracy, but still used about 2.5 times the plain-text
input tokens/cost and scored lower. Pre-inference character counts were
1,375,708 plain text, 17,616,432 raw HTML and 3,383,705 cleaned HTML, including
context/attachment labels. Character reduction alone did not predict accuracy.

## Remaining failures

- **V4 plain text:** DPZ's cumulative $12.80 amount was emitted as annual EPS in
  both runs. Repeat B additionally labeled ASML's EUR 12.93 as USD and omitted
  TSMC's explicitly reported USD 4.60 per ADR amount.
- **Raw HTML:** ASML currency and TSMC omission persisted. Additional failures
  included reported/cumulative amounts classified as adjusted EPS, CMC annual
  EPS classified as Q4, and conflicting GM duplicates. JPM had a provider
  `ValidationException`; the adapter did not retain its detailed message, so a
  context-limit cause is unconfirmed.
- **Cleaned HTML:** ASML currency persisted. DPZ assigned quarterly 4.60 and
  cumulative 12.80 to the same fiscal identity, invalidating that filing. GM
  encoded nine-month values as `fiscal_quarter: 9`, also invalidating the filing.
  GS/RTX produced cumulative or reported amounts as adjusted EPS. JPM, TSMC and
  CMC matched their targets in this run.

Keep strict validation and scoring. Invalid payloads fail the whole filing, with
all its targets counted as missing; extra-observation counts do not enumerate
unknown predictions from rejected payloads. Correct values may therefore be
present in a raw response even when the filing scores as failed. Read scores,
extraction errors and native/normalized responses together.

## Reproduction and comparison

These are paid inference commands; each creates a new output directory:

```bash
.venv/bin/finbot-eval-eps run --config configs/bedrock-nova-2-lite-prompt-v4.json
.venv/bin/finbot-eval-eps run --config configs/bedrock-nova-2-lite-prompt-v4-raw-html.json
.venv/bin/finbot-eval-eps run --config configs/bedrock-nova-2-lite-prompt-v4-cleaned-html.json
```

Read-only comparison of the saved experiments:

```bash
.venv/bin/finbot-eval-eps compare \
  "$FINBOT_DATA_ROOT/filing-evals/runs/20261022T200807Z-087b9cd4" \
  "$FINBOT_DATA_ROOT/filing-evals/runs/20261022T204355Z-7411a967"
.venv/bin/finbot-eval-eps compare \
  "$FINBOT_DATA_ROOT/filing-evals/runs/20261022T200807Z-087b9cd4" \
  "$FINBOT_DATA_ROOT/filing-evals/runs/20261022T220153Z-ac6f92af"
```

Comparisons require the same frozen target revision, filing membership, label
contract and scoring policy. Changing reviewed data creates a new revision.
Align prompt and model settings explicitly when isolating input representation.
Saved-prediction rescoring makes no model calls and cannot measure new accuracy,
cost or latency effects from a changed prompt or preprocessing mode.

## Interpretation and next work

This is a small, repeatedly tuned sample, not held-out validation. There are two
v4 text runs and only one run for each HTML mode; output variation prevents
precise attribution of every per-filing change. Preserve both v4 repeats rather
than reporting only the best run. The evidence supports plain text plus v4 as
the current baseline, not a general conclusion that HTML is always worse.

Pause further prompt/input-format tuning on these 13 filings. Use the fixed
baseline for repeated measurements and additional human-reviewed coverage before
making broader accuracy claims. The existing alternatives remain available for
future controlled comparisons. A Streamlit evaluation screen is still deferred;
the current interface is the CLI and saved reports.
