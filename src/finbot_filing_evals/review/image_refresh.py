"""Offline, additive image refresh into a new bundle; never change the source.

An operator supplies published FilingReady snapshots, acquisition records and
already downloaded, hashed image files in a local image-refresh.json manifest.
There are no AWS clients or network calls. Changed packages require confirmation
again; labels/notes are preserved and prior confirmation/provenance is archived.
"""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import shutil
import tempfile

from .dataset import _read_json, load_dataset, safe_file
from .errors import ReviewError
from .exports import build_exports, json_bytes, review_state
from .persistence import _target, inventory, synchronization_pending, verify_bundle, writer_lock


def _write(root, relative, value):
    path = _target(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(value))


def _validate_update(case, update, inputs):
    old = case.to_dict()['filing']
    event = update['filing']
    for key in ('filing_id', 'ticker', 'cik', 'company_name', 'form_type', 'filed_at', 'primary_artifact_id'):
        if event.get(key) != old[key]:
            raise ReviewError(f"Refreshed filing identity changed: {case.case_id} ({key}).")
    artifacts = {a['artifact_id']: a for a in event['artifacts']}
    if len(artifacts) != len(event['artifacts']):
        raise ReviewError('Duplicate refreshed artifact identity.')
    previous = {a['artifact_id']: a for a in old['artifacts']}
    if any(artifacts.get(key) != value for key, value in previous.items()):
        raise ReviewError('Refresh must preserve every original artifact unchanged.')
    added = set(artifacts) - set(previous)
    if not added or set(update['files']) != added:
        raise ReviewError('Refresh files must match exactly the added images.')
    parent = update['filing_record']
    archived = update['event_record']
    records = {a['artifact_id']: a for a in update['artifact_records']}
    if (parent.get('accession_number') != case.filing_id
            or parent.get('ready_snapshot_id') != event.get('snapshot_id')
            or not parent.get('ready_published_at') or parent.get('terminal_at')
            or parent.get('selection_decision') != 'SELECT'
            or set(parent.get('selected_artifact_ids', ())) != set(artifacts)
            or len(records) != len(update['artifact_records']) or set(records) != set(artifacts)):
        raise ReviewError('Refresh requires a complete, published acquisition snapshot.')
    if (json.loads(archived.get('event_json', '{}')) != event
            or archived.get('accession_number') != f"__filing_ready__/{case.filing_id}/{event['snapshot_id']}"
            or archived.get('record_type') != 'filing_ready'
            or archived.get('published_at') != parent['ready_published_at']):
        raise ReviewError('Published event archive differs from the refreshed snapshot.')
    paths = {}
    for key, artifact in artifacts.items():
        row = records[key]
        if (any(row.get(name) != artifact.get(name) for name in
                ('artifact_id', 'filename', 's3_uri', 'size_bytes', 'document_type', 'content_type'))
                or row.get('accession_number') != case.filing_id
                or not row.get('stored_at') or not row.get('published_at') or row.get('terminal_at')):
            raise ReviewError('Acquisition artifact differs from the published snapshot.')
        if key not in added:
            continue
        name = artifact['filename']
        if (not name.lower().endswith(('.jpg', '.jpeg', '.png', '.gif'))
                or type(artifact['size_bytes']) is not int or not 0 < artifact['size_bytes'] <= 8 * 1024 * 1024):
            raise ReviewError('Only bounded supporting raster additions are allowed.')
        mapping = update['files'][key]
        _target(inputs, mapping['path'])  # Reject even an internal symlink.
        path = safe_file(inputs, mapping['path'])
        if path.stat().st_size != artifact['size_bytes']:
            raise ReviewError('Refreshed image size mismatch.')
        body = path.read_bytes()
        if sha256(body).hexdigest() != mapping['sha256']:
            raise ReviewError('Refreshed image hash mismatch.')
        paths[key] = path
    if len(paths) > 128 or sum(artifacts[key]['size_bytes'] for key in paths) > 64 * 1024 * 1024:
        raise ReviewError('Refreshed images exceed the viewer bounds.')
    return paths


def _document_exports(dataset, timestamp):
    import pyarrow as pa
    import pyarrow.parquet as pq

    root = dataset.root
    old = pq.read_table(root / 'documents.parquet')
    indexed = {r['artifact_id']: r for r in old.to_pylist()}
    rows = []
    for case in dataset.cases:
        manifests = {a['artifact_id']: a for a in case.to_dict()['filing']['artifacts']}
        for doc in case.documents:
            rows.append({**indexed.get(doc.artifact_id, {}), **manifests[doc.artifact_id],
                         'case_id': case.case_id, 'ticker': case.ticker, 'filing_id': case.filing_id,
                         'form_type': case.form_type, 'path': doc.relative_path, 'sha256': doc.sha256})
    fields = list(old.schema)
    known = {field.name for field in fields}
    for name in ('case_id', 'ticker', 'filing_id', 'form_type', 'filename', 's3_uri', 'document_type', 'content_type', 'size_bytes'):
        if name not in known:
            fields.append(pa.field(name, pa.int64() if name == 'size_bytes' else pa.string()))
    table = pa.Table.from_pylist(rows, schema=pa.schema(fields))
    sink = io.BytesIO()
    pq.write_table(table, sink)
    body = sink.getvalue()
    (root / 'documents.parquet').write_bytes(body)
    meta, _, _ = _read_json(root, 'documents.metadata.json')
    state = review_state([case.to_dict() for case in dataset.cases])
    meta.update(row_count=len(rows), entity_count=len({case.ticker for case in dataset.cases}),
                sha256=sha256(body).hexdigest(), generated_at_utc=timestamp, updated_at_utc=timestamp,
                notes='Complete source snapshots, including supporting images; original documents preserved.',
                **{k: state[k] for k in ('label_source', 'human_reviewed', 'review_status')})
    _write(root, 'documents.metadata.json', meta)


def _acquisition_exports(root, updates, timestamp):
    path = root / 'source-records.json'
    if path.exists():
        source, _, _ = _read_json(root, path.name)
        ids = set(updates)
        source['filings'] = [r for r in source['filings'] if r['accession_number'] not in ids]
        source['artifacts'] = [r for r in source['artifacts'] if r['accession_number'] not in ids]
        existing_events = {r['accession_number'] for r in source.get('events', [])}
        for accession, update in updates.items():
            source['filings'].append(update['filing_record'])
            source['artifacts'].extend(update['artifact_records'])
            event = update['filing']
            key = f"__filing_ready__/{accession}/{event['snapshot_id']}"
            if key not in existing_events:
                source.setdefault('events', []).append(update['event_record'])
            new_objects = {r['Key']: r for r in update.get('s3_objects', [])}
            old_objects = {r['Key']: r for r in source.get('objects', [])}
            source['objects'] = list((old_objects | new_objects).values())
        source['refreshed_at_utc'] = timestamp
        _write(root, path.name, source)
    path = root / 'source-inventory.json'
    if path.exists():
        source, _, _ = _read_json(root, path.name)
        for entry in [*source.get('cases', []), *source.get('pending_sources', [])]:
            case_id = entry.get('case_id', entry.get('source_id', ''))
            update = next((u for a, u in updates.items() if case_id.endswith(a)), None)
            if update:
                artifacts = update['filing']['artifacts']
                entry.update(files=len(artifacts), bytes=sum(a['size_bytes'] for a in artifacts),
                             snapshot_id=update['filing']['snapshot_id'])
                if 'runtime_fits' in entry:
                    # This old field used the pre-image aggregate document limit.
                    entry.pop('runtime_fits')
                    entry['runtime_fit_status'] = 'not_evaluated_after_image_refresh'
        source['refreshed_at_utc'] = timestamp
        _write(root, path.name, source)


def stage_image_refresh(source, destination, inputs):
    """Create a validated new bundle. On failure, remove only our temporary copy."""
    source, inputs = Path(source).resolve(strict=True), Path(inputs).resolve(strict=True)
    destination = Path(destination).absolute()
    _target(destination.parent, destination.name)
    for base in (source, inputs):
        resolved = destination.resolve()
        if resolved == base or resolved.is_relative_to(base) or base.is_relative_to(resolved):
            raise ReviewError('Refreshed bundle must be separate from source and import directories.')
    if destination.exists():
        raise ReviewError('Refreshed destination must be new.')
    timestamp = datetime.now(timezone.utc).isoformat()
    with writer_lock(source):
        if synchronization_pending(source):
            raise ReviewError('Finish the pending label save before refreshing sources.')
        dataset = load_dataset(source)
        baseline = verify_bundle(dataset)
        incoming, raw, _ = _read_json(inputs, 'image-refresh.json')
        if incoming.get('schema_version') != 'filing_image_refresh.v1':
            raise ReviewError('Unsupported image refresh manifest.')
        cases = {case.filing_id: case for case in dataset.cases}
        updates, paths = {}, {}
        if not isinstance(incoming.get('snapshots'), list) or not incoming['snapshots']:
            raise ReviewError('Image refresh requires snapshots.')
        for update in incoming['snapshots']:
            accession = update['filing']['filing_id']
            if accession not in cases or accession in updates:
                raise ReviewError('Unknown or duplicate refreshed filing.')
            paths[accession] = _validate_update(cases[accession], update, inputs)
            updates[accession] = update
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix='.image-refresh-', dir=destination.parent))
        try:
            shutil.copytree(source, temporary, dirs_exist_ok=True)
            for accession, update in updates.items():
                case = cases[accession]
                record = case.to_dict()
                relative = case.path.relative_to(source).as_posix()
                provenance_path = (case.path.parent / 'provenance.json').relative_to(source).as_posix()
                provenance, _, _ = _read_json(temporary, provenance_path)
                history = deepcopy(provenance.get('source_refresh_history', []))
                history.append(dict(refreshed_at_utc=timestamp, previous_filing=record['filing'],
                    previous_review=deepcopy(record['review']),
                    previous_provenance={k: v for k, v in provenance.items() if k != 'source_refresh_history'}))
                objects = {r['Key']: r for r in provenance.get('s3_objects', [])}
                objects.update({r['Key']: r for r in update.get('s3_objects', [])})
                provenance.update(metadata_origin='published_production_snapshot', original_event_available=True,
                    ready_at_origin='published FilingReady snapshot', filing_record=update['filing_record'],
                    artifact_records=update['artifact_records'], s3_objects=list(objects.values()), source_refresh_history=history)
                for key, path in paths[accession].items():
                    name = next(a['filename'] for a in update['filing']['artifacts'] if a['artifact_id'] == key)
                    new_relative = (case.path.parent / 'documents' / name).relative_to(source).as_posix()
                    target = _target(temporary, new_relative)
                    if target.exists():
                        raise ReviewError('New image would overwrite an existing bundle file.')
                    shutil.copyfile(path, target)
                    record['documents'][key] = dict(path=new_relative, sha256=update['files'][key]['sha256'])
                record['filing'] = deepcopy(update['filing'])
                record['review'].update(status='unreviewed', reviewed_at_utc=None)
                _write(temporary, relative, record)
                _write(temporary, provenance_path, provenance)
                _write(temporary, (case.path.parent / 'filing-ready.json').relative_to(source).as_posix(), record['filing'])
            staged = load_dataset(temporary, validate_counts=False)
            metadata, _, _ = _read_json(temporary, 'labels.metadata.json')
            for name, body in build_exports(staged, [c.to_dict() for c in staged.cases], metadata, timestamp).items():
                _target(temporary, name).write_bytes(body)
            staged = load_dataset(temporary)
            _document_exports(staged, timestamp)
            _acquisition_exports(temporary, updates, timestamp)
            receipt = dict(refreshed_at_utc=timestamp, source_integrity_sha256=sha256((source/'integrity.json').read_bytes()).hexdigest(),
                           import_manifest_sha256=sha256(raw).hexdigest(), updated_filings=sorted(updates),
                           added_images=sum(len(p) for p in paths.values()))
            _write(temporary, '.review/image-refresh.json', receipt)
            if (temporary/'README.md').exists():
                with (temporary/'README.md').open('a') as out:
                    out.write(f"\nSource refresh {timestamp}: {receipt['added_images']} supporting images added; "
                              f"current bundle has {staged.document_count} artifacts. Original labels and notes preserved. "
                              "Previous source counts above describe the initial draft.\n")
            integrity = {**baseline, 'files': inventory(temporary), 'updated_at_utc': timestamp}
            _write(temporary, 'integrity.json', integrity)
            verify_bundle(staged)
            from .viewer import case_images, viewer_frame
            for case in staged.cases:
                if case.filing_id in updates:
                    viewer_frame(b'', images=case_images(case))  # Decode/validate every new raster.
            if inventory(source) != baseline['files']:
                raise ReviewError('Original bundle changed during refresh.')
            if destination.exists():
                raise ReviewError('Refreshed destination appeared during staging.')
            os.rename(temporary, destination)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    return load_dataset(destination)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--inputs', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        dataset = stage_image_refresh(args.dataset_root, args.output, args.inputs)
    except (ReviewError, OSError, KeyError, TypeError, ValueError) as exc:
        parser.exit(1, f'Image refresh failed: {exc}\n')
    print(json.dumps(dict(bundle=str(dataset.root), cases=len(dataset.cases),
                         documents=dataset.document_count, observations=dataset.observation_count)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
