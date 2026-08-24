"""Integrity-checked loading for immutable package resources."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
from importlib import resources


class UnknownResourceVersionError(ValueError):
    """A caller requested a prompt or schema version not packaged here."""


class ResourceIntegrityError(RuntimeError):
    """A versioned resource no longer matches its frozen digest."""


def load_versioned_resource(
    *,
    package: str,
    version: str,
    registry: Mapping[str, tuple[str, str]],
) -> bytes:
    try:
        filename, expected_sha256 = registry[version]
    except KeyError as error:
        supported = ", ".join(sorted(registry))
        raise UnknownResourceVersionError(
            f"unknown resource version {version!r}; supported versions: {supported}"
        ) from error

    content = resources.files(package).joinpath(filename).read_bytes()
    actual_sha256 = hashlib.sha256(content).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ResourceIntegrityError(
            f"resource {filename!r} has SHA-256 {actual_sha256}, "
            f"expected {expected_sha256} for {version}"
        )
    return content
