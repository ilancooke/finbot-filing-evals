# EPS extraction experiment report — updated 2026-10-23

## Findings

In the original 13-filing study, Luna 6 through the direct OpenAI API matched all
20 EPS targets on three v4 runs, with identical predictions. Its first measured
run cost an estimated **$0.05445**; two repeats with almost entirely cached inputs
cost **$0.00525–$0.00529** each. The three runs took 48.50–54.71 seconds of
recorded extractor time. A later, prompt-tuned 50-filing run matched all 83
targets with v6; that sample is not held out and does not establish performance
on unseen filings. See the follow-up results below.

Claude Haiku 5.5, Claude Sonnet 4.6 and Kimi K3 also matched every target in one
successful run each. Haiku cost $0.12563 and took 40.59 seconds. Sonnet was the
fastest perfect run at 38.44 seconds, with a post-hoc cost estimate of $1.70724.
Kimi cost $1.52113 and took 94.26 seconds. These observations favor Luna on cost;
they do not establish accuracy on new filings.

Earlier Nova experiments established **prompt v4, plain-text HTML plus original
images** as the reference input configuration. Nova scored 97.6% and 90.0% F1 on
two otherwise identical v4 runs. Further prompt changes and raw or cleaned HTML
did not improve the observed result. Retain Nova as a historical comparator and
use the fixed v4 prompt for broader model testing. No config or prompt was changed
to prepare this report.

## Scope and measurement

The original study below covers **18 saved full-bundle runs** conducted on
2026-10-22: 16 with the fiscal v2 contract and two earlier legacy runs. The
50-filing follow-up was conducted on 2026-10-23 and is reported separately.
Small synthetic smoke tests and single-request debugging probes are excluded.

The 16 fiscal runs share:

- 13 human-reviewed filing packages: ASML, BAC, DAL, DPZ, GS, JNJ, JPM, MS, UNH,
  TSM, CMC, RTX and GM; 27 HTML documents and 50 original supporting images.
- 20 quarterly/annual targets: 14 reported and six adjusted diluted EPS
  observations. The projection excludes 14 cumulative/YTD observations from the
  34 reviewed source observations.
- Frozen target revision
  `fa4cdfb8c8f81f0d2e55c4ad135eed414b1afad35fc15d4975bb92e1a58094c9`,
  label contract `earnings_eps.fiscal.v2`, and scoring policy `eps_fiscal_exact.v2`.
- Exact matching on metric, currency, period type, fiscal year, fiscal quarter
  and Decimal EPS value. An incorrect identity counts as missing plus extra.
  Invalid output fails the whole filing; all its targets become missing.

F1 is calculated across observations. An exact filing contains every expected
observation and no incorrect or extra observations. Failed requests remain in
the score denominator. An extraction error can be a provider rejection, invalid
JSON or schema failure; it does not necessarily mean the model could not read EPS.
Reviewed target values and review notes are not supplied in model requests.

Runtime is the **sum of recorded extractor durations**, including input preparation
and request handling. It is neither pure server latency nor complete CLI wall time.
Calls were sequential. Dollar amounts are **USD estimates per 13-filing run**,
based on reported usage and token rates, not reconciled provider invoices.

The saved manifests, results, reports, responses and integrity inventories are
the evidence. All 18 inventories were verified read-only for this report. No
inference, golden-data edits or catalog writes were made during report preparation.

## Model comparison: fixed v4 prompt and plain-text input

All rows include the original images. IDs refer to the run inventory below.
Errors include both provider and output-validation failures.

| ID | Model / API | F1 | Exact filings | Errors | Runtime | Estimated run cost | Cost evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| N4A | Nova 2 Lite / Bedrock | 97.6% | 12/13 | 0 | 48.52 s | $0.13490059 | Saved, complete |
| N4B | Nova 2 Lite / Bedrock, repeat | 90.0% | 10/13 | 0 | 48.40 s | $0.13479059 | Saved, complete |
| S1 | Claude Sonnet 4.6 / Bedrock | 100.0% | 13/13 | 0 | 38.44 s | $1.70723520 | Post-hoc, 13/13 usage |
| K1 | Kimi K3 / Bedrock | 100.0% | 13/13 | 0 | 94.26 s | $1.52113236 | Saved, complete |
| M1 | Mistral Large 3 / Bedrock | 0.0% | 0/13 | 13 | 58.38 s | $0.19237750* | Post-hoc, 10/13 usage |
| Q1 | Qwen3 VL 235B / Bedrock | 78.8% | 9/13 | 3 | 56.51 s | $0.21487137* | Post-hoc, 11/13 usage |
| L1 | Luna 6 / OpenAI, first run | 100.0% | 13/13 | 0 | 51.45 s | $0.054453210 | Saved, complete |
| L2 | Luna 6 / OpenAI, cached repeat | 100.0% | 13/13 | 0 | 48.50 s | $0.00525418 | Saved, complete |
| L3 | Luna 6 / OpenAI, cached repeat | 100.0% | 13/13 | 0 | 54.71 s | $0.00529318 | Saved, complete |
| H1 | Claude Haiku 5.5 / Anthropic, fixed adapter | 100.0% | 13/13 | 0 | 40.59 s | $0.12563460 | Saved, complete |

\* Partial cost of responses with known usage, not the complete job cost.
Sonnet, Mistral and Qwen configs omitted pricing, so their immutable saved reports
show cost as unknown. Their estimates above were calculated after the runs; those
reports/configs were not rewritten. A saved known-cost subtotal of zero with
`cost_complete: false` does not mean a run was free.

Comparisons measure the **complete extractor configuration**. Nova and Sonnet use
forced `submit_eps` tool output; Kimi, Mistral and Qwen use strict JSON text output.
Direct Luna and Haiku use native structured outputs and deterministic transport
schemas, followed by the same full local validation. Both direct configs use
medium reasoning/effort; Kimi retains provider-default reasoning. All use a
4096-token maximum output budget. Tokenizers, image handling, schema transport and
provider defaults differ. Bedrock uses US profiles or regional IDs; direct APIs
use global processing. The source documents and v4 prompt remain aligned.

## 50-filing Luna follow-up — 2026-10-23

The same frozen revision of the 50 human-reviewed filings was used for both runs.
It contains 83 fiscal EPS targets after cumulative/YTD exclusions. V4 produced 80
correct targets, two incorrect values and one missing target (F1 97.0%; 47/50
exact). The IBM and AT&T reported EPS predictions used continuing-operations
values, while the reviewed labels use total diluted EPS. HON did not reach the
provider: local input preparation incorrectly applied Bedrock's 20-image cap to
OpenAI. Its known run cost of $0.15229 is incomplete because HON had no provider
usage.

| ID | Model / prompt | Correct / incorrect / missing / extra | F1 | Exact filings | Runtime | Estimated run cost |
| --- | --- | --- | --- | --- | --- | --- |
| L4 | Luna 6 / OpenAI, v4 | 80 / 2 / 1 / 0 | 97.0% | 47/50 | 144.81 s | $0.15228919*, incomplete |
| L5 | Luna 6 / OpenAI, v6 | 83 / 0 / 0 / 0 | 100.0% | 50/50 | 164.13 s | $0.15943719, complete |

The v6 prompt clarifies that when continuing-operations and total diluted EPS
are both shown, reported EPS is the issuer's total. The OpenAI image-limit fix
also allowed HON's 34-image filing to be processed; HON's reported EPS was
correct. Of the 49 predictions returned in L4, 47 were unchanged in L5; IBM and
AT&T changed to the reviewed totals. Because prompt and provider-specific input
handling changed between these single runs, the overall improvement cannot be
attributed to the prompt alone. The 50-filing sample was used during prompt
development, so these results are not held-out accuracy.

Full reports and request artifacts are under
`$FINBOT_DATA_ROOT/filing-evals/runs/`:
`20261023T135326Z-0126d7df` (L4) and `20261023T145725Z-9ff8c84b` (L5).

## Token usage and caching

**Total prompt** means ordinary input + cache-read input + cache-write input.
These normalized categories are disjoint: OpenAI's native input count already
includes cache tokens, so adding it again would double-count them. Output includes
any billed reasoning tokens once. Token counts are model-specific.

| ID | Ordinary input | Cache read | Cache write | Total prompt | Output | Usage coverage |
| --- | --- | --- | --- | --- | --- | --- |
| N4A | 397,473 | 0 | 0 | 397,473 | 1,358 | 13/13 |
| N4B | 397,473 | 0 | 0 | 397,473 | 1,318 | 13/13 |
| S1 | 509,539 | 0 | 0 | 509,539 | 1,561 | 13/13 |
| K1 | 436,086 | 18,732 | 0 | 454,818 | 4,598 | 13/13 |
| M1 | 381,485 | 0 | 0 | 381,485 | 1,090 | 10/13, partial |
| Q1 | 400,183 | 0 | 0 | 400,183 | 1,043 | 11/13, partial |
| L1 | 39 | 20,256 | 427,522 | 447,817 | 1,613 | 13/13 |
| L2 | 39 | 447,778 | 0 | 447,817 | 1,545 | 13/13 |
| L3 | 39 | 447,778 | 0 | 447,817 | 1,623 | 13/13 |
| H1 | 664,452 | 0 | 0 | 664,452 | 2,594 | 13/13 |

Luna's repeats each reused 447,778 prompt tokens, explaining their much lower
cost. L1 was mostly cache writes, with some cache hits; it was not completely
uncached. Budget new documents using the first-run scale rather than the half-cent
repeat cost. The three measured Luna jobs cost $0.06500057 together and averaged
51.55 seconds. Their mixed-cache average cost is not a forecast for unseen filings;
caching did not demonstrate a consistent latency improvement in these measurements.

All three Luna runs returned identical predictions: 60 correct observations and
39 exact filing evaluations across repeats, still only **20 unique targets and
13 unique filings**. L1 preceded the Haiku speed/error-diagnostic fix in shared
adapter code. Its prompt/config match L2/L3; the two repeats also have identical
implementation hashes. This supports repeatability on the current sample.

Haiku's CMC request contained 144,341 input tokens and 78 output tokens. It alone
crossed Haiku's 100,000-token pricing threshold and cost $0.07236550, about 58% of
the job estimate. Equal headline base rates for Luna and Haiku therefore did not
produce equal job costs. No Haiku cache usage was reported or explicitly requested.

## Nova prompt and input experiments

All rows retain original images. Counts below mean correct / incorrect value /
missing / extra observations, against 20 expected targets.

| ID | Prompt / input | Correct / incorrect / missing / extra | F1 | Exact filings | Errors | Runtime | Estimated run cost |
| --- | --- | --- | --- | --- | --- | --- | --- |
| N2 | v2 / plain text | 17 / 1 / 2 / 18 | 60.7% | 5/13 | 0 | 51.72 s | $0.13350227 |
| N3 | v3 / plain text | 16 / 0 / 4 / 2 | 84.2% | 9/13 | 2 | 51.01 s | $0.13479664 |
| N4A | v4 / plain text | 20 / 0 / 0 / 1 | 97.6% | 12/13 | 0 | 48.52 s | $0.13490059 |
| N4B | v4 / plain text repeat | 18 / 0 / 2 / 2 | 90.0% | 10/13 | 0 | 48.40 s | $0.13479059 |
| N5 | v5 / plain text | 17 / 0 / 3 / 6 | 79.1% | 9/13 | 1 | 55.24 s | $0.13705593 |
| NR | v4 / raw HTML | 13 / 0 / 7 / 7 | 65.0% | 4/13 | 2 | 339.73 s | $1.38162882* |
| NC | v4 / cleaned HTML | 16 / 0 / 4 / 5 | 78.0% | 8/13 | 2 | 78.10 s | $0.33410047 |

\* Raw HTML has usage/cost for 12/13 filings. Other rows have complete usage-based
estimates. N4A/N4B repeat the same two runs from the model comparison.

| ID | Reported input tokens | Reported output tokens | Usage coverage |
| --- | --- | --- | --- |
| N2 | 388,269 | 1,954 | 13/13 |
| N3 | 393,508 | 1,796 | 13/13 |
| N4A | 397,473 | 1,358 | 13/13 |
| N4B | 397,473 | 1,318 | 13/13 |
| N5 | 400,671 | 1,758 | 13/13 |
| NR | 4,173,479 | 1,593 | 12/13, partial |
| NC | 997,809 | 1,754 | 13/13 |

No cache usage was reported in these Nova runs. V3 clarified current-period
columns, adjusted EPS and multiple currencies/ADRs. V4 explicitly excluded
partial-year multiquarter aggregations. V5 added currency, parenthetical ADR and
quarter-heading checks; its one run did not improve the outcome. The v4 repeats
had identical data, prompt, settings and implementation hashes but different
answers. Prompt wording alone cannot explain every observed score change.

Raw HTML was slower, more expensive and less accurate in its measured run.
Cleaning improved on raw HTML, but still used about 2.5 times the plain-text input
tokens/cost. The [earlier Nova experiment record](EVALUATION_EXPERIMENTS.md)
preserves preprocessing details and per-filing failures. The evidence supports
plain text for this workflow, without establishing that HTML is generally worse.

## Failures and integration fixes

- **Nova v4:** both runs emitted DPZ's cumulative $12.80 as annual EPS. Repeat B
  also used USD instead of EUR for ASML's 12.93 and omitted TSM's USD 4.60 ADR EPS.
- **Mistral:** ten responses wrapped JSON in Markdown fences, rejected by strict
  parsing. ASML, BAC and UNH returned provider `ValidationException`. Its 0% F1
  measures this failed integration/configuration; it does not establish that every
  raw numeric answer was wrong. Detailed provider causes were not retained.
- **Qwen:** BAC/UNH returned provider `ValidationException`; JNJ used invalid field
  names ending in `epsilon`; CMC returned empty arrays and missed annual EPS.
  Whole-run counts were 13 correct, zero incorrect, seven missing and zero extra.
- **Initial Haiku adapter (H0):** all 13 requests failed with HTTP 400 in 7.34 seconds,
  with no usage or complete cost. A diagnostic replay established that Haiku
  rejects the `speed` parameter, including `standard`. Omitting it fixed a TSM
  probe, then H1 matched the full bundle. H0 is an integration failure, not an
  accuracy benchmark or a free completed job.

Strict parsing and local validation were retained. There was no Markdown stripping,
model-based repair, dropping of attachments or relaxation of scoring. Known usage
remains counted when output later fails validation. Rejected payloads are not
scored observation by observation; zero extras does not establish that their raw
responses contained no extra observations.

## Cost method and sources

For each request, calculate:

```text
(ordinary input × input rate
 + cache reads × cache-read rate
 + cache writes × cache-write rate
 + output × output rate) / 1,000,000
```

Apply any long-context multiplier for that individual request, then sum job costs.
Thresholds use each request's total prompt tokens, not the sum across filings.
Missing usage or pricing stays unknown. Retries/failed calls may have charges
not represented in successful response usage. Taxes, credits, contract discounts
and unrecorded debugging spend are excluded.

Rates were checked for these experiments as of 2026-10-22. Values below are USD
per million tokens for the configured route/tier.

| Model / route | Input | Output | Cache read | Cache write | Basis |
| --- | --- | --- | --- | --- | --- |
| Nova 2 Lite / Bedrock US | $0.33 | $2.75 | $0.0825 | $0 | Frozen config; Price List `20261016210806` |
| Kimi K3 / Bedrock US | $3.30 | $16.50 | $0.33 | $4.125 | Frozen config; 30-minute write |
| Sonnet 4.6 / Bedrock US | $3.30 | $16.50 | Not needed | Not needed | Post-hoc; no cache tokens reported |
| Mistral Large 3 / Bedrock US East | $0.50 | $1.50 | Not established | Not established | Post-hoc; known responses only |
| Qwen3 VL 235B / Bedrock US East | $0.53 | $2.66 | Not established | Not established | Post-hoc; known responses only |
| Luna 6 / OpenAI global Standard | $0.10 | $0.50 | $0.01 | $0.125 | Frozen config; 30-minute write |
| Haiku 5.5 / Anthropic global Standard | $0.10 | $0.50 | $0.01 | $0.125 | Frozen config; base tier, 5-minute write |

The [AWS Bedrock pricing page](https://aws.amazon.com/bedrock/pricing/) supports
the Kimi, Mistral and Qwen schedules. Nova's pinned catalog, effective 2026-10-01,
and pricing SKUs are recorded in the [README](../README.md).
Sonnet's estimate uses $3/$15 base rates plus the 10% geographic endpoint premium
documented in [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing).
This is a derived estimate, not a rate newly pinned in its saved config.

[Luna pricing](https://developers.openai.com/api/docs/models/gpt-6-luna) applies
2× input/cache and 1.5× output above 272,000 prompt tokens; none of these Luna
requests crossed that threshold. [Haiku pricing](https://platform.claude.com/docs/en/models/haiku-5-5/overview)
applies 5× all base token rates above 100,000 prompt tokens for the whole request;
CMC triggered it. Nova/Kimi configs use no long-context surcharge here.

For example, the post-hoc Sonnet calculation is
`(509539 × 3.30 + 1561 × 16.50) / 1000000 = $1.70723520`.
Mistral/Qwen estimates cover only responses with known usage and zero reported
cache tokens. Unknown cache schedules have not been assumed free.

## Earlier legacy-contract experiments

These runs used 34 date/free-text-based targets under `earnings_eps.v1` and
`eps_exact.v1`; their scores cannot be combined with fiscal v2 scores.

| ID | Experiment | F1 | Exact filings | Errors | Runtime | Estimated cost |
| --- | --- | --- | --- | --- | --- | --- |
| B0 | Luna through Bedrock, access attempt | 0.0% | 0/13 | 13 | 7.68 s | Unknown; no usage |
| N1 | Nova 2 Lite, legacy contract | 0.0% | 0/13 | 1 | 50.12 s | $0.13241591 |

B0 encountered account-level model access restrictions. N1 reported 383,927 input
and 2,080 output tokens. Strict period/date identity mismatches contributed to
zero matched observations, alongside extraction/period-selection errors. Fiscal
v2 changed the target definition, so the score jump is not a model improvement
under an unchanged benchmark. Small synthetic Nova format probes and Haiku
diagnostic probes were integration checks, excluded from these full-run tables.

## Run inventory and reproduction

Artifacts live at `$FINBOT_DATA_ROOT/filing-evals/runs/<run_id>/`. IDs below are
report shorthand, not renamed directories. Snapshots preserve exact configs,
prompts, source membership and implementation hashes.

| ID | Run ID | Configuration / purpose |
| --- | --- | --- |
| B0 | `20261022T170052Z-c662becc` | Legacy Luna / Bedrock access attempt |
| N1 | `20261022T175523Z-9d0397c7` | Legacy Nova baseline |
| N2 | `20261022T182538Z-553cc644` | Nova v2 / plain text |
| N3 | `20261022T193052Z-e7a6a26a` | Nova v3 / plain text |
| N4A | `20261022T200445Z-86cc5fd2` | Nova v4 / plain text |
| N4B | `20261022T200807Z-087b9cd4` | Nova v4 / plain text repeat |
| N5 | `20261022T202959Z-f8208a78` | Nova v5 / plain text |
| NR | `20261022T204355Z-7411a967` | Nova v4 / raw HTML |
| NC | `20261022T220153Z-ac6f92af` | Nova v4 / cleaned HTML |
| S1 | `20261022T222842Z-974f0311` | Sonnet 4.6 v4 / Bedrock |
| K1 | `20261022T223005Z-f56042e6` | Kimi K3 v4 / Bedrock |
| M1 | `20261022T223518Z-a437e1f0` | Mistral Large 3 v4 / Bedrock |
| Q1 | `20261022T224753Z-6ce966ab` | Qwen3 VL 235B v4 / Bedrock |
| L1 | `20261022T232136Z-eea4d640` | Luna 6 v4 / OpenAI, first run |
| H0 | `20261022T232238Z-2ae9a23b` | Haiku 5.5 v4 / Anthropic, unsupported speed |
| H1 | `20261022T232904Z-c1870c56` | Haiku 5.5 v4 / Anthropic, fixed adapter |
| L2 | `20261022T233524Z-ef3fe165` | Luna 6 v4 / OpenAI, cached repeat |
| L3 | `20261022T233620Z-c8266d77` | Luna 6 v4 / OpenAI, cached repeat |
| L4 | `20261023T135326Z-0126d7df` | Luna 6 v4 / OpenAI, 50-filing run; incomplete after local HON image-limit failure |
| L5 | `20261023T145725Z-9ff8c84b` | Luna 6 v6 / OpenAI, 50-filing follow-up |

Read-only comparison from the package root:

```bash
export FINBOT_DATA_ROOT=/absolute/path/to/finbot/data
.venv/bin/finbot-eval-eps compare \
  "$FINBOT_DATA_ROOT/filing-evals/runs/20261022T200445Z-86cc5fd2" \
  "$FINBOT_DATA_ROOT/filing-evals/runs/20261022T233620Z-c8266d77"
```

New **paid** runs, after installing optional SDKs and exporting credentials:

```bash
.venv/bin/finbot-eval-eps run --config configs/openai-luna-6-prompt-v4.json
.venv/bin/finbot-eval-eps run --config configs/anthropic-haiku-5-5-prompt-v4.json
.venv/bin/finbot-eval-eps run --config configs/bedrock-nova-2-lite-prompt-v4.json
```

The [README](../README.md#direct-openai-and-anthropic-apis) documents setup and all
candidate configs. Comparisons require the same revision, membership, contract
and scoring policy. Saved-prediction rescoring cannot measure a new model or
prompt's accuracy, latency or cost.

## Recommended next experiments

Freeze v6 and evaluate it on a separate, newly reviewed set that was not used for
prompt development. Keep prompt changes and provider/input-handling changes
separate in future comparisons. Retain v4 as the historical baseline, use Haiku
as a second direct-provider comparator and Nova as the historical reference, and
measure fresh-document costs separately from cache-hit repeats.

Both the original 13-filing sample and the 50-filing follow-up were used for
prompt development and model selection; there is no held-out validation. Most
alternatives have only one successful run.
Provider/adapter differences and limited repeats prevent a general claim that
one underlying model is best. Luna's three perfect runs justify further testing;
expanding reviewed coverage is now more informative than repeating these same
50 filings.
