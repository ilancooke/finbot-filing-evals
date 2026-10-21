"""Local catalog CLI adapter; only canonical saves may refresh shared outputs.

The receipt lives outside bundle integrity, alongside the writer's operational
state. A saved transaction without a matching receipt is pending, even if the
process stopped between completing the save and invoking this adapter.
"""

from datetime import datetime, timezone
from hashlib import sha256
import json
import subprocess

from .config import ReviewConfig
from .dataset import load_dataset
from .errors import ReviewError
from .exports import json_bytes
from .persistence import _atomic, _target, synchronization_pending, verify_bundle, writer_lock

RECEIPT = ".review/catalog-refresh.json"


def refresh_status(config: ReviewConfig) -> str:
    """Read-only: disabled, unknown (no app saves), pending, or current.

    Current means this app successfully refreshed this bundle revision. It is
    not a claim that unrelated datasets in the shared root have stayed unchanged.
    """
    if not config.catalog_enabled:
        return "disabled"
    root = config.dataset_root
    try:
        if synchronization_pending(root):
            return "pending"
        receipt = _target(root, RECEIPT)
        if receipt.exists():
            record = json.loads(receipt.read_bytes())
            digest = sha256(_target(root, "integrity.json").read_bytes()).hexdigest()
            matches = (
                record.get("status") == "success"
                and record.get("integrity_sha256") == digest
                and record.get("data_root") == str(config.data_root)
            )
            return "current" if matches else "pending"
        return "pending" if any(_target(root, ".review").glob("*/case.before.json")) else "unknown"
    except (OSError, ValueError, AttributeError, ReviewError):
        # A missing/corrupt receipt must never establish catalog freshness.
        return "pending"


def refresh_catalog(config: ReviewConfig) -> bool:
    """Refresh after synchronized persistence or an explicit retry; no shell.

    Return False for copies without touching them or launching any process.
    Hold the existing writer lock through verification, CLI execution and receipt
    replacement so another review save cannot be acknowledged by mistake.
    """
    if not config.catalog_enabled:
        return False
    root = config.dataset_root
    try:
        with writer_lock(root):
            if synchronization_pending(root):
                raise ReviewError("Finish dataset synchronization before refreshing the catalog.")
            verify_bundle(load_dataset(root))
            digest = sha256(_target(root, "integrity.json").read_bytes()).hexdigest()
            # Invalidate an earlier receipt before any attempt. A failed or killed
            # retry may have partially rewritten catalog outputs.
            _atomic(root, RECEIPT, json_bytes({"status": "pending"}))
            interpreter = config.catalog_repo / ".venv/bin/python"
            script = config.catalog_repo / "scripts/build_catalog.py"
            if not interpreter.is_file() or not script.is_file():
                raise ReviewError(
                    "Catalog tooling is missing. Install finbot-catalog's repo-local .venv "
                    "or set --catalog-repo to its repository."
                )
            subprocess.run(
                [str(interpreter), str(script), "--data-root", str(config.data_root)],
                cwd=config.catalog_repo, check=True, capture_output=True, text=True,
                timeout=60,
            )
            if sha256(_target(root, "integrity.json").read_bytes()).hexdigest() != digest:
                raise ReviewError("Bundle revision changed during catalog refresh. Retry for the saved revision.")
            _atomic(root, RECEIPT, json_bytes({
                "status": "success", "integrity_sha256": digest, "data_root": str(config.data_root),
                "refreshed_at_utc": datetime.now(timezone.utc).isoformat(),
            }))
        return True
    except subprocess.TimeoutExpired as error:
        raise ReviewError("Catalog refresh timed out after 60 seconds. Check the catalog CLI and retry.") from error
    except subprocess.CalledProcessError as error:
        raise ReviewError(
            f"Catalog CLI exited with status {error.returncode}. Run the documented catalog command "
            "to inspect its error, then retry."
        ) from error
    except OSError as error:
        raise ReviewError(f"Cannot run catalog tooling or record refresh success: {error}") from error
