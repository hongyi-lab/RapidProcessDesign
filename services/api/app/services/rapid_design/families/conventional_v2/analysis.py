from __future__ import annotations

import hashlib
import json
from math import cos, log10, pi, radians, sqrt, tanh

from services.api.app.schemas.rapid_design import (
    BWB_V1_CONDITION_BOUNDS,
    ConventionalV2AnalyzeRequest,
    ConventionalV2Design,
    RapidAnalyzeRequest,
    RapidAnalyzeResponse,
    RapidFamilyManifest,
)
from services.api.app.services.rapid_design.bwb_analysis import _isa_properties
from services.api.app.services.rapid_design.families.conventional_v2.geometry import (
    GEOMETRY_DECODER_ID,
    GEOMETRY_DECODER_VERSION,
    decode_conventional_geometry,
)
from services.api.app.services.rapid_design.families.conventional_v2.manifest import (
    CONVENTIONAL_V2_BOUNDS,
    conventional_v2_manifest,
)
from services.api.app.services.rapid_design.families.conventional_v2.presets import (
    CONVENTIONAL_V2_PRESETS,
    PRESET_PROPULSION,
)

MODEL_ID = "clean-room-conventional-conceptual"
MODEL_VERSION = "0.1.0"
FIDELITY = "conceptual_low_order"


def _rounded(value: float, digits: int = 8) -> float:
    result = round(float(value), digits)
    return 0.0 if result == 0 else result


def _design_hash(request: ConventionalV2AnalyzeRequest) -> str:
    payload = {
        "family_id": request.family_id,
        "preset_id": request.preset_id,
        "design": {
            key: _rounded(value, 12)
            for key, value in request.design.model_dump().items()
        },
        "condition": request.condition.model_dump(),
        "geometry_decoder": {
            "id": GEOMETRY_DECODER_ID,
            "version": GEOMETRY_DECODER_VERSION,
        },
        "performance_model": {"id": MODEL_ID, "version": MODEL_VERSION},
    }
    canonical = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _range_check(
    name: str,
    value: float,
    minimum: float,
    maximum: float,
    unit: str,
) -> dict[str, float | str]:
    return {
        "name": name,
        "value": value,
        "minimum": minimum,
        "maximum": maximum,
        "unit": unit,
        "status": "pass" if minimum <= value <= maximum else "fail",
    }


def _polar(
    request: ConventionalV2AnalyzeRequest,
    metrics: dict[str, float],
) -> tuple[dict[str, list[float]], dict[str, float], list[str]]:
    design = request.design
    condition = request.condition
    density, viscosity, speed_of_sound = _isa_properties(condition.altitude_m)
    speed_m_s = condition.speed_kmh / 3.6
    reynolds = (
        density * speed_m_s * metrics["mean_aerodynamic_chord_m"] / viscosity
    )
    mach = speed_m_s / speed_of_sound
    aspect_ratio = metrics["aspect_ratio"]
    sweep = radians(design.wing_sweep_deg)
    beta = sqrt(max(1.0 - mach * mach, 0.70))
    cl_alpha = (
        2.0
        * pi
        * aspect_ratio
        / (
            2.0
            + sqrt(
                4.0
                + (aspect_ratio * beta / max(cos(sweep), 0.65)) ** 2
            )
        )
    )
    oswald = max(
        0.68,
        min(
            0.88,
            0.86
            - 0.08 * (1.0 - design.wing_taper_ratio) ** 2
            - 0.0015 * design.wing_sweep_deg,
        ),
    )
    induced_factor = 1.0 / (pi * oswald * aspect_ratio)
    skin_friction = 0.455 / max(log10(reynolds), 1.0) ** 2.58
    engine_count = 2 if PRESET_PROPULSION[request.preset_id] == "twin_wing_mounted" else 1
    cd0 = (
        0.0065
        + skin_friction * metrics["wetted_area_m2"] / metrics["reference_area_m2"]
        + 0.012 * design.wing_thickness_ratio**2
        + 0.0008 * engine_count
    )
    incidence_deg = 2.0 + 0.12 * design.wing_twist_tip_deg
    cl_max = max(
        1.0,
        min(
            1.55,
            1.18
            + 1.7 * (design.wing_thickness_ratio - 0.08)
            - 0.003 * design.wing_sweep_deg,
        ),
    )
    alpha_step = (
        condition.alpha_max_deg - condition.alpha_min_deg
    ) / (condition.alpha_samples - 1)
    alphas = [
        condition.alpha_min_deg + index * alpha_step
        for index in range(condition.alpha_samples)
    ]
    alphas[0] = condition.alpha_min_deg
    alphas[-1] = condition.alpha_max_deg
    cls: list[float] = []
    cds: list[float] = []
    lds: list[float] = []
    for alpha_deg in alphas:
        linear_cl = cl_alpha * radians(alpha_deg + incidence_deg)
        cl = cl_max * tanh(linear_cl / cl_max)
        excess = max(0.0, abs(linear_cl) - 0.86 * cl_max)
        cd = cd0 + induced_factor * cl * cl + 0.050 * excess * excess
        cls.append(cl)
        cds.append(cd)
        lds.append(cl / cd)
    best_index = max(range(len(lds)), key=lds.__getitem__)
    cl_zero = cl_max * tanh(cl_alpha * radians(incidence_deg) / cl_max)
    polar = {
        "alpha_deg": [_rounded(value, 6) for value in alphas],
        "cl": [_rounded(value) for value in cls],
        "cd": [_rounded(value) for value in cds],
        "ld": [_rounded(value) for value in lds],
    }
    summary = {
        "reynolds_number": _rounded(reynolds, 2),
        "mach": _rounded(mach, 6),
        "cl_alpha_per_rad": _rounded(cl_alpha),
        "cl_at_zero_alpha": _rounded(cl_zero),
        "cd0": _rounded(cd0),
        "induced_drag_factor": _rounded(induced_factor),
        "max_ld": _rounded(lds[best_index]),
        "alpha_at_max_ld_deg": _rounded(alphas[best_index], 6),
    }
    warnings = [
        "Conceptual trend estimate only; it is not a validated high-fidelity analysis.",
        "Preset propulsion is a geometry choice, not an optimization conclusion.",
        "No external model weights, proprietary geometry, or MIT assets are used.",
    ]
    if condition.alpha_min_deg < -6.0 or condition.alpha_max_deg > 12.0:
        warnings.append(
            "High-angle points use empirical smooth saturation and carry increased uncertainty."
        )
    return polar, summary, warnings


def _domain_status(
    request: ConventionalV2AnalyzeRequest,
    metrics: dict[str, float],
    summary: dict[str, float],
) -> dict[str, object]:
    checks = []
    design_values = request.design.model_dump()
    for key, (minimum, maximum, _step, unit, _label) in CONVENTIONAL_V2_BOUNDS.items():
        checks.append(
            _range_check(f"design.{key}", design_values[key], minimum, maximum, unit)
        )
    for key, (minimum, maximum, unit) in BWB_V1_CONDITION_BOUNDS.items():
        checks.append(
            _range_check(
                f"condition.{key}",
                float(getattr(request.condition, key)),
                minimum,
                maximum,
                unit,
            )
        )
    checks.extend(
        [
            _range_check(
                "derived.aspect_ratio", metrics["aspect_ratio"], 4.0, 24.0, "-"
            ),
            _range_check("derived.mach", summary["mach"], 0.05, 0.55, "-"),
            _range_check(
                "derived.reynolds_number",
                summary["reynolds_number"],
                5.0e4,
                1.0e8,
                "-",
            ),
        ]
    )
    return {
        "status": (
            "in_domain"
            if all(check["status"] == "pass" for check in checks)
            else "out_of_domain"
        ),
        "checks": checks,
    }


def analyze_conventional(
    request: ConventionalV2AnalyzeRequest,
) -> RapidAnalyzeResponse:
    geometry_state, metrics = decode_conventional_geometry(
        request.design, request.preset_id
    )
    polar, summary, warnings = _polar(request, metrics)
    domain_status = _domain_status(request, metrics, summary)
    if domain_status["status"] == "out_of_domain":
        warnings.append(
            "One or more derived values are outside the declared conceptual-model domain."
        )
    provenance = {
        "model_id": MODEL_ID,
        "model_version": MODEL_VERSION,
        "geometry_decoder_id": GEOMETRY_DECODER_ID,
        "geometry_decoder_version": GEOMETRY_DECODER_VERSION,
        "methodology": (
            "Transparent conceptual finite-wing lift, skin-friction/profile drag, "
            "parabolic induced drag and smooth high-angle saturation."
        ),
        "scope": "whole_aircraft_longitudinal_polar",
        "uses_external_weights": False,
        "uses_mit_assets": False,
    }
    return RapidAnalyzeResponse.model_validate(
        {
            "family_id": request.family_id,
            "preset_id": request.preset_id,
            "design_hash": _design_hash(request),
            "geometry_state": geometry_state,
            "geometry_metrics": metrics,
            "analysis": {"polar": polar, "summary": summary},
            "domain_status": domain_status,
            "warnings": warnings,
            "provenance": provenance,
            "fidelity": FIDELITY,
            "geometry": metrics,
            "polar": polar,
            "summary": summary,
        }
    )


class ConventionalV2Family:
    def __init__(self) -> None:
        self._manifest = conventional_v2_manifest()

    @property
    def manifest(self) -> RapidFamilyManifest:
        return self._manifest

    def analyze(self, request: RapidAnalyzeRequest) -> RapidAnalyzeResponse:
        preset_id = request.preset_id or self.manifest.default_preset_id
        try:
            preset = CONVENTIONAL_V2_PRESETS[preset_id]
        except KeyError as exc:
            raise ValueError(f"unknown conventional_v2 preset: {preset_id}") from exc
        values = {**preset, **request.design}
        design = ConventionalV2Design.model_validate(values)
        strict_request = ConventionalV2AnalyzeRequest(
            family_id="conventional_v2",
            preset_id=preset_id,
            design=design,
            condition=request.condition,
        )
        return analyze_conventional(strict_request)
