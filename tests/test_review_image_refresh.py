"""Source migrations must preserve edits and refuse partial or altered packages."""
from copy import deepcopy
from hashlib import sha256
import io
import json

from PIL import Image
import pytest

from conftest import save_json, snapshot
from finbot_filing_evals.review.dataset import load_dataset
from finbot_filing_evals.review.errors import ReviewError
from finbot_filing_evals.review.image_refresh import stage_image_refresh
from finbot_filing_evals.review.persistence import confirm_case, inventory, verify_bundle


@pytest.fixture
def refresh_inputs(writable_dataset, tmp_path):
    source = writable_dataset
    case = load_dataset(source).cases[0]
    old = case.to_dict()
    # Preserve already confirmed labels/notes in history when the source grows.
    confirm_case(source, case.case_id, case.fingerprint, old['labels'])
    case = load_dataset(source).cases[0]
    old = case.to_dict()
    event = deepcopy(old['filing'])
    buffer = io.BytesIO()
    Image.new('RGB', (120, 80), color='white').save(buffer, 'PNG')
    body = buffer.getvalue()
    key = case.filing_id + '/page.png'
    event['artifacts'].append(dict(artifact_id=key, filename='page.png',
        s3_uri='s3://synthetic-fixture/recovered/page.png', size_bytes=len(body),
        document_type='GRAPHIC', content_type='image/png'))
    event['ready_at'] = '2026-10-21T21:35:00.000000Z'
    snapshot(event)
    parent = dict(accession_number=case.filing_id, selected_artifact_ids=sorted(a['artifact_id'] for a in event['artifacts']),
        ready_snapshot_id=event['snapshot_id'], ready_published_at=event['ready_at'], selection_decision='SELECT')
    artifacts = [{**a, 'accession_number':case.filing_id, 'stored_at':event['ready_at'],
                  'published_at':event['ready_at']} for a in event['artifacts']]
    archived = dict(accession_number=f"__filing_ready__/{case.filing_id}/{event['snapshot_id']}",
                    event_json=json.dumps(event), record_type='filing_ready', published_at=event['ready_at'], revision=1)
    update = dict(filing=event, filing_record=parent, artifact_records=artifacts, event_record=archived,
                  s3_objects=[dict(Key='recovered/page.png', Size=len(body))],
                  files={key:dict(path='images/page.png', sha256=sha256(body).hexdigest())})
    inputs = tmp_path/'inputs'
    (inputs/'images').mkdir(parents=True)
    (inputs/'images/page.png').write_bytes(body)
    manifest = dict(schema_version='filing_image_refresh.v1', snapshots=[update])
    save_json(inputs/'image-refresh.json', manifest)
    # Production bundles carry these acquisition exports; the local app fixtures
    # deliberately omit them by default.
    save_json(source/'source-records.json', dict(filings=[{'accession_number':case.filing_id}],
        artifacts=[{'accession_number':case.filing_id, 'artifact_id':a['artifact_id']} for a in old['filing']['artifacts']],
        events=[{'accession_number':'old-archive', 'custom':'preserve'}], objects=[{'Key':'original.htm'}]))
    save_json(source/'source-inventory.json', dict(cases=[{'case_id':case.case_id, 'runtime_fits':True}],
        pending_sources=[{'source_id':case.case_id}], custom=['preserve']))
    save_json(source/'integrity.json', dict(algorithm='sha256', files=inventory(source)))
    return source, inputs, manifest, old


def test_refresh_preserves_sources_labels_notes_and_unrelated_cases(refresh_inputs, tmp_path):
    source, inputs, manifest, old = refresh_inputs
    before = inventory(source)
    other = load_dataset(source).cases[1]
    other_bytes = other.path.read_bytes()
    result = stage_image_refresh(source, tmp_path/'refreshed', inputs)
    verify_bundle(result)
    assert inventory(source) == before
    assert result.document_count == 4 and result.observation_count == 4
    case = result.cases[0].to_dict()
    assert case['labels'] == old['labels']
    assert case['custom_case_metadata'] == old['custom_case_metadata']
    assert case['review']['notes'] == old['review']['notes']
    assert case['review']['status'] == 'unreviewed' and case['review']['reviewed_at_utc'] is None
    assert result.cases[1].path.read_bytes() == other_bytes
    for document in load_dataset(source).cases[0].documents:
        assert (result.root/document.relative_path).read_bytes() == document.read_bytes()
    provenance = json.loads((result.cases[0].path.parent/'provenance.json').read_text())
    history = provenance['source_refresh_history'][-1]
    assert history['previous_filing'] == old['filing']
    assert history['previous_review'] == old['review']
    assert provenance['synthetic'] is True
    records = json.loads((result.root/'source-records.json').read_text())
    assert records['events'][0] == {'accession_number':'old-archive','custom':'preserve'}
    assert records['events'][1] == manifest['snapshots'][0]['event_record']
    assert len(records['artifacts']) == 3
    indexed = json.loads((result.root/'source-inventory.json').read_text())
    assert indexed['cases'][0]['files'] == indexed['pending_sources'][0]['files'] == 3
    assert indexed['custom'] == ['preserve']
    # A normal label save remains usable against the refreshed source inventory.
    case_model=result.cases[0]
    confirm_case(result.root, case_model.case_id, case_model.fingerprint, case['labels'])
    verify_bundle(load_dataset(result.root))


@pytest.mark.parametrize('change', ['hash','missing_file','changed_original','dropped_original',
    'unpublished','wrong_archive','corrupt_image','bad_snapshot','duplicate_case','unknown_case','symlink'])
def test_invalid_refresh_never_changes_source_or_creates_final_output(refresh_inputs, tmp_path, change):
    source, inputs, manifest, old = refresh_inputs
    update = manifest['snapshots'][0]
    image_key = next(iter(update['files']))
    if change == 'hash':
        update['files'][image_key]['sha256']='0'*64
    elif change == 'missing_file':
        (inputs/'images/page.png').unlink()
    elif change == 'changed_original':
        update['filing']['artifacts'][0]['s3_uri']='s3://wrong/source.htm'
    elif change == 'dropped_original':
        update['filing']['artifacts'].pop(0)
    elif change == 'unpublished':
        update['filing_record'].pop('ready_published_at')
    elif change == 'wrong_archive':
        update['event_record']['event_json']='{}'
    elif change == 'corrupt_image':
        path=inputs/'images/page.png'
        body=b'X'*path.stat().st_size
        path.write_bytes(body)
        update['files'][image_key]['sha256']=sha256(body).hexdigest()
    elif change == 'bad_snapshot':
        update['filing']['snapshot_id']='0'*64
        update['filing_record']['ready_snapshot_id']='0'*64
        update['event_record']['event_json']=json.dumps(update['filing'])
        update['event_record']['accession_number']=f"__filing_ready__/{old['filing']['filing_id']}/{'0'*64}"
    elif change == 'duplicate_case':
        manifest['snapshots'].append(deepcopy(update))
    elif change == 'unknown_case':
        update['filing']['filing_id']='0000000000-26-000000'
    else:
        original=inputs/'images/page.png'
        alias=inputs/'images/alias.png'
        alias.symlink_to(original)
        update['files'][image_key]['path']='images/alias.png'
    save_json(inputs/'image-refresh.json',manifest)
    before=inventory(source)
    output=tmp_path/'refused'
    with pytest.raises((ReviewError, OSError)):
        stage_image_refresh(source,output,inputs)
    assert inventory(source)==before
    assert not output.exists()
    assert not list(tmp_path.glob('.image-refresh-*'))


def test_existing_destination_and_pending_saves_are_refused(refresh_inputs, tmp_path):
    source, inputs, _, _ = refresh_inputs
    existing=tmp_path/'existing'
    existing.mkdir()
    (existing/'keep').write_text('keep')
    with pytest.raises(ReviewError):
        stage_image_refresh(source,existing,inputs)
    assert (existing/'keep').read_text()=='keep'
    (source/'.review/pending.json').write_text('{}')
    with pytest.raises(ReviewError, match='pending label save'):
        stage_image_refresh(source,tmp_path/'refused',inputs)
