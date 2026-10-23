# 50-filing artifact import

Completed 2026-10-22 America/Phoenix (2026-10-23 UTC).

**Current annotation state:** all 37 additions now have assistant-drafted EPS
rows and source notes for human review. The bundle has 151 source observations;
13 cases are confirmed and 37 remain unreviewed. See
[the labeling handoff](SAMPLE_50_LABELING.md). Counts and empty-label statements
below describe the earlier artifact-only import, before that annotation pass.

The [selected 37 additions](EVALUATION_SAMPLE_50.md) were downloaded from
`finbot-prod-state-artifacts82dd59a1-8gt63rcgmaua` and imported alongside exact
copies of the original 13 reviewed cases into:

```text
/Users/ilan/workspace/finbot/data/filing-evals/golden/earnings-eps-50-v1
```

| State at import | Count |
| --- | ---: |
| Total filings / distinct issuers | 50 |
| Original reviewed filings retained | 13 |
| New unreviewed filings | 37 |
| Newly downloaded HTML files | 77 |
| Newly downloaded images | 35 |
| Newly downloaded bytes | 53,081,714 |
| Total HTML files | 104 |
| Total original images | 85 |
| Total source artifacts | 189 |
| Existing EPS observations retained | 34 |
| EPS observations generated for new cases | 0 |

## Open the labeling UI

The new bundle was launched at **http://127.0.0.1:8502**. To relaunch from the
`finbot-filing-evals` repository:

```bash
.venv/bin/python -m streamlit run scripts/review_eps.py \
  --server.address 127.0.0.1 --server.port 8502 -- \
  --dataset-root /Users/ilan/workspace/finbot/data/filing-evals/golden/earnings-eps-50-v1
```

Select **AA** for the first new case, or **HON** for the 10-Q with 34 JPEGs.
Review all relevant attachments, enter EPS rows, save changes and confirm the
filing when complete. Empty arrays on a new unreviewed case are placeholders;
they do not establish that no qualifying EPS exists. No extraction model was
called and no numeric labels were prefilled.

The original bundle remains at `../earnings-eps-v1` with its reviewed case files
and source bytes unchanged. The app's default dataset path and saved evaluation
configs still refer to that original bundle. Use the explicit path above for 50.

## Provenance and integrity

All selected S3 keys, sizes, ETags and package membership still matched the frozen
[selection manifest](EVALUATION_SAMPLE_50.json) immediately before import.
Downloads used conditional reads against those ETags. All 112 new artifacts
passed byte-count and simple ETag checks; HTML SHA-256 hashes agreed with the
selection hashes, and all 35 new images passed decoding/format verification.

Per-case `provenance.json` records original object metadata, S3 version IDs,
hashes and source URLs. New `filing-ready.json` manifests are explicitly marked
as **reconstructed from S3 artifact metadata**; original upstream events were
not retrieved. Their `ready_at` is the local import timestamp, and display company
names come from the selection manifest. CIKs, filing dates, primary/exhibit types
and artifact identities come from original S3 provenance, not accession-prefix
guesses. Case snapshot IDs are derived from the reconstructed manifests.

Original case directories were copied byte for byte, including labels, notes,
confirmation timestamps, source manifests, provenance and original documents.
The original bundle was verified under its writer lock before copying and again
before publishing the validated new bundle from staging.

The new bundle includes `dataset.json`, authoritative case JSON, document and
label Parquet exports with metadata sidecars, matching label JSON, `REVIEW.md`,
current source inventory/records, the frozen source selection and `integrity.json`.
Historical inventory and metadata are under `provenance/original-13`; archived
sidecars end in `.metadata.archived.json` to avoid false catalog discovery.
Current review state is **in_progress**, 13 confirmed and 37 unreviewed.

## Catalog and checks

The shared catalog was rebuilt. It includes the new 189-row document manifest
and 34-row label export; labels are correctly marked partial while 37 filings
remain unreviewed. Because this separate bundle is outside the app's canonical
default path, automatic catalog refresh after saves is disabled. Refresh after
labeling sessions from this repository with:

```bash
../finbot-catalog/.venv/bin/python ../finbot-catalog/scripts/build_catalog.py \
  --data-root /Users/ilan/workspace/finbot/data
```

Validation: full bundle integrity, labels JSON/Parquet agreement, document manifest
agreement, 50 unique issuers/accessions, all 37 additions unreviewed with empty
arrays, all original case/source bytes preserved, and all new images verified.
Streamlit AppTest loaded 50 filings with 13 confirmed/37 unreviewed and opened
AA, HON, ERIC, GLDG, SPOT, WIT, META, NRIX, PG and NFLX without errors or writes.
The package suite passed **498 tests**. No application code, dependencies, model
settings, original golden data or AWS resources were changed.

Finish human review before evaluation. Preserve original_13/new_37 membership
from `source-selection.json` and report both cohorts and the combined 50.
