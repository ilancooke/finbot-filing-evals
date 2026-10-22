"""A trusted local extractor command receives one label-free request on stdin."""

from decimal import Decimal, InvalidOperation
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time

from ..review.errors import ReviewError
from .contracts import FISCAL_CONTRACT, LEGACY_CONTRACT, require_contract, validate_labels
from .files import decode, digest, read_json

MAX_RESPONSE = 4 * 1024 * 1024


def load_config(path):
    path = Path(path).expanduser().resolve()
    raw = path.read_bytes()
    config = decode(raw)
    if not isinstance(config, dict) or set(config) - {
        "name", "command", "model", "settings", "prompt_file", "timeout_seconds",
        "provider", "region", "aws_profile", "pricing", "label_contract", "html_input"
    }:
        raise ReviewError("Extractor config must be an object with documented fields only.")
    for field in ("name", "model"):
        if not isinstance(config.get(field), str) or not config[field].strip():
            raise ReviewError(f"Extractor config requires a nonblank {field}.")
    require_contract(config.get('label_contract', LEGACY_CONTRACT))
    provider = config.get('provider', 'command')
    if provider not in {'command', 'bedrock', 'openai', 'anthropic'}:
        raise ReviewError('Extractor provider must be command, bedrock, openai or anthropic.')
    if provider == 'command':
        if 'html_input' in config:
            raise ReviewError('html_input is supported only by the Bedrock adapter.')
        command = config.get("command")
        if not isinstance(command, list) or not command or any(not isinstance(arg, str) or not arg for arg in command):
            raise ReviewError("Extractor command must be a nonempty JSON argument list.")
    elif provider == 'bedrock':
        from .bedrock import validate_config
        validate_config(config)
    else:
        from .direct import validate_config
        validate_config(config)
    timeout = config.get("timeout_seconds", 120)
    if type(timeout) not in (float, int) or not math.isfinite(timeout) or not 0 < timeout <= 3600:
        raise ReviewError("timeout_seconds must be greater than zero and at most 3600.")
    if not isinstance(config.get("settings", {}), dict):
        raise ReviewError("Extractor settings must be an object.")
    prompt_path = config.get("prompt_file")
    if not isinstance(prompt_path, str) or not prompt_path.strip():
        raise ReviewError("Extractor config requires prompt_file (relative to the config file or absolute).")
    prompt = (path.parent / prompt_path).read_text(encoding="utf-8")
    if not prompt.strip():
        raise ReviewError("Extractor prompt must not be blank.")
    return dict(**config, config_sha256=digest(raw)), prompt


def response_metadata(value):
    if not isinstance(value, dict) or set(value) - {"labels", "cost_usd", "usage"}:
        raise ReviewError("Extractor response must contain labels and optional cost_usd/usage only.")
    cost = value.get("cost_usd")
    if cost is not None:
        try:
            valid = isinstance(cost, str) and Decimal(cost).is_finite() and Decimal(cost) >= 0
        except InvalidOperation:
            valid = False
        if not valid:
            raise ReviewError("cost_usd must be a nonnegative finite decimal string or null.")
    if "usage" in value and not isinstance(value["usage"], dict):
        raise ReviewError("usage must be an object.")
    return cost, value.get("usage", {})


def response(value, *, contract=LEGACY_CONTRACT):
    cost, usage = response_metadata(value)
    validate_labels(value.get("labels"), location="prediction", contract=contract)
    return value['labels'], cost, usage


def invoke(config, request_path, workdir, raw_path):
    started = time.monotonic()
    # Configuration goes over stdin; paths refer only to the copied source documents.
    # A trusted command has ordinary OS access; this is not a security sandbox.
    env = {key: value for key, value in os.environ.items()
           if key not in {"FINBOT_DATA_ROOT", "FINBOT_HOST_DATA_ROOT", "FINBOT_EVAL_DATASET_ROOT"}}
    error = None
    with raw_path.open("wb") as stdout, tempfile.TemporaryFile() as stderr:
        try:
            result = subprocess.run(config["command"], input=request_path.read_bytes(),
                                    cwd=workdir, env=env, stdout=stdout, stderr=stderr,
                                    timeout=config.get("timeout_seconds", 120), check=False)
            if result.returncode:
                error = f"Extractor exited with status {result.returncode}."
        except subprocess.TimeoutExpired:
            error = "Extractor timed out."
        except OSError as exc:
            error = f"Extractor could not start: {exc.strerror}."
    duration = time.monotonic() - started
    if raw_path.stat().st_size > MAX_RESPONSE:
        # Preserve a bounded excerpt, even if a faulty adapter wrote excessive output.
        with raw_path.open("rb") as stream:
            excerpt = stream.read(MAX_RESPONSE)
        raw_path.write_bytes(excerpt)
        error = "Extractor output exceeds 4 MiB (saved response truncated)."
    return raw_path.read_bytes(), duration, error


def load_predictions(path, case_ids, *, contract=LEGACY_CONTRACT):
    value = read_json(path)
    if contract == FISCAL_CONTRACT:
        if (not isinstance(value, dict) or set(value) != {'schema_version', 'label_contract', 'cases'}
                or value.get('schema_version') != 'eps_predictions.v2' or value.get('label_contract') != contract):
            raise ReviewError('Fiscal v2 saved predictions require an eps_predictions.v2 envelope and matching label_contract; legacy predictions are not converted.')
        value = value['cases']
    if not isinstance(value, dict) or set(value) != set(case_ids):
        raise ReviewError("Predictions must map every dataset case_id exactly once; no unknown or omitted cases.")
    return value
