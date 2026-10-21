# Disposable-copy review verification

Run from the `finbot-filing-evals` repository with its own Python >=3.12
environment and `.[dev,review]` installed. Normal tests use synthetic temporary
fixtures; the optional browser exercise below uses an existing local bundle.
It requires no SEC/S3 downloads, model calls, AWS access or real review save.

## Create and launch a copy

Stop any writer to the source bundle before copying. This command includes
hidden `.review/` state; do not omit that state from a pending-save backup.
Set `FINBOT_DATA_ROOT` to your existing shared root first.

```bash
qa_parent=$(mktemp -d /private/tmp/finbot-eps-qa.XXXXXX)
cp -R "$FINBOT_DATA_ROOT/filing-evals/golden/earnings-eps-v1" "$qa_parent/dataset-copy"
export FINBOT_QA_DATASET_ROOT="$qa_parent/dataset-copy"
.venv/bin/python -m streamlit run scripts/review_eps.py --server.address 127.0.0.1 --server.port 8517 --browser.gatherUsageStats false -- --dataset-root "$FINBOT_QA_DATASET_ROOT"
```

Open `http://127.0.0.1:8517`. Check the sidebar says **Catalog refresh disabled**.
The explicit copy path takes precedence over `FINBOT_DATA_ROOT`; leave it in
every launch command. Do not point QA at the canonical bundle. If the source
has pending synchronization, finish recovery on the copy first and then verify
its outputs before starting the checklist.

## Browser checklist

All trial annotations and confirmations below belong only to the disposable copy.

1. Check current filing/document/observation counts against the saved bundle;
   the original draft had 13/27/34. Inspect ASML's default EX-99.1 and financial
   statements attachment. Switch between formatted HTML and readable text.
   Download an original and compare its bytes with the selected source file.
2. Double-click a value and enter a trial negative decimal with trailing zeroes,
   such as `-12.930`. Commit with Enter, then change attachments and view modes.
   The draft must remain visible. Save changes: status stays unreviewed and the
   exact decimal survives reload.
3. Use the table toolbar's Fullscreen button to see all six columns. Add an
   adjusted observation with a unique period, value `-0.500`, a three-letter
   currency, blank start and valid end. A partial row must show row errors and
   disable Save/Confirm. Finish it and save. Select its left row gutter, use
   Delete row(s), and close fullscreen. Empty adjusted EPS must be described as
   an empty array, not zero.
4. Request Next with the deletion unsaved. Stay must retain it. Request Next
   again and choose Save; only then should navigation finish. Return with
   Previous and check the deletion persisted. Make another trial edit and test
   navigation's Discard; returning must show the latest saved value.
5. Confirm an eligible filing with empty adjusted EPS. The count increases and
   the app advances. Inspect JNJ's September 27 end and all four unknown starts,
   plus its operational-adjustment note; confirm while retaining the nulls.
6. Inspect TSM's release and both reported values: TWD `29.43` and USD `4.60`.
   Its ADR note must remain visible. Confirm without converting currencies.
7. Open CMC's annual report, scroll inside the document frame, and try readable
   text. Source links are inert, assets are absent, and wide tables may require
   horizontal scrolling. Use fullscreen for an editor wider than the side pane.
8. Confirm the last filing (GM in the initial bundle): stay there, show the
   end-of-list message, and retain accurate progress for earlier unreviewed cases.
   An end-of-list message alone must not claim the whole dataset is reviewed.
9. Stop the server with Ctrl-C, relaunch the same copy command, and reload the
   browser. The first manifest filing opens with saved labels, status, UTC
   confirmation time and progress. Session-only drafts and destinations are gone.
   Saving changed labels on a confirmed filing must reset it to unreviewed and
   clear its confirmation timestamp.

For controlled stale-writer and interruption checks, use synthetic tests rather
than damaging bundle files manually:

```bash
.venv/bin/python -m pytest tests/test_review_app.py -k 'complete_review_workflow or conflicting_draft or pending_save or interrupted_confirmation or guarded_save_retry'
.venv/bin/python -m pytest tests/test_review_persistence.py
```

The stale-draft flow must retain pending edits after refusal; Discard reloads the
latest saved case. Interrupted saves block writes/navigation, including after
restart. Retry synchronization completes the recorded action and stays on the
current filing. Do not delete journals or regenerate hashes to bypass failures.

## Read-only output verification

In another terminal, set `FINBOT_QA_DATASET_ROOT` to the printed copy path, then:

```bash
.venv/bin/python - <<'PY'
import os
from finbot_filing_evals.review.dataset import load_dataset
from finbot_filing_evals.review.exports import review_state
from finbot_filing_evals.review.persistence import synchronization_pending, verify_bundle

root = os.environ['FINBOT_QA_DATASET_ROOT']
assert not synchronization_pending(root), 'Use Retry synchronization in the app first'
dataset = load_dataset(root)
verify_bundle(dataset)
print(f'{len(dataset.cases)} filings / {dataset.document_count} documents / {dataset.observation_count} observations')
print(review_state([case.to_dict() for case in dataset.cases]))
print('Source hashes, JSON/Parquet labels, metadata and integrity agree.')
PY
```

The verifier checks original-source hashes against their preserved manifests,
lossless string Parquet/JSON agreement, counts and review state. Compare source
and copy document/acquisition bytes separately when auditing unchanged inputs.
Keep a before/after SHA-256 inventory of the entire real bundle during QA if
you need proof that real review state also remained untouched.

## Operating failures

| Symptom | Action |
| --- | --- |
| Missing configuration/files | Set the shared root or explicit copy path; the app does not create a bundle. |
| Row error or unknown start warning | Correct partial/invalid rows; retaining a null start is allowed. |
| Saved case changed | Preserve desired edits, Discard to reload, then reapply and save. |
| Synchronization pending | Use Retry synchronization before further writes or filing navigation. Keep the entire `.review/` tree. |
| Unexpected integrity/staging change | Restore a known consistent file set; do not accept changes by rewriting hashes. |
| Catalog refresh pending on canonical saves | Labels are saved. Fix the catalog repo's own environment/path, then Retry catalog refresh. Recovery must finish first. |
| Catalog refresh disabled on a copy | Expected; a catalog-repo override does not enable copies. |
| Busy local port | Stop the old server or choose another `--server.port`; keep the dataset override. |

Catalog success only attests to that bundle revision at refresh time. Real catalog
integration is verified after an explicitly requested real review save, separately
from QA. Retained transactions need disk space and have no automatic pruning.

Stop the QA server and close its tab when done. The temporary copy contains trial
labels; never copy it over the canonical bundle. Remove only that disposable
directory when its evidence is no longer needed.
