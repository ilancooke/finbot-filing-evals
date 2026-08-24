# Visual Financial-Statement Golden Dataset Roadmap

## Scope and guiding contract

This roadmap builds a benchmark for faithfully reconstructing tables as they
appear in screenshots of SEC financial statements. The visual benchmark records
what a statement says, not what downstream accounting logic thinks it means.

The source convention is:

```text
$FINBOT_DATA_ROOT/raw/financial_statement_screenshots_golden_dataset/
└── {TICKER}/
    ├── 10k balance sheet.png
    ├── 10k income statement.png
    ├── 10k cash flows.png
    ├── 10q balance sheet.png
    ├── 10q income statement.png
    └── 10q cash flows.png
```

Ticker, filing type, and statement type are path-derived facts. No model may be
asked to infer them. A model transcribes statement-level raw text, an ordered
row manifest, an ordered value-column manifest, and visible table cells. Rows
include meaningful standalone no-value section headings. Hierarchies use
arbitrary-depth `row_path_raw` and `column_path_raw` arrays; raw fields are never
overwritten by comparison or accounting normalization.

The implemented package root is
`src/finbot_filing_evals/golden_dataset/`. Generated data lives outside the
repository under the configured finbot data root:

```text
$FINBOT_DATA_ROOT/
├── raw/financial_statement_screenshots_golden_dataset/
├── intermediate/
│   ├── golden_dataset_annotations/{provider}/
│   └── golden_dataset_consensus/
└── processed/financial_statement_visual_gold/
```

Raw source images and generated provider responses are immutable inputs. New
runs use new versioned/run directories rather than overwriting prior results.
API-backed tests remain opt-in and never run as part of the normal unit suite.

## Milestone 0 — Project scaffold and contracts

### Purpose

Establish package boundaries, shared types, deterministic source discovery,
configuration, and the provider contract without external API calls.

### Inputs

- Repository packaging and testing conventions.
- The screenshot directory hierarchy and filename convention.
- `FINBOT_DATA_ROOT` or explicit path overrides.
- Image bytes used to create stable SHA-256 identities.

### Outputs

- `finbot_filing_evals.golden_dataset` package scaffold.
- Typed statement, cell, extraction request, and result-envelope models.
- Deterministically ordered screenshot records with path-derived metadata.
- Shared filesystem configuration and provider protocol.
- Unit tests and an environment-dependent 90-image corpus acceptance test.

### Implementation tasks

- [x] Inspect repository architecture and available Python/test environment.
- [x] Create a `src/` package scaffold for discovery, extraction, prompts,
  consensus, export, and validation.
- [x] Define statement metadata, including raw title/units extension points.
- [x] Define one-record-per-visible-value-cell annotations.
- [x] Represent row and column hierarchy with arbitrary-depth sequences.
- [x] Define provider-neutral extraction request and auditable result envelope.
- [x] Capture provider/model, prompt/schema version, timestamp, raw response,
  parsed response, usage, status/error, and retry metadata in the contracts.
- [x] Define filing type, statement type, provider, and status enums.
- [x] Discover screenshots deterministically from direct ticker children.
- [x] Validate uppercase ticker directories and exact expected filenames.
- [x] Derive ticker, filing type, statement type, and statement ID from paths.
- [x] Compute streaming SHA-256 hashes and content-based source image IDs.
- [x] Define a runtime-checkable common provider protocol.
- [x] Define prompt naming (`<task>_v<N>.txt`) and serialized schema naming
  (`<contract>.v<N>`) conventions.
- [x] Document environment variables, output roots, setup, and test commands.
- [x] Add unit tests for discovery, derivation, hashing, models, and config.
- [x] Add a conditional acceptance test for the complete source corpus.

### Important design decisions

- Standard-library frozen dataclasses and enums define shared benchmark
  records. Milestone 1 uses a checked-in JSON Schema plus `jsonschema` for the
  separate provider-facing wire contract.
- `statement_id` is `{TICKER}_{10K|10Q}_{statement_type}` for the current corpus,
  which has exactly one image for each combination.
- `source_image_id` is `sha256:<lowercase digest>` and the digest is retained
  separately for manifest use.
- Discovery ignores hidden files such as `.DS_Store`, but rejects any visible
  unexpected file, nested directory, invalid ticker, or misnamed screenshot.
- Completeness and expected-count checks are explicit options. This permits
  valid pilot subsets while allowing the full corpus to require six images per
  ticker and 90 total.
- Configuration resolves paths without creating directories. Artifact writers
  introduced later must implement explicit no-overwrite behavior.
- Provider-specific SDK objects may be retained in memory as raw responses, but
  adapters must serialize losslessly/auditably before artifact persistence.
- `visual_metadata` is an extension point for optional presentation features;
  the core contract does not prematurely prescribe indentation or styling.

### Tests and acceptance criteria

- [x] Synthetic fixtures are returned in the same identity order regardless of
  creation order.
- [x] Metadata derivation uses only directory and filename components.
- [x] Misnamed PNGs and incomplete sets fail with actionable errors when the
  relevant validation is enabled.
- [x] Raw parentheses and arbitrary-depth row/column paths remain unchanged.
- [x] Successful envelopes require both raw and parsed responses; failures
  retain structured error details.
- [x] When the source corpus is present, exactly 90 unique statement IDs across
  15 tickers are discovered twice with identical records and hashes.
- [x] Normal tests make no network requests.

### Explicitly out of scope

- Provider SDKs or API calls.
- The frozen model-facing extraction JSON schema and prompt text.
- Writing annotation artifacts, retry orchestration, or a CLI runner.
- Comparison normalization, alignment, consensus, review, or gold export.
- Accounting normalization and financial calculations.

### Dependencies

- None. This is the foundation for every later milestone.

## Milestone 1 — Extraction schema and prompt

### Purpose

Freeze V1 of the provider-neutral, pure visual/table extraction contract before
integrating any external model.

### Inputs

- Milestone 0 models and version conventions.
- Representative screenshots covering multi-level rows/columns and visual
  edge cases.
- Hand-authored valid and malformed response fixtures.

### Outputs

- Immutable `prompts/visual_table_extraction_v1.txt`.
- A machine-enforceable V1 structured response schema.
- Conversion from validated response documents into shared raw models.
- Written transcription rules and fixture corpus.

### Implementation tasks

- [x] Choose a lightweight validation mechanism (checked-in JSON Schema plus
  `jsonschema`) and document the dependency decision.
- [x] Define a complete structured response schema with raw statement text,
  ordered row/column manifests, and indexed cell records.
- [x] Support arbitrary-depth `row_path_raw` and `column_path_raw` arrays.
- [x] Preserve `value_raw`, including whitespace when meaningful, parentheses,
  currency marks, dashes, footnote marks, and empty displayed values.
- [x] Preserve `statement_title_raw` and `units_raw` exactly as visible.
- [x] Specify treatment of section headings, blank values, spanning headers,
  repeated labels, footnotes, indentation, subtotal/total rows, and decorative
  content.
- [x] Decide whether deliberately represented blank cells are cell records and
  encode that choice unambiguously.
- [x] Write `visual_table_extraction_v1` with explicit prohibitions on concept
  mapping, arithmetic, period inference, units conversion, and row combining.
- [x] Include examples for Apple's multi-index period columns, `Net sales →
  Products`, `(171)`, and statement-level units.
- [x] Ensure examples do not accidentally teach accounting normalization.
- [x] Add a schema-version migration policy: never mutate V1 after use; create
  V2 and preserve readers for old stored artifacts.

### Important design decisions

- The logical schema must be identical across provider families even if their
  native structured-output features differ.
- Indices are contiguous and zero-based. Row indices include all meaningful
  data and section-heading rows; column indices include value columns only.
- The wire response normalizes paths into row and column manifests. Wire cells
  contain only `row_index`, `column_index`, and `value_raw`; conversion hydrates
  the required self-contained cell records deterministically.
- Every meaningful row is recorded as `data` or `section_heading`. Totals and
  subtotals remain data rows rather than semantic classifications.
- A clearly present blank intersection is a cell with `value_raw: ""`; `null`
  is reserved for a visibly absent statement title or units string.
- Unknown response fields are rejected at every object level.
- Presentation flags beyond hierarchy are deferred to a future schema version.
- Raw transcription fields must never contain comparison-normalized values.
- Prompt and schema versions are independently recorded because either may
  change without the other.

### Tests and acceptance criteria

- [x] Valid fixtures deserialize into typed statement, row, column, and cell
  annotations.
- [x] Malformed fixtures fail clearly for empty paths, wrong types, invalid
  indices, missing/extra fields, invalid references, and structural conflicts.
- [x] Deterministic statement IDs and source metadata are injected during
  conversion and are not echoed or inferred by the model.
- [x] Round trips preserve every `_raw` string byte-for-byte at the JSON string
  level.
- [x] Deep (more than two-level) row and column paths validate successfully.
- [x] The packaged prompt and schema are loadable by version and their
  checksums are testable.
- [x] No external provider integration is required or invoked.

### Explicitly out of scope

- Calling OpenAI, Anthropic, or Qwen.
- Comparison normalization or deciding whether two raw strings agree.
- Canonical accounting concepts, numeric parsing, unit scaling, or derived
  periods and values.

### Dependencies

- Milestone 0 contracts, discovery, configuration, and version policy.

## Milestone 2 — OpenAI extraction adapter and pilot runner

### Purpose

Implement the first production-quality vision extraction backend and exercise
the frozen contract on a small representative pilot.

### Inputs

- Milestone 1 prompt and response schema.
- Discovered source records and immutable images.
- `OPENAI_API_KEY` supplied at runtime.
- Explicit provider/model and run configuration.

### Outputs

- OpenAI adapter implementing `ExtractionProvider`.
- Versioned, immutable raw and parsed annotation artifacts.
- A CLI runner for controlled subsets and resumable runs.
- Pilot annotations and run manifest, not consensus or gold data.

### Implementation tasks

- [ ] Add the OpenAI SDK as an optional/provider-specific dependency.
- [ ] Send one screenshot per independent request with dense-document,
  high-detail image settings.
- [ ] Use native structured output/schema enforcement when supported.
- [ ] Record the exact requested model and returned model version when exposed.
- [ ] Implement bounded timeouts, classified retries, exponential backoff, and
  rate-limit handling without changing request semantics.
- [ ] Log identifiers and outcomes without leaking credentials or full private
  payloads into console logs.
- [ ] Persist the raw provider response before/alongside parsing; never discard
  it after successful parsing.
- [ ] Persist the parsed common annotation separately from the raw response.
- [ ] Capture usage/token/cost-relevant metadata when returned.
- [ ] Write atomically into a run-scoped immutable artifact directory and
  refuse accidental overwrite.
- [ ] Add runner selectors for one file, one ticker, limited sample, and all
  files.
- [ ] Add dry-run output showing selected inputs, versions, and destination with
  no API request or directory mutation.
- [ ] Add resume/skip-successful behavior based on validated existing envelopes.
- [ ] Pilot on a small set spanning filing types, statement types, dense
  columns, nested rows, parentheses, footnotes, and blank cells.

### Important design decisions

- Extraction and consensus stay in separate modules and artifact trees.
- Retry attempts target the same source, prompt, schema, and model; retry count
  is part of the envelope.
- A success marker is written only after raw persistence and parsed validation
  both complete.
- Model responses are independent requests and receive no previous annotation.
- Cost controls and an explicit `--all` selection guard should prevent an
  accidental 90-image run during development.

### Tests and acceptance criteria

- [ ] Unit tests mock transport behavior for success, invalid structured output,
  timeouts, rate limits, retries, and usage capture.
- [ ] Dry-run and selector tests prove the exact intended file set.
- [ ] Resume skips only fully validated successful artifacts and retries failed
  or incomplete artifacts explicitly.
- [ ] Raw and parsed records link to identical source, prompt, schema, provider,
  and request metadata.
- [ ] A manually triggered pilot produces auditable stored annotations for the
  selected images.
- [ ] Normal unit tests require neither network nor API key.

### Explicitly out of scope

- Anthropic and Qwen adapters.
- Passing annotations between providers.
- Cell alignment, consensus, adjudication, or gold publication.
- Full-corpus execution until pilot quality and cost are reviewed.

### Dependencies

- Milestones 0 and 1.

## Milestone 3 — Additional independent provider adapters

### Purpose

Generate genuinely independent annotations from Anthropic Claude and Qwen
using the same logical extraction task.

### Inputs

- Frozen Milestone 1 contract and prompt semantics.
- Milestone 2 artifact/run conventions and source selection behavior.
- Runtime `ANTHROPIC_API_KEY` and `QWEN_API_KEY` (plus endpoint configuration if
  Qwen deployment requires it).

### Outputs

- Anthropic and Qwen adapters implementing the common provider contract.
- Provider-native raw responses and common parsed annotations.
- Comparable run manifests for the same image set across all providers.

### Implementation tasks

- [ ] Add each SDK/client only in its provider-specific optional dependency.
- [ ] Implement Claude adapter with provider-native error and usage capture.
- [ ] Implement Qwen adapter with provider-native error and usage capture.
- [ ] Map both responses into the exact common extraction schema.
- [ ] Keep task instructions logically equivalent while documenting unavoidable
  API/structured-output/image-transport differences.
- [ ] Reuse selectors, dry-run, retry, atomic persistence, and resume semantics.
- [ ] Guarantee one independent request per provider per source image.
- [ ] Prohibit provider annotations from appearing in another provider's input.
- [ ] Support an explicit multi-provider run over the same frozen manifest.

### Important design decisions

- Provider-native response envelopes remain separate, while every extracted
  structured body validates against the same frozen wire schema and converts to
  the same parsed annotation models.
- Model family names are not sufficient provenance: exact identifiers, returned
  versions, endpoints where relevant, and timestamps are retained.
- Independence is enforced in the runner/input construction, not merely stated
  in the prompt.
- Provider-specific failures do not block successful annotations from other
  providers and remain retryable/auditable.

### Tests and acceptance criteria

- [ ] Mocked contract tests run identically against every adapter.
- [ ] Provider-specific raw fixtures map to the common schema without losing
  their original responses.
- [ ] The same test image can independently produce stored annotations from
  OpenAI, Anthropic, and Qwen in an opt-in integration run.
- [ ] Request capture proves no provider receives another provider's answer.
- [ ] Normal tests remain network-free and credentials remain uncommitted.

### Explicitly out of scope

- Cross-provider adjudication or LLM-as-judge behavior.
- Comparison normalization, alignment, and consensus.
- Accounting or financial normalization.

### Dependencies

- Milestones 0–2.

## Milestone 4 — Deterministic annotation comparison

### Purpose

Conservatively align multiple provider annotations at cell level without using
an LLM to decide equivalence.

### Inputs

- Successful parsed annotations for the same source image from multiple
  providers.
- Every provider's untouched raw fields and structural indices.
- A versioned comparison-normalization policy.

### Outputs

- Deterministic normalized comparison keys stored separately from raw values.
- Ordered row- and column-manifest alignments, including standalone section
  headings, row kinds, missing/extra structure, and hierarchy disagreements.
- Cell alignments with matched, missing, extra, hierarchy-disagreement, and
  value-disagreement evidence.
- Document-level structural statistics and explainable diagnostics.

### Implementation tasks

- [ ] Define and version conservative comparison normalization.
- [ ] Trim inconsequential leading/trailing whitespace and normalize repeated
  whitespace only where explicitly justified.
- [ ] Specify conservative punctuation and currency-symbol handling with tests.
- [ ] Normalize row path, column path, and value independently for comparison.
- [ ] Never modify `row_path_raw`, `column_path_raw`, or `value_raw`.
- [ ] Align ordered row and column manifests before aligning cells, preserving
  standalone no-value rows and comparing `data` versus `section_heading` kinds.
- [ ] Define deterministic cell identity/matching order using paths and indices.
- [ ] Detect missing and extra cells separately.
- [ ] Detect hierarchy and header-structure disagreements.
- [ ] Detect value disagreements among otherwise aligned cells.
- [ ] Produce per-document row/column counts and structural summaries.
- [ ] Define duplicate-label/cell behavior and surface ambiguity explicitly.
- [ ] Avoid fuzzy matching initially; if later introduced, make thresholds,
  ordering, and error behavior explicit and measurable.

### Important design decisions

- Comparison normalization is string equivalence for annotation comparison, not
  numeric parsing or accounting normalization.
- Row path, column path, and value agreement are separate dimensions.
- Structural row/column alignments are first-class outputs rather than
  synthetic blank cells.
- Alignment output retains pointers to every original provider annotation.
- Ambiguous alignment is a result to review, not an invitation for a hidden
  heuristic or semantic guess.

### Tests and acceptance criteria

- [ ] `"78,678"` and `" 78,678 "` compare equal under the documented rule while
  both raw values remain retrievable.
- [ ] Parentheses, signs, decimals, dashes, currency symbols, and footnotes have
  explicit conservative test cases.
- [ ] Fixtures detect missing/extra rows and columns, row-kind conflicts,
  structural/path disagreements, and missing/extra/value-conflicting cells.
- [ ] Reordering and duplicate labels behave deterministically.
- [ ] Repeated runs produce byte-identical alignment output.
- [ ] No LLM or network call participates in comparison.

### Explicitly out of scope

- Majority/unanimous classification policy.
- Human correction or final-gold selection.
- Semantic row mapping, numeric conversion, fuzzy accounting synonyms, and
  inferred dates/periods.

### Dependencies

- Milestones 0–3 and at least two provider annotations per compared image.

## Milestone 5 — Consensus classification

### Purpose

Convert deterministic alignments into candidate-gold records and focused
review queues without treating agreement as proof of truth.

### Inputs

- Milestone 4 alignments and disagreement evidence.
- Provider/run/source provenance for every annotation.
- A versioned classification policy.

### Outputs

- Agreement classifications for cell groups and structural records:
  `unanimous`, `majority`, `conflict`, `missing_conflict`, and
  `structure_conflict` at minimum, as applicable to the record type.
- Row- and column-structure consensus records, including standalone section
  headings, paths, kinds, ordering, and missing/extra structure.
- Candidate values and candidate row/column structures where policy permits,
  still linked to all raw annotations.
- Review queues and summary metrics by relevant dimensions.

### Implementation tasks

- [ ] Define exact classification precedence for overlapping disagreement types.
- [ ] Classify every aligned cell group deterministically.
- [ ] Classify aligned row and column structures independently from cell values,
  including row paths, row kinds, column paths, order, and presence.
- [ ] Retain links to all source provider annotations and their raw fields.
- [ ] Mark candidates as unreviewed rather than final gold.
- [ ] Generate metrics per provider, statement, ticker, filing type, and
  statement type.
- [ ] Include cells extracted, unanimous, majority, conflict, missing, extra,
  and structure-conflict counts/rates.
- [ ] Include row/column extracted, matched, missing, extra, and conflicting
  counts/rates, including standalone section headings.
- [ ] Capture document-level cell completeness and structural summaries.
- [ ] Version classification logic and record its version in output metadata.

### Important design decisions

- `unanimous` means provider agreement under a versioned comparison rule; it
  does not mean human-verified correctness.
- Majority requires a defined minimum provider count and an unambiguous winning
  raw/normalized representation.
- Structure conflicts are first-class row, column, or document results and take
  precedence where cell identity itself is uncertain; they are not forced into
  synthetic value-cell records.
- Metrics distinguish missing provider output from explicit blank table cells.

### Tests and acceptance criteria

- [ ] Fixtures cover every classification and precedence combination.
- [ ] Each cell and structural result can trace back to every contributing raw
  annotation.
- [ ] Cell totals and row/column structural totals reconcile independently.
- [ ] Provider/statement/ticker/form/type aggregations are deterministic.
- [ ] No unanimous or majority result is labeled final or verified by default.

### Explicitly out of scope

- Human adjudication and audit sampling.
- Changing provider annotations.
- Accounting normalization or feature calculation.

### Dependencies

- Milestone 4 and a documented minimum provider set.

## Milestone 6 — Human review workflow

### Purpose

Efficiently adjudicate disagreements and audit samples of apparently easy
agreements to detect correlated model errors.

### Inputs

- Consensus classifications and source-linked provider annotations.
- Immutable source screenshots.
- A recorded random seed and sampling policy.

### Outputs

- Review artifact(s) supporting source viewing and side-by-side cell, row, and
  column annotations.
- Human selections/corrections, reviewer notes, timestamps, and status.
- Deterministic samples of unanimous cells and unanimous documents.

### Implementation tasks

- [ ] Define review-record schema with stable review item IDs.
- [ ] Include source image path/ID, crop or location metadata when available,
  all provider raw annotations, and disagreement category.
- [ ] Support review items for value cells, row paths/kinds/presence, column
  paths/presence, and document-level structure conflicts.
- [ ] Allow selecting a provider transcription or entering a corrected value,
  path, row kind, or structural decision as appropriate to the review item.
- [ ] Record reviewer identity, notes, timestamp, and validation status.
- [ ] Support `unreviewed`, `verified`, `corrected`, and `rejected` statuses.
- [ ] Generate deterministic random samples of unanimous cells and documents
  using a stored seed, population hash, and sampling parameters.
- [ ] Preserve review history; corrections append revisions rather than
  overwriting original annotations.
- [ ] Start with CSV/JSON plus image links unless usability evidence justifies a
  richer tool.

### Important design decisions

- Agreement sampling is mandatory because models can make correlated errors.
- Review state is a separate layer from provider and consensus artifacts.
- A rejected item requires an explicit reason and does not silently disappear.
- If crops are generated, their coordinates and source hash become provenance.

### Tests and acceptance criteria

- [ ] A reviewer can locate the source screenshot and see every provider value
  or structural annotation for each disputed cell, row, or column.
- [ ] Review edits preserve old state and all provenance.
- [ ] The same seed and population produce the same audit sample.
- [ ] Sample sizes and strata are validated and reported.
- [ ] CSV/JSON exports round-trip without losing hierarchy or raw text.

### Explicitly out of scope

- A web UI unless separately requested.
- Automatic LLM adjudication.
- Accounting normalization or derived metrics.

### Dependencies

- Milestone 5; optional visual-location metadata may be added without changing
  core cell identity.

## Milestone 7 — Freeze visual golden dataset V1

### Purpose

Publish a reproducible, human-validated transcription benchmark with frozen
inputs, contracts, provenance, structural truth, and cell-level truth.

### Inputs

- Immutable source image corpus and hashes.
- Versioned prompts/schemas and provider annotations.
- Deterministic consensus results and completed human adjudications/audits.

### Outputs

- Immutable source-image manifest with hashes.
- Prompt/schema/comparison/classification versions.
- Provider/model/run metadata and raw annotations.
- Consensus and human-review artifacts.
- Final statement metadata, row-manifest, column-manifest, and self-contained
  cell-level visual gold tables.
- Bundle metadata and integrity hashes.

### Implementation tasks

- [ ] Define the V1 bundle manifest and exact file formats/schemas.
- [ ] Verify all 90 source hashes against the frozen source manifest.
- [ ] Require complete provenance for every included annotation and decision.
- [ ] Resolve or explicitly reject every required review item.
- [ ] Include results of unanimous cell/document audits.
- [ ] Export statement metadata, ordered rows, ordered columns, and
  self-contained cells without semantic accounting concepts.
- [ ] Hash primary and derived artifacts and record tool/package versions.
- [ ] Implement no-overwrite publication and full offline integrity verification.
- [ ] Document licensing/access constraints and reproducible rebuild steps.

### Important design decisions

- V1 is immutable. Corrections produce a new dataset version with change notes.
- The final tables retain the visually reported raw labels, headers, values,
  titles, units, standalone section headings, row kinds, and zero-based order.
- Final cells retain hydrated `row_path_raw` and `column_path_raw` even though
  the model-facing wire cells refer to row/column manifests by index.
- Provider raw responses may require a restricted artifact tier, but their
  hashes and provenance remain linked from the benchmark.
- Publication must not depend on mutable absolute paths alone; manifests use
  logical paths plus hashes while preserving original path provenance.

### Tests and acceptance criteria

- [ ] Offline verification confirms every declared file and hash.
- [ ] Every final row, column, and cell traces to source, provider annotations,
  consensus, and human decision/audit status.
- [ ] Statement/row/column/cell counts, zero-based order, references, row kinds,
  and hydrated path relationships pass schema checks.
- [ ] A clean environment can load and validate the frozen benchmark.
- [ ] No final field contains canonical concepts such as `revenue` or
  `current_assets`.

### Explicitly out of scope

- Evaluating new candidate models (Milestone 8).
- Canonical accounting facts (Milestone 9).
- Ratios, growth, TTM, MRQ, valuation, or other features (Milestone 10).

### Dependencies

- Milestones 0–6 and completed review/audit policy thresholds.

## Milestone 8 — Benchmark/evaluation runner

### Purpose

Evaluate any future vision model or prompt against frozen visual gold with
deterministic, diagnostic metrics rather than a single opaque accuracy score.

### Inputs

- Frozen Milestone 7 visual gold bundle.
- Candidate model annotations conforming to a recorded schema/prompt/run.
- Versioned deterministic comparison and evaluation rules.

### Outputs

- Per-row, per-column, per-cell, and per-document error records.
- Aggregate metrics with statement/form breakdowns.
- Reproducible evaluation report linked to exact gold and candidate versions.

### Implementation tasks

- [ ] Validate candidate source hashes and schema compatibility before scoring.
- [ ] Reuse/freeze comparison normalization appropriate to benchmark scoring.
- [ ] Implement exact raw value accuracy.
- [ ] Implement normalized comparison value accuracy.
- [ ] Implement full-cell accuracy over the hydrated row path, column path, and
  raw value.
- [ ] Implement row recall/completeness, row-path accuracy, and row-kind
  accuracy, including standalone section headings.
- [ ] Implement column recall/completeness and column-path accuracy.
- [ ] Implement ordered table-structure accuracy over row and column manifests.
- [ ] Implement cell recall/completeness and hallucinated/extra-cell rate.
- [ ] Implement document-perfect rate.
- [ ] Break errors down by statement type and 10-K versus 10-Q.
- [ ] Report denominators, missing documents, and invalid outputs explicitly.
- [ ] Export machine-readable results alongside human-readable summaries.

### Important design decisions

- A candidate cannot receive credit by changing the frozen gold or comparison
  policy during evaluation.
- Row, column, path, row-kind, missing, extra, and value failures remain
  distinguishable.
- Metrics operate on raw visual transcription, not semantic accounting facts.
- Evaluation randomness is avoided; any sampling/report bootstrap is separately
  seeded and does not affect primary scores.

### Tests and acceptance criteria

- [ ] Perfect fixture annotations score 100% on all applicable metrics.
- [ ] Controlled row, column, row-kind, path, value, blank, missing, and extra
  mutations affect only expected metric dimensions.
- [ ] Missing and extra cells have correct, reconciled denominators.
- [ ] Missing and extra rows/columns have correct, reconciled denominators.
- [ ] Aggregates exactly reconcile with structural, per-cell, and per-document
  outputs.
- [ ] Repeated evaluations are byte-identical given identical inputs.

### Explicitly out of scope

- Training models or optimizing prompts inside the evaluation runner.
- Accounting concept accuracy and financial feature correctness.
- LLM judging of output quality.

### Dependencies

- Milestone 7; reuse stable deterministic components from Milestones 4 and 5.

## Milestone 9 — Future accounting-normalization benchmark

### Purpose

Transform visually transcribed reported cells into canonical financial facts in
a separate downstream benchmark.

### Inputs

- Frozen visual gold cells and statement metadata.
- A separately versioned accounting ontology and period/unit rules.
- Independently reviewed canonical-fact annotations.

### Outputs

- Canonical facts such as `"Net sales" → revenue` and
  `"Operating income" → operating_income`.
- Explicit applicability/absence, period, unit, numeric, and semantic fields.
- A benchmark isolated from the visual transcription ground truth.

### Implementation tasks

- [ ] Design the canonical accounting ontology and its version policy.
- [ ] Define correct-absence and applicability semantics.
- [ ] Parse numeric displays without mutating visual raw values.
- [ ] Normalize units and periods with explicit evidence and rules.
- [ ] Map reported rows to canonical concepts with registrant/statement context.
- [ ] Establish separate annotation, review, freeze, and evaluation workflows.

### Important design decisions

- This stage consumes the visual dataset but never rewrites it.
- Canonical mapping, missing attributes, period inference, unit conversion, and
  numeric parsing belong here—not in visual extraction or comparison.
- Ambiguity and not-applicable states must be first-class reviewed outcomes.

### Tests and acceptance criteria

- [ ] Canonical facts trace back to exact frozen visual cells.
- [ ] Visual raw fields remain unchanged and independently loadable.
- [ ] Accounting-specific rules and edge cases have expert-reviewed fixtures.
- [ ] Evaluation distinguishes transcription errors from normalization errors.

### Explicitly out of scope

- This entire milestone is out of scope for the current visual extraction
  implementation.
- Financial ratio and feature calculation remains Milestone 10.

### Dependencies

- A frozen visual dataset from Milestone 7; its implementation should be
  planned as a separate project stage.

## Milestone 10 — Future deterministic financial feature generation

### Purpose

Compute reproducible financial features from canonical facts, using explicit
deterministic formulas rather than asking an LLM to calculate them.

### Inputs

- Reviewed canonical facts from Milestone 9.
- Versioned formula definitions, period-selection rules, and external market
  data where valuation metrics require it.

### Outputs

- Deterministically calculated features with complete input provenance.
- Examples include current ratio, quick ratio, gross/operating margin, ROA,
  ROE, free cash flow, debt/equity, YoY growth, TTM, MRQ, and valuation ratios.

### Implementation tasks

- [ ] Specify formulas, acceptable source concepts, units, and period rules.
- [ ] Define missing-input, divide-by-zero, restatement, and sign behavior.
- [ ] Build deterministic calculation functions with input lineage.
- [ ] Version and snapshot any required external market data.
- [ ] Test formulas against hand-calculated expert fixtures.
- [ ] Separate extraction/normalization quality from calculation quality in
  evaluation reports.

### Important design decisions

- Calculations are code-driven and deterministic by default.
- TTM, MRQ, quarterly derivation, and YoY calculations never leak upstream into
  the visual transcription contract.
- Every output cites its canonical inputs, formula version, and market-data
  snapshot where applicable.

### Tests and acceptance criteria

- [ ] Formula fixtures cover normal and edge cases with exact expected outputs.
- [ ] Repeated calculations with identical inputs are identical.
- [ ] Missing or incompatible inputs produce explicit statuses, not guesses.
- [ ] Every feature has complete lineage to canonical and visual evidence.

### Explicitly out of scope

- This entire milestone is out of scope for the current project phase.
- LLM-generated arithmetic or implicit formulas.
- Modifying the frozen visual or accounting-normalization benchmarks.

### Dependencies

- Milestone 9 canonical facts and separately governed external-data inputs.

## Recommended next session

Implement **Milestone 2 — OpenAI extraction adapter and pilot runner** only.
Begin with mocked transport, immutable artifact persistence, selectors,
dry-run, retry, and resume behavior before making any opt-in pilot API calls.
