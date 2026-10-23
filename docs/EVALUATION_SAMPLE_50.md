# Proposed 50-filing EPS evaluation sample

Selected 2026-10-22 (America/Phoenix); manifest finalized 2026-10-23 UTC.

Keep the exact **13 reviewed filing packages** from the
[experiment report](MODEL_EXPERIMENT_REPORT.md) and add **37 new companies**.
This gives **50 filings from 50 issuers**, with no same-company/same-quarter
8-K/10-Q duplication. The operator explicitly approved useful smaller legacy
filings below the current $5 billion acquisition threshold.

**Import completed:** the selected artifacts now live in the separate
`data/filing-evals/golden/earnings-eps-50-v1` review bundle. It contains 13 reviewed
originals and 37 unreviewed additions. See [the import handoff](SAMPLE_50_IMPORT.md)
for the UI launch command and verification results.

The [selection manifest](EVALUATION_SAMPLE_50.json) is the authoritative list of
accessions, exact S3 prefixes, object keys, sizes, ETags, inspection hashes,
cohorts and selection reasons. The JSON remains the frozen pre-import selection
record; it is not itself an app-loadable bundle. New cases have no reviewed gold
labels yet. The 37 additions have since received source-grounded assistant drafts
for human correction and confirmation; see [the labeling handoff](SAMPLE_50_LABELING.md).
Use the explicit dataset-root in the handoff to open the new bundle.

## Coverage and selection method

Read-only enumeration of
`s3://finbot-prod-state-artifacts82dd59a1-8gt63rcgmaua/` found **66 tickers,
89 filing packages and 263 objects** (147,078,618 bytes). Choose complete
*collected* packages rather than individual convenient attachments. S3 membership
is not a claim that every exhibit at the SEC was acquired.

The proposed sample contains:

- **104 HTML documents and 85 original images** (189 objects, 79,001,929 bytes).
- **37 8-Ks, six 6-Ks, six 10-Qs and one 10-K**. The annual report is the
  retained CMC filing; no additional annual report was available in this snapshot.
- **10 tech/digital companies and 40 others**. The broad tech/digital grouping
  comprises ASML, TSM, ERIC, IBM, LRCX, META, NFLX, SPOT, WDC and WIT.
  Seven are grouped as information technology; META, NFLX and SPOT are digital
  communication services. These are selection groupings, not a refreshed GICS dataset.
- Nine broad sectors: information technology 7, financials 16, industrials 10,
  consumer discretionary 2, health care 4, materials 3, consumer staples 3,
  energy 1 and communication services 4. Eight of the 16 financials are banks;
  the rest cover brokers, asset managers and insurance businesses.
- **Six foreign 6-K filers**: retain ASML and TSM; add ERIC, GLDG, SPOT and WIT.
  This includes every foreign 6-K issuer in the bucket snapshot.
- Smaller legacy businesses as well as large-company anchors such as META, IBM,
  ASML, TSM, JPM and PG. Smaller-company coverage includes industrials, biotech
  and mining as well as regional financial firms.

Selection was based on issuer, sector, size context, filing format and source
content, without evaluating model accuracy on the new cases. All 77 selected
new HTML documents were read from S3 through temporary local copies; their byte
sizes and single-part ETags agreed with the inventory. SHA-256 hashes for these
HTML bytes are in the manifest. Each new package contains EPS terminology;
this is a suitability check, not a completed human review. New images were
inventoried, not manually reviewed or assigned labels.

For the original 13, S3 filenames/sizes agreed with the reviewed bundle, and
all local document SHA-256 hashes were verified. Reuse those local reviewed
cases and original bytes during expansion. Their labels must not be regenerated
from model output or overwritten by an S3 re-import.

## Foreign companies and currencies

| Ticker | Issuer context | Currency review focus | Why it matters |
| --- | --- | --- | --- |
| ASML | Netherlands; original 6-K | EUR | Retain the known currency-sensitive case. |
| TSM | Taiwan; original 6-K | TWD and explicit USD ADR EPS | Retain multiple explicit currency/share presentations. |
| ERIC | Sweden; new 6-K | SEK | Quarterly diluted EPS is explicitly denominated in SEK. |
| GLDG | Canada; new 6-K | CAD | Negative EPS; statements distinguish per-share amounts from thousands of CAD. |
| SPOT | Luxembourg issuer with Swedish operating roots; new 6-K | EUR | Financial statements and quarterly/YTD EPS are in the primary 6-K itself. |
| WIT | India; new 6-K | INR and explicit USD convenience translations | Multiple IFRS exhibits repeat EPS; quarterly and six-month columns need separation. |

These currencies were checked in the collected documents. They are review
priorities, not finalized labels. Do not infer an EPS currency from a US listing,
convert currencies, or include every currency mentioned in a hedging footnote.
Apply the existing extraction contract to explicit EPS presentations and deduplicate
across attachments. These are English-language documents; foreign-domicile
coverage does not establish performance on non-English reports.

## Smaller-company evidence

S3 provenance does not include market cap. The following dated public snapshots
were checked separately to establish size variety. Values are USD and selection
context only; they do not reproduce market caps at filing time or alter the
production acquisition universe. Most of these are mid-caps, not conventional
small-caps; GLDG provides an actual micro-cap case.

| Ticker | Snapshot market cap | Snapshot date | Source |
| --- | --- | --- | --- |
| GLDG | $173.82M | 2026-10-19 | [Stock Analysis](https://stockanalysis.com/stocks/gldg/market-cap/) |
| FBK | $2.59B | 2026-10-20 | [Stock Analysis](https://stockanalysis.com/stocks/fbk/market-cap/) |
| NRIX | $2.84B | 2026-10-21 | [Stock Analysis](https://stockanalysis.com/stocks/nrix/market-cap/) |
| SFNC | $3.19B | 2026-10-16 | [Stock Analysis](https://stockanalysis.com/stocks/sfnc/market-cap/) |
| CNS | $3.58B | 2026-10-16 | [Stock Analysis](https://stockanalysis.com/stocks/cns/market-cap/) |
| BANF | $3.64B | 2026-10-19 | [Stock Analysis](https://stockanalysis.com/stocks/banf/market-cap/) |
| INDB | $3.82B | 2026-10-21 | [Stock Analysis](https://stockanalysis.com/stocks/indb/market-cap/) |
| AZZ | $4.04B | 2026-10-22 | [Stock Analysis](https://stockanalysis.com/stocks/azz/market-cap/) |
| HOMB | $5.82B | 2026-10-16 | [Stock Analysis](https://stockanalysis.com/stocks/homb/market-cap/) |

Eight checked additions are below $5B; HOMB adds a company near the lower end
of the current acquisition threshold. Market caps not checked for this selection
remain null in the manifest rather than being estimated.

## Exact selection

Keep the original 13 in their existing manifest order. The new 37 are listed
alphabetically below; review priority can differ from storage order. Exact
accessions and object keys are in the linked JSON manifest.

| Cohort | Ticker | Company | Form / filed | HTML / images | Selection reason |
| --- | --- | --- | --- | --- | --- |
| Original | ASML | ASML HOLDING NV | 6-K / 2026-10-14 | 3 / 12 | Retain the exact human-reviewed filing and local source membership from the original experiment. |
| Original | BAC | BANK OF AMERICA CORP /DE/ | 8-K / 2026-10-14 | 2 / 19 | Retain the exact human-reviewed filing and local source membership from the original experiment. |
| Original | DAL | DELTA AIR LINES, INC. | 8-K / 2026-10-09 | 2 / 0 | Retain the exact human-reviewed filing and local source membership from the original experiment. |
| Original | DPZ | DOMINOS PIZZA INC | 8-K / 2026-10-13 | 2 / 0 | Retain the exact human-reviewed filing and local source membership from the original experiment. |
| Original | GS | GOLDMAN SACHS GROUP INC | 8-K / 2026-10-13 | 2 / 0 | Retain the exact human-reviewed filing and local source membership from the original experiment. |
| Original | JNJ | JOHNSON & JOHNSON | 8-K / 2026-10-13 | 3 / 0 | Retain the exact human-reviewed filing and local source membership from the original experiment. |
| Original | JPM | JPMORGAN CHASE & CO | 8-K / 2026-10-13 | 3 / 0 | Retain the exact human-reviewed filing and local source membership from the original experiment. |
| Original | MS | MORGAN STANLEY | 8-K / 2026-10-14 | 3 / 0 | Retain the exact human-reviewed filing and local source membership from the original experiment. |
| Original | UNH | UNITEDHEALTH GROUP INC | 8-K / 2026-10-13 | 2 / 16 | Retain the exact human-reviewed filing and local source membership from the original experiment. |
| Original | TSM | TAIWAN SEMICONDUCTOR MANUFACTURING CO LTD | 6-K / 2026-10-15 | 2 / 0 | Retain the exact human-reviewed filing and local source membership from the original experiment. |
| Original | CMC | COMMERCIAL METALS Co | 10-K / 2026-10-16 | 1 / 3 | Retain the exact human-reviewed filing and local source membership from the original experiment. |
| Original | RTX | RTX Corp | 10-Q / 2026-10-20 | 1 / 0 | Retain the exact human-reviewed filing and local source membership from the original experiment. |
| Original | GM | General Motors Co | 10-Q / 2026-10-20 | 1 / 0 | Retain the exact human-reviewed filing and local source membership from the original experiment. |
| New | AA | Alcoa | 8-K / 2026-10-15 | 2 / 0 | Aluminum producer; reported/adjusted results and cyclical non-tech coverage. |
| New | ABT | Abbott Laboratories | 8-K / 2026-10-21 | 2 / 0 | Medical devices and diagnostics; reported and adjusted diluted EPS. |
| New | ACI | Albertsons | 8-K / 2026-10-13 | 2 / 0 | Supermarket operator; off-calendar fiscal quarter and cumulative columns. |
| New | AZZ | AZZ | 8-K / 2026-10-13 | 2 / 0 | Smaller coatings business; fiscal Q2 FY2027 and GAAP/non-GAAP reconciliation. |
| New | BANF | BancFirst | 8-K / 2026-10-21 | 2 / 1 | Smaller regional bank; compact release; one stored image is not an image-stress designation. |
| New | BLK | BlackRock | 8-K / 2026-10-14 | 3 / 0 | Large asset manager; earnings release and financial supplement. |
| New | CBSH | Commerce Bancshares | 8-K / 2026-10-20 | 2 / 0 | Regional bank; adds smaller-company financial reporting. |
| New | CNS | Cohen & Steers | 8-K / 2026-10-15 | 3 / 0 | Smaller asset manager; multiple release documents require deduplication. |
| New | ERIC | Ericsson | 6-K / 2026-10-15 | 2 / 0 | Foreign telecom equipment; explicit SEK diluted EPS and quarter/YTD columns. |
| New | FAST | Fastenal | 8-K / 2026-10-14 | 2 / 0 | Industrial distribution; current quarter and nine-month columns. |
| New | FBK | FB Financial | 8-K / 2026-10-13 | 3 / 0 | Smaller bank; reported/adjusted EPS and supplemental financial tables. |
| New | GLDG | GoldMining | 6-K / 2026-10-14 | 2 / 0 | Canadian mining issuer; CAD loss per share, basic/diluted wording and quarter/YTD separation. |
| New | HAL | Halliburton | 8-K / 2026-10-20 | 2 / 0 | Oilfield services; reported and adjusted diluted EPS. |
| New | HOMB | Home BancShares | 8-K / 2026-10-14 | 2 / 0 | Lower-end-of-current-universe bank; multiple quarterly comparisons and adjusted EPS. |
| New | HON | Honeywell | 10-Q / 2026-10-22 | 1 / 34 | Required image case: 34 stored JPEGs; continuing/discontinued operations and total EPS. |
| New | IBKR | Interactive Brokers | 8-K / 2026-10-15 | 2 / 0 | Electronic brokerage; reported and adjusted EPS without classifying it as an IT company. |
| New | IBM | IBM | 8-K / 2026-10-21 | 2 / 0 | Enterprise technology; GAAP versus operating/non-GAAP presentation. |
| New | INDB | Independent Bank | 8-K / 2026-10-15 | 2 / 0 | Smaller regional bank; current/prior quarter and adjusted results. |
| New | JBHT | J.B. Hunt | 8-K / 2026-10-15 | 2 / 0 | Trucking and logistics; broadens non-bank, non-tech coverage. |
| New | LRCX | Lam Research | 8-K / 2026-10-21 | 2 / 0 | Semiconductor equipment; fiscal Q1 FY2027 and GAAP/non-GAAP EPS. |
| New | META | Meta Platforms | 8-K / 2026-10-21 | 2 / 0 | Large digital platform; reported EPS plus tax-related counterfactual EPS need careful scope review. |
| New | MMM | 3M | 8-K / 2026-10-20 | 2 / 0 | Diversified industrial; reported results and earnings presentation across periods. |
| New | MRSH | Marsh | 8-K / 2026-10-15 | 2 / 0 | Insurance brokerage rather than another bank; reported and adjusted EPS. |
| New | NFLX | Netflix | 10-Q / 2026-10-21 | 1 / 0 | Digital media; use the stored 10-Q because the 8-K lacks its shareholder-letter exhibit. |
| New | NOC | Northrop Grumman | 8-K / 2026-10-20 | 2 / 0 | Defense manufacturer; historical results versus forward guidance. |
| New | NRIX | Nurix Therapeutics | 10-Q / 2026-10-13 | 1 / 0 | Smaller biotech; current profit versus prior losses and off-calendar fiscal Q3. |
| New | PG | Procter & Gamble | 10-Q / 2026-10-22 | 1 / 0 | Consumer products; fiscal Q1 FY2027; stored 8-K lacks its earnings exhibit. |
| New | PM | Philip Morris International | 8-K / 2026-10-21 | 2 / 0 | Consumer staples; distinguish reported/adjusted results, currency-neutral variants and guidance. |
| New | SCHW | Charles Schwab | 8-K / 2026-10-15 | 2 / 0 | Brokerage; GAAP and adjusted EPS. |
| New | SFNC | Simmons First National | 8-K / 2026-10-15 | 2 / 0 | Smaller regional bank; multiple periods and reported/adjusted reconciliation. |
| New | SPOT | Spotify | 6-K / 2026-10-22 | 1 / 0 | Foreign digital media; EUR statements and quarter/YTD EPS within the primary 6-K. |
| New | T | AT&T | 8-K / 2026-10-21 | 3 / 0 | Telecom operator; distinguish continuing-operations and consolidated EPS. |
| New | TRV | Travelers | 8-K / 2026-10-16 | 3 / 0 | Property/casualty insurance; net-income EPS versus core-income EPS terminology. |
| New | UAL | United Airlines | 8-K / 2026-10-20 | 2 / 0 | Airline; reported and adjusted EPS, including adjustments that can reduce reported earnings. |
| New | UNP | Union Pacific | 8-K / 2026-10-22 | 2 / 0 | Railroad; reported/adjusted results and historical/guidance separation. |
| New | WDC | Western Digital | 8-K / 2026-10-22 | 2 / 0 | Storage hardware; fiscal Q1 FY2027 and GAAP/non-GAAP EPS. |
| New | WIT | Wipro | 6-K / 2026-10-20 | 5 / 0 | Foreign IT services; INR and explicit USD translations, IFRS, multiple exhibits and six-month exclusions. |

## Package choices, omissions and reserves

**HON:** choose the 2026-10-22 **10-Q**, accession
`0000773840-26-000143`: one HTML file plus **34 JPEGs**. Its 8-K has two HTML
files and no stored images, so it does not fulfill the requested image case.
The 10-Q also raises a substantive review issue: continuing-operations,
discontinued-operations and total EPS must be distinguished under the existing
consolidated-EPS policy. Do not silently substitute the 8-K or merge both forms.

**NFLX and PG:** use their 10-Qs. The stored 8-Ks reference a shareholder letter
and earnings release, respectively, but those exhibits are absent from the bucket.
Both selected 10-Qs contain diluted EPS. **META** does have its earnings exhibit
in S3 despite its primary filename using an earlier event date; its actual stored
content was inspected before inclusion.

**TSLA, PLD and PGR:** leave out for this expansion. Each stored package contains
only its primary 8-K, references earnings exhibits not present in the snapshot,
and contains no diluted-EPS text on inspection. Their absence is a collection
coverage limitation, not evidence that the underlying company reported no EPS.
They would be useful future additions after collecting their substantive exhibits.

**HOVR:** leave as a reserve. The selected GLDG and NRIX filings already add
legacy small-company/non-bank coverage; prioritize their CAD/IFRS and biotech
variation for these 37 additions. No claim is made about HOVR label contents.

**Additional financial reserves:** BNY, C, CFG, COF, FHN, MTB, PNC, RF, STT,
TFC, USB and WFC. The bucket is heavily populated with financial firms; adding
all of these would displace non-tech operating businesses or repeat similar bank
reporting. These are reserves, not failed filings. Together with the four
omissions above, this accounts for all 16 unselected tickers.

GLDG's primary 6-K references additional exhibits, and WIT references a newspaper
advertisement not present in the snapshot. Their collected financial statements
and EPS-bearing exhibits are present. Review and score only the explicitly
frozen collected package; do not silently download or append other SEC documents.

## Review and evaluation handoff

1. Freeze this membership before running models. Start human review with HON,
   WIT, ERIC, GLDG, SPOT, META, NRIX and AZZ, then finish the remaining additions.
   This order brings image, currency, fiscal-year and scope issues forward.
2. **Completed:** a new 50-case bundle copies the exact original 13 reviewed cases
   and imports the 37 new collected packages as **unreviewed**. The original
   13-case bundle and saved runs are preserved. The selection JSON is not accepted
   directly by the current review app; open the imported bundle instead.
3. Have a person review every new case, including attachment completeness,
   currency, consolidated versus continuing-operations EPS, primary adjusted/core
   measures, current fiscal quarter/year, and exclusion of partial-year totals.
   The UI is now prefilled with assistant source annotations as requested by the
   operator; review and correct them before confirming. Keep future extractor
   evaluation predictions separate from the annotation workflow. Preserve the
   existing review label contract and fiscal v2 evaluation projection.
4. Validate bundle paths, source integrity, exports and review status, then refresh
   the catalog when a real new bundle is created. No catalog refresh is needed
   for planning documents alone. The imported bundle was validated and the
   catalog rebuilt at import completion.
5. Evaluate with the fixed v4 prompt, plain-text HTML and original images. Report
   **original 13**, **new 37** and **combined 50** separately. Use the new 37 as
   the expansion validation cohort; the original 13 were used for tuning and
   cannot become held out by inclusion in a larger total. If the new cases are
   used to tune prompts, retire their held-out status and select fresh validation.

This is a deliberately varied, inventory-constrained sample, not a random sample
of all eligible US-listed equities. Financials remain 32% of the total; utilities
and a usable REIT package are absent; only one annual report is included. Report
those limits with results, and retain failed/invalid requests in the denominator.
Track new-document costs separately from cache-hit repeats. Selection required
only S3 listing/reads; importing sources can incur S3 request/transfer charges,
and future model evaluations incur their configured provider charges.

Validation for this planning change: 50 distinct issuers/accessions; exact 13+37
cohorts; all selected S3 keys present; new HTML bytes verified against inventory;
original local source hashes verified; summary counts independently recomputed;
package suite **498 passed**. No application code, prompts, configs, gold labels,
shared-data outputs or AWS resources were changed.
