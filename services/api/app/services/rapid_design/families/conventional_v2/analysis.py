from __future__ import annotations

import hashlib
import json

import numpy as np

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
)

from .aerodynamics import (
    MIN_CONFIDENCE,
    MODEL_ID,
    MODEL_SIZE,
    MODEL_VERSION,
    SOFTWARE_VERSIONS,
    AircraftAerodynamics,
)

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
        "performance_model": {
            "id": MODEL_ID, "version": MODEL_VERSION,
            "software_versions": SOFTWARE_VERSIONS, "model_size": MODEL_SIZE,
        },
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


def _polar(request: ConventionalV2AnalyzeRequest, geometry_state, metrics):
    condition = request.condition
    model = AircraftAerodynamics(geometry_state, condition)
    alphas = np.linspace(condition.alpha_min_deg, condition.alpha_max_deg, condition.alpha_samples)
    # Include two fixed points for derivatives, independent of the requested plot range.
    aero = model.evaluate(np.concatenate([alphas, [0.0, 0.1]]))
    cls, cds = aero["cl"][:-2], aero["cd"][:-2]
    lds = cls / cds
    best = int(np.argmax(lds))
    density, viscosity, sound_speed = _isa_properties(condition.altitude_m)
    speed = condition.speed_kmh / 3.6
    polar = {
        "alpha_deg": alphas.tolist(), "cl": cls.tolist(), "cd": cds.tolist(),
        "ld": lds.tolist(), "cm": aero["cm"][:-2].tolist(),
        "confidence": aero["confidence"][:-2].tolist(),
    }
    # Include the fixed derivative points: a narrow user sweep may sit at CL=0.
    nonzero = np.flatnonzero(np.abs(aero["cl"]) > 1e-6)
    k = float(np.median(aero["cd_induced"][nonzero] / aero["cl"][nonzero]**2))
    summary = {
        "reynolds_number": density * speed * model.chord / viscosity,
        "mach": speed / sound_speed,
        "cl_alpha_per_rad": float((aero["cl"][-1] - aero["cl"][-2]) / np.radians(0.1)),
        "cl_at_zero_alpha": float(aero["cl"][-2]),
        "cd0": float(aero["cd_profile"][-2]),
        "induced_drag_factor": k,
        "max_ld": float(lds[best]), "alpha_at_max_ld_deg": float(alphas[best]),
        "cm_at_zero_alpha": float(aero["cm"][-2]),
        "cm_alpha_per_rad": float((aero["cm"][-1] - aero["cm"][-2]) / np.radians(0.1)),
        "minimum_confidence": float(np.min(aero["confidence"][:-2])),
        "reference_x_m": float(model.reference[0]),
        "reference_z_m": float(model.reference[2]), "reference_chord_m": model.chord,
    }
    warnings = [
        (
            "Conceptual trend estimate using pretrained NeuralFoil and AeroSandbox AeroBuildup; "
            "not independently validated for these aircraft."
        ),
        (
            "The plotted polar has neutral elevator and moments about the main-wing quarter-chord; "
            "mission analysis separately solves cruise trim at the assumed CG."
        ),
        (
            "Component buildup does not resolve wing-tail wakes, propeller slipstream, "
            "installation interference or deep stall."
        ),
        "Propulsion ratings, CG, elevator geometry and mass coefficients remain design assumptions.",
    ]
    if summary["minimum_confidence"] < MIN_CONFIDENCE:
        warnings.append("Some plotted points have low NeuralFoil confidence; cruise checks "
                        "evaluate confidence again at the trimmed operating points.")
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
    polar, summary, warnings = _polar(request, geometry_state, metrics)
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
            "Canonical section profiles, twist, canted tail surfaces and body stations "
            "evaluated by AeroSandbox AeroBuildup with pretrained NeuralFoil section aerodynamics."
        ),
        "scope": "whole_aircraft_longitudinal_polar",
        "uses_external_weights": True,
        "software_versions": SOFTWARE_VERSIONS,
        "model_size": MODEL_SIZE,
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
