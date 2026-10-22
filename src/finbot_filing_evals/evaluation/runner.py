"""Freeze reviewed inputs before extraction; never write to a golden bundle."""

from datetime import datetime, timezone
import json
from importlib.metadata import PackageNotFoundError, version
import platform
from pathlib import Path
import shutil
import tempfile

from .. import __version__
from ..review.dataset import load_dataset
from ..review.errors import ReviewError
from ..review.persistence import synchronization_pending, verify_bundle
from .contracts import FISCAL_CONTRACT, LEGACY_CONTRACT, load_schema, project_labels, require_contract
from .extractor import invoke, load_config, load_predictions, response, response_metadata
from .files import decode, digest, inventory, seal, write_json
from .reports import export_tables, report
from .scoring import policy_for, score_case, summarize


def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def dependency_versions():
    result = {}
    for name in ('jsonschema', 'pyarrow', 'boto3', 'botocore', 'html5lib', 'Pillow'):
        try:
            result[name] = version(name)
        except PackageNotFoundError:
            pass
    return result


def freeze(dataset_root, target, *, contract=LEGACY_CONTRACT):
    require_contract(contract)
    dataset = load_dataset(dataset_root)
    if synchronization_pending(dataset.root):
        raise ReviewError('Finish pending golden dataset synchronization before evaluation.')
    unreviewed = [case.case_id for case in dataset.cases if case.review_status != 'human_reviewed']
    if unreviewed:
        raise ReviewError('Evaluation requires every filing to be human reviewed: ' + ', '.join(unreviewed))
    verify_bundle(dataset)
    integrity = (dataset.root / 'integrity.json').read_bytes()
    records = [case.to_dict() for case in dataset.cases]
    snapshot = dict(dataset=dataset.to_dict(), cases=records, source_integrity_sha256=digest(integrity))
    revision = digest(json.dumps(snapshot, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode())
    if contract == FISCAL_CONTRACT:
        targets, exclusions = [], []
        for case in dataset.cases:
            labels, excluded = project_labels(case.to_dict()['labels'], location=case.case_id)
            targets.append(dict(case_id=case.case_id, ticker=case.ticker, form_type=case.form_type, labels=labels))
            exclusions.extend(dict(case_id=case.case_id, **row) for row in excluded)
        projection = dict(schema_version='eps_target_projection.v2', label_contract=contract,
                          source_label_contract=LEGACY_CONTRACT, source_dataset_revision=revision,
                          source_observation_count=dataset.observation_count,
                          target_observation_count=sum(len(rows) for case in targets for rows in case['labels'].values()),
                          excluded_observation_count=len(exclusions), excluded=exclusions)
        write_json(target / 'source_snapshot.json', snapshot)
        write_json(target / 'target_projection.json', projection)
        golden = dict(schema_version=contract, source_dataset_id=dataset.dataset_id,
                      source_dataset_revision=revision, cases=targets)
        revision = digest(json.dumps(golden, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode())
        write_json(target / 'golden.json', golden)
        write_json(target / 'labels.schema.json', load_schema(contract))
    else:
        write_json(target / 'golden.json', snapshot)
    for case in dataset.cases:
        folder = target / 'inputs' / case.case_id
        (folder / 'documents').mkdir(parents=True)
        documents = []
        for document in case.documents:
            (folder / 'documents' / document.filename).write_bytes(document.read_bytes())
            documents.append(dict(artifact_id=document.artifact_id, filename=document.filename,
                                  path=f'documents/{document.filename}', sha256=document.sha256,
                                  content_type=document.content_type, document_type=document.document_type))
        filing = case.to_dict()['filing']
        # Whitelist public filing context; no labels, notes, case paths or dataset root.
        request = dict(schema_version='eps_extraction_request.v2' if contract == FISCAL_CONTRACT else 'eps_extraction_request.v1', case_id=case.case_id,
                       filing={key: filing[key] for key in ('filing_id', 'ticker', 'company_name', 'form_type', 'filed_at', 'cik')},
                       documents=documents, label_schema=load_schema(contract))
        if contract == FISCAL_CONTRACT:
            request['label_contract'] = contract
        write_json(folder / 'request.json', request)
    # Detect concurrent review saves or source changes during snapshot creation.
    fresh = load_dataset(dataset.root)
    verify_bundle(fresh)
    if (synchronization_pending(dataset.root) or fresh.fingerprint != dataset.fingerprint
            or [case.fingerprint for case in fresh.cases] != [case.fingerprint for case in dataset.cases]
            or (dataset.root / 'integrity.json').read_bytes() != integrity):
        raise ReviewError('Golden dataset changed while freezing evaluation inputs; retry.')
    return dataset, revision


def run(dataset_root, output, config_path, *, predictions=None, progress=None):
    config, prompt = load_config(config_path)
    contract = config.get('label_contract', LEGACY_CONTRACT)
    root = Path(dataset_root).expanduser().resolve()
    output = Path(output).expanduser().resolve()
    if output.is_relative_to(root) or root.is_relative_to(output):
        raise ReviewError('Evaluation output must be separate from the golden dataset.')
    if output.exists():
        raise ReviewError('Evaluation output already exists; choose a new directory.')
    output.parent.mkdir(parents=True, exist_ok=True)
    started = now()
    with tempfile.TemporaryDirectory(prefix='.eps-eval-', dir=output.parent) as temp:
        stage = Path(temp) / 'run'
        stage.mkdir()
        dataset, revision = freeze(root, stage, contract=contract)
        frozen = decode((stage / 'golden.json').read_bytes())
        targets = {case['case_id']: case['labels'] for case in frozen['cases']}
        saved = load_predictions(predictions, [case.case_id for case in dataset.cases], contract=contract) if predictions else None
        write_json(stage / 'extractor.json', config)
        (stage / 'prompt.txt').write_text(prompt, encoding='utf-8')
        for case in dataset.cases:
            request_path = stage / 'inputs' / case.case_id / 'request.json'
            request = decode(request_path.read_bytes())
            request.update(prompt=prompt, model=config['model'], settings=config.get('settings', {}))
            if config.get('provider', 'command') == 'bedrock':
                request['html_input'] = config.get('html_input', 'plain_text')
            write_json(request_path, request)
        frozen_inputs = inventory(stage / 'inputs')
        frozen_golden = digest((stage / 'golden.json').read_bytes())
        frozen_evidence = {path.name: digest(path.read_bytes()) for path in stage.iterdir() if path.is_file()}
        provider = config.get('provider', 'command')
        bedrock = None
        preprocessing = 'external command'
        if provider == 'bedrock':
            from .bedrock import BedrockExtractor, preprocessing_description
            preprocessing = preprocessing_description(config)
            if saved is None:
                bedrock = BedrockExtractor(config)
        results = []
        for index, case in enumerate(dataset.cases, 1):
            if progress:
                progress(f'{index}/{len(dataset.cases)}: {case.case_id}')
            workdir = stage / 'inputs' / case.case_id
            request_path = workdir / 'request.json'
            raw_path = stage / 'responses' / f'{case.case_id}.json'
            raw_path.parent.mkdir(exist_ok=True)
            if saved is None:
                raw, duration, error = (bedrock.invoke(request_path, workdir, raw_path) if bedrock else
                                        invoke(config, request_path, workdir, raw_path))
            else:
                write_json(raw_path, saved[case.case_id])
                raw, duration, error = raw_path.read_bytes(), 0.0, None
            predicted, cost, usage = None, None, {}
            try:
                envelope = decode(raw)
                cost, usage = response_metadata(envelope)
                if error is None:
                    predicted, cost, usage = response(envelope, contract=contract)
            except ReviewError as exc:
                error = error or str(exc)
            status = 'error' if error else 'ok'
            score = score_case(targets[case.case_id], predicted, failed=bool(error), contract=contract)
            results.append(dict(case_id=case.case_id, ticker=case.ticker, form_type=case.form_type,
                                status=status, error=error, prediction=predicted, cost_usd=cost,
                                usage=usage, duration_seconds=duration, score=score))
        if (inventory(stage / 'inputs') != frozen_inputs
                or digest((stage / 'golden.json').read_bytes()) != frozen_golden
                or any(digest((stage / name).read_bytes()) != expected for name, expected in frozen_evidence.items())):
            raise ReviewError('Extractor changed frozen evaluation inputs; refusing to publish the run.')
        results = dict(summary=summarize(results), cases=results)
        manifest = dict(schema_version='eps_evaluation.v2' if contract == FISCAL_CONTRACT else 'eps_evaluation.v1', run_id=output.name,
                        dataset_id=dataset.dataset_id, dataset_revision=revision,
                        started_at_utc=started, finished_at_utc=now(), scoring_policy=policy_for(contract),
                        label_contract=contract,
                        mode='saved_predictions' if saved is not None else provider,
                        extractor=config, prompt_sha256=digest(prompt.encode()),
                        package_version=__version__, python_version=platform.python_version(),
                        dependencies=dependency_versions(),
                        implementation={path.name: digest(path.read_bytes()) for path in [
                            *Path(__file__).parent.glob('*.py'), Path(__file__).parent.parent / 'review/viewer.py']},
                        preprocessing=preprocessing,
                        status='completed_with_errors' if results['summary']['extraction_errors'] else 'completed')
        if contract == FISCAL_CONTRACT:
            manifest['target_projection'] = decode((stage / 'target_projection.json').read_bytes())
        write_json(stage / 'results.json', results)
        predictions_export = {
            case['case_id']: dict(labels=case['prediction'], cost_usd=case['cost_usd'], usage=case['usage'])
            for case in results['cases']
        }
        if contract == FISCAL_CONTRACT:
            predictions_export = dict(schema_version='eps_predictions.v2', label_contract=contract, cases=predictions_export)
        write_json(stage / 'predictions.json', predictions_export)
        write_json(stage / 'run.json', manifest)
        export_tables(stage, manifest, results)
        (stage / 'REPORT.md').write_text(report(manifest, results), encoding='utf-8')
        seal(stage)
        if output.exists():
            raise ReviewError('Evaluation output appeared during the run; refusing to replace it.')
        stage.rename(output)
    return manifest, results
