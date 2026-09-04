from __future__ import annotations

from typing import Protocol

from services.api.app.schemas.rapid_design import (
    RapidAnalyzeRequest,
    RapidAnalyzeResponse,
    RapidFamilyManifest,
)


class RapidAircraftFamily(Protocol):
    """Small adapter boundary; deliberately not a general plugin framework."""

    @property
    def manifest(self) -> RapidFamilyManifest: ...

    def analyze(self, request: RapidAnalyzeRequest) -> RapidAnalyzeResponse: ...

