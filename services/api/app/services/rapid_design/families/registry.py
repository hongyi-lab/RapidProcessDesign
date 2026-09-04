from __future__ import annotations

from collections.abc import Iterable

from services.api.app.schemas.rapid_design import (
    RapidAnalyzeRequest,
    RapidAnalyzeResponse,
    RapidFamilyManifest,
)
from services.api.app.services.rapid_design.families.base import RapidAircraftFamily
from services.api.app.services.rapid_design.families.bwb_v1 import BwbV1Family
from services.api.app.services.rapid_design.families.conventional_v2 import (
    ConventionalV2Family,
)


class UnknownFamilyError(ValueError):
    pass


class FamilyRegistry:
    def __init__(self, families: Iterable[RapidAircraftFamily]) -> None:
        self._families: dict[str, RapidAircraftFamily] = {}
        for family in families:
            family_id = family.manifest.family_id
            if family_id in self._families:
                raise ValueError(f"duplicate rapid-design family: {family_id}")
            self._families[family_id] = family

    def manifests(self) -> list[RapidFamilyManifest]:
        return [self._families[key].manifest for key in sorted(self._families)]

    def manifest(self, family_id: str) -> RapidFamilyManifest:
        return self.family(family_id).manifest

    def family(self, family_id: str) -> RapidAircraftFamily:
        try:
            return self._families[family_id]
        except KeyError as exc:
            raise UnknownFamilyError(f"unknown aircraft family: {family_id}") from exc

    def analyze(self, request: RapidAnalyzeRequest) -> RapidAnalyzeResponse:
        return self.family(request.family_id).analyze(request)


registry = FamilyRegistry((BwbV1Family(), ConventionalV2Family()))

