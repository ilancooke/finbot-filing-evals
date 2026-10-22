"""Strict JSON, atomic publication, and portable run integrity checks."""

from hashlib import sha256
import json
from pathlib import Path

from ..review.dataset import _nonfinite, _pairs
from ..review.errors import ReviewError
from .contracts import FISCAL_CONTRACT, LEGACY_CONTRACT


def digest(raw):
    return sha256(raw).hexdigest()


def decode(raw):
    try:
        return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_nonfinite)
    except (ValueError, UnicodeError) as error:
        raise ReviewError(f"Invalid evaluation JSON: {error}") from error


def read_json(path):
    return decode(Path(path).read_bytes())


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def inventory(root):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ReviewError("Evaluation artifacts must not contain symlinks.")
        if path.is_file() and path != root / "integrity.json":
            raw = path.read_bytes()
            result[path.relative_to(root).as_posix()] = dict(sha256=digest(raw), size_bytes=len(raw))
    return result


def seal(root):
    write_json(root / "integrity.json", dict(algorithm="sha256", files=inventory(root)))


def load_run(path):
    root = Path(path).expanduser().resolve()
    integrity = read_json(root / "integrity.json")
    if integrity != dict(algorithm="sha256", files=inventory(root)):
        raise ReviewError("Evaluation run integrity mismatch.")
    manifest = read_json(root / "run.json")
    if not isinstance(manifest, dict) or manifest.get("schema_version") not in {"eps_evaluation.v1", "eps_evaluation.v2"}:
        raise ReviewError("Unsupported evaluation run schema.")
    if any(key not in manifest for key in ('run_id', 'dataset_revision', 'scoring_policy')):
        raise ReviewError('Evaluation run manifest is incomplete.')
    expected_contract = FISCAL_CONTRACT if manifest['schema_version'] == 'eps_evaluation.v2' else LEGACY_CONTRACT
    expected_policy = 'eps_fiscal_exact.v2' if expected_contract == FISCAL_CONTRACT else 'eps_exact.v1'
    if (manifest.get('label_contract', LEGACY_CONTRACT) != expected_contract
            or not isinstance(manifest['scoring_policy'], dict)
            or manifest['scoring_policy'].get('version') != expected_policy):
        raise ReviewError('Evaluation run schema, label contract and scoring policy disagree.')
    results = read_json(root / 'results.json')
    if not isinstance(results, dict) or not isinstance(results.get('summary'), dict) or not isinstance(results.get('cases'), list):
        raise ReviewError('Evaluation results must contain a summary and case list.')
    return manifest, results
