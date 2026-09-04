from services.api.app.schemas.rapid_design import (
    BwbAnalyzeRequest,
    BwbV1Design,
    RapidAnalyzeRequest,
    RapidAnalyzeResponse,
    RapidFamilyManifest,
)
from services.api.app.services.rapid_design.bwb_analysis import analyze_bwb
from services.api.app.services.rapid_design.families.bwb_v1.manifest import (
    bwb_v1_manifest,
)
from services.api.app.services.rapid_design.families.bwb_v1.presets import BWB_PRESETS


class BwbV1Family:
    def __init__(self) -> None:
        self._manifest = bwb_v1_manifest()

    @property
    def manifest(self) -> RapidFamilyManifest:
        return self._manifest

    def analyze(self, request: RapidAnalyzeRequest) -> RapidAnalyzeResponse:
        preset_id = request.preset_id or self.manifest.default_preset_id
        try:
            preset = BWB_PRESETS[preset_id]
        except KeyError as exc:
            raise ValueError(f"unknown bwb_v1 preset: {preset_id}") from exc
        values = {**preset, **request.design}
        design = BwbV1Design.model_validate(values)
        strict_request = BwbAnalyzeRequest(
            family_id="bwb_v1",
            preset_id=preset_id,
            design=design,
            condition=request.condition,
        )
        return analyze_bwb(strict_request)
