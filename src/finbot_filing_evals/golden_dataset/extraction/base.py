"""Common contract implemented independently by every vision provider."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..models import ExtractionRequest, ExtractionResult, Provider


@runtime_checkable
class ExtractionProvider(Protocol):
    """A provider adapter that processes exactly one image per request."""

    @property
    def provider(self) -> Provider:
        """Stable provider-family identifier."""

        ...

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        """Independently transcribe the request image and retain raw output."""

        ...
