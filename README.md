# finbot-filing-evals

This package is the home of a reproducible visual-table extraction benchmark
for screenshots of SEC financial statements. Milestones 0 and 1 are complete:
typed data contracts, deterministic screenshot discovery, configuration, a
frozen V1 visual extraction schema and prompt, and provider interfaces. It
makes no API calls and does not perform consensus matching or accounting
normalization.

See [ROADMAP.md](ROADMAP.md) for the milestone-by-milestone implementation
plan.

## Setup

Python 3.12 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Set the shared finbot data root in your shell. A local `.env` may be used by
your shell tooling, but the package deliberately does not parse `.env` files
or depend on a dotenv library.

```bash
export FINBOT_DATA_ROOT=/Users/ilan/workspace/finbot/data
```

The default source and output layout is then:

```text
$FINBOT_DATA_ROOT/
├── raw/financial_statement_screenshots_golden_dataset/
├── intermediate/
│   ├── golden_dataset_annotations/
│   └── golden_dataset_consensus/
└── processed/financial_statement_visual_gold/
```

The source, intermediate, and processed roots can each be overridden with the
variables documented in `.env.example`. Configuration only resolves paths; it
does not create directories or overwrite artifacts.

## Discover screenshots

```python
from finbot_filing_evals.golden_dataset import GoldenDatasetConfig
from finbot_filing_evals.golden_dataset.discovery import discover_screenshots

config = GoldenDatasetConfig.from_env()
screenshots = discover_screenshots(
    config.source_root,
    expected_count=90,
    require_complete_ticker_sets=True,
)
```

Discovery reads `{ticker}/{filing} {statement}.png`, validates ticker and file
naming, computes a SHA-256 content hash, and derives deterministic statement
metadata without an LLM. Hidden files such as `.DS_Store` are ignored;
misnamed PNG files are errors.

## Validate a V1 extraction response

The model-facing V1 response uses ordered row and column manifests with
contiguous zero-based indices. Cells contain `row_index`, `column_index`, and
`value_raw`; parsing deterministically hydrates the benchmark's self-contained
cell records with arbitrary-depth raw row and column paths.

```python
import json

from finbot_filing_evals.golden_dataset.validation import (
    parse_visual_table_response,
)

provider_payload = json.loads(raw_json_text)
annotation = parse_visual_table_response(provider_payload, screenshots[0])
```

The checked-in JSON Schema rejects unknown fields and validates basic JSON
shape. Deterministic semantic checks additionally enforce contiguous indices,
row-major unique cells, valid references, section-heading behavior, and
nonblank path components. Ticker, filing type, statement type, statement ID,
and source image metadata are never requested from the model; parsing attaches
them from screenshot discovery.

V1 transcription rules are frozen in
`prompts/visual_table_extraction_v1.txt`. Both prompt and schema are loaded
through SHA-256 integrity checks. Changes require a new prompt or schema
version rather than editing V1 in place.

Blank intersections are represented with `value_raw: ""` only when the table
position is visually clear. Every meaningful row is represented separately,
including standalone no-value rows. V1 permits only `data` and
`section_heading` row kinds: section headings have no cells, while subtotals and
totals remain ordinary data rows whose visible labels and values are preserved
without accounting interpretation.

Milestone 2 is the next implementation milestone: the OpenAI extraction adapter
and a controlled pilot runner.

## Tests

```bash
.venv/bin/python -m compileall -q src tests
.venv/bin/python -m pytest
```

Unit tests use temporary fixture files and hand-authored V1 JSON responses. An
additional corpus acceptance test runs only when the configured or conventional
90-image source directory is present. No normal test performs a network
request.
