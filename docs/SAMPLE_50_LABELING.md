# Assistant draft labels for the 37 additions

Completed 2026-10-22 America/Phoenix (2026-10-23 UTC).

The 37 additions in
`data/filing-evals/golden/earnings-eps-50-v1` now have draft reported/adjusted
diluted EPS observations and source notes. Open **http://127.0.0.1:8502** and
refresh the page to review the prefilled rows. Select AA to start, correct rows
where necessary, and use Confirm and next after reviewing the entire filing.
The original 13 reviewed cases were preserved byte for byte.

| Scope | Source observations | Fiscal evaluation targets | Cumulative/YTD exclusions |
| --- | ---: | ---: | ---: |
| Original 13 reviewed filings | 34 | 20 | 14 |
| New 37 assistant-drafted filings | 117 | 63 | 54 |
| Combined 50 | 151 | 83 | 68 |

The original 13 remain human reviewed. **All 37 additions remain unreviewed**
with null confirmation timestamps; annotation does not count as human review.
The fiscal target counts describe schema projection, not a scored evaluation.

## Annotation method and review priorities

The assistant read the collected source text and financial tables, checked
current versus comparison columns, and inspected HON's 34 collected charts.
Values were transcribed directly; no paid provider API, candidate extractor,
evaluation run, currency conversion or EPS arithmetic was used. Source filenames,
reconciliations and scope decisions are recorded in each case's UI review notes.

The existing review schema retains the latest fiscal quarter and explicitly
reported current YTD amounts. YTD observations have separate cumulative labels
and are excluded by the existing fiscal v2 projection. First-quarter YTD amounts
are not duplicated. Values preserve signs, currencies, decimal precision and
trailing zeroes. An empty adjusted array means no qualifying explicitly stated
adjusted EPS was identified in the selected documents, and still requires review.

Review these distinctions in particular:

- HON, IBM and AT&T: consolidated reported diluted EPS differs from continuing
  operations. HON's selected 10-Q contains no explicitly stated adjusted EPS.
- IBM and AT&T: the primary issuer non-GAAP adjusted measure uses a
  continuing-operations basis. That basis is flagged in the notes; no adjusted
  consolidated amount was calculated.
- INDB, PG and TRV: the primary non-GAAP measure is named operating or core EPS;
  the explicit reconciliation supports its draft adjusted classification.
- META: the explicitly stated EPS excluding the litigation charge is retained
  as adjusted under the significant-items policy; its would-have wording is
  flagged for human review. No adjusted YTD amount was calculated.
- ERIC, GLDG, SPOT and WIT: preserve SEK, CAD, EUR, and Wipro's explicitly
  disclosed INR and USD convenience translations. WIT's USD amounts are reported
  EPS presentations, not adjusted EPS.
- ACI uses 12-week/28-week periods; AZZ, LRCX, PG, WDC and WIT have fiscal-year
  identifiers differing from publication-year/calendar-quarter assumptions.
  WDC's actual first-quarter end is October 2, 2026. NRIX and GLDG end August 31.
- FAST places nine-month columns before quarter columns. WIT places prior-year
  columns before current-year columns. TRV's supplement lists older quarters
  before current quarters. MMM's adjusted figures use its newly stated basis.

## Persistence, audit and verification

Draft labels used the existing `save_changes` writer, retaining backups,
stale-save detection, integrity checks and synchronized JSON/Parquet exports.
The full pre-annotation bundle is backed up at:

```text
data/filing-evals/backups/earnings-eps-50-v1-before-assistant-labels-20261023T022620Z.zip
```

The new bundle's operational audit contains the exact proposed labels, source
document hashes, notes, summary, replacement backups and completion receipt:

```text
.review/assistant-draft-labels-20261023T022620Z/
```

Notes/metadata maintenance first verified the valid saved bundle and retained
exact before/after replacements, with rollback on failure. Original sources,
filing manifests, acquisition provenance and the 13 reviewed cases were not edited.
The new bundle's README, review guide, counts, label exports, metadata and
integrity were refreshed. The shared catalog now reflects 151 label rows across
50 issuers with partial status pending human confirmation.

Validation covers the label schema, fiscal projection of every observation,
JSON/Parquet agreement, source integrity, review state, exact preservation of
original case bytes, and the actual prefilled UI tables and source notes.
Streamlit AppTest opened **all 37** new cases and matched every displayed EPS
value to its saved decimal string, with source notes visible, confirmations
still 13/50 and no writes. The package suite passed **498 tests**; compile,
documentation links and whitespace checks passed.
The human-reviewed evaluation gate is unchanged. Finish the 37 reviews before
running a combined benchmark, and continue reporting original/new/combined
cohorts separately.

Relaunch and catalog-refresh commands are in [the import handoff](SAMPLE_50_IMPORT.md).
