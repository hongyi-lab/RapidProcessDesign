"""Deterministic clean-room low-order analysis for the ``bwb_v1`` family.

This module is intentionally independent of the MIT hackathon geometry, data,
weights, and nTop files.  It is a conceptual comparison model, not a surrogate
for those artifacts and not a certification-quality aerodynamic solver.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from math import acos, atan2, cos, hypot, log10, pi, radians, sqrt, tan, tanh
from typing import Any

from services.api.app.schemas.rapid_design import (
    BWB_V1_CONDITION_BOUNDS,
    BWB_V1_DESIGN_BOUNDS,
    BwbAnalysisCondition,
    BwbV1Design,
    RapidAnalyzeRequest,
    RapidAnalyzeResponse,
)

MODEL_ID = "clean-room-bwb-low-order"
MODEL_VERSION = "1.0.0"
GEOMETRY_DECODER_ID = "clean-room-bwb-loft"
GEOMETRY_DECODER_VERSION = "1.0.0"
FIDELITY = "conceptual_low_order"

_GAUSS_NODES = (
    -0.9602898564975363,
    -0.7966664774136267,
    -0.5255324099163290,
    -0.1834346424956498,
    0.1834346424956498,
    0.5255324099163290,
    0.7966664774136267,
    0.9602898564975363,
)
_GAUSS_WEIGHTS = (
    0.1012285362903763,
    0.2223810344533745,
    0.3137066458778873,
    0.3626837833783620,
    0.3626837833783620,
    0.3137066458778873,
    0.2223810344533745,
    0.1012285362903763,
)


@dataclass(frozen=True)
class _Geometry:
    reference_area_m2: float
    span_m: float
    semi_span_m: float
    aspect_ratio: float
    mean_aerodynamic_chord_m: float
    wetted_area_m2: float
    taper_ratio: float
    volume_proxy_m3: float
    effective_sweep_deg: float
    kink_severity: float
    outer_area_fraction: float


@dataclass(frozen=True)
class _Curve:
    coordinates: tuple[float, ...]
    values: tuple[float, ...]
    tangents: tuple[float, ...]


def _monotone_curve(
    coordinates: tuple[float, ...],
    values: tuple[float, ...],
    *,
    flatten_root: bool = False,
) -> _Curve:
    """Match the browser decoder's shape-preserving cubic Hermite curve."""

    count = len(coordinates)
    deltas = [
        (values[index + 1] - values[index])
        / max(1e-8, coordinates[index + 1] - coordinates[index])
        for index in range(count - 1)
    ]
    tangents = [0.0] * count
    tangents[0] = 0.0 if flatten_root else deltas[0]
    tangents[-1] = deltas[-1]

    for index in range(1, count - 1):
        before = deltas[index - 1]
        after = deltas[index]
        if (
            before == 0.0
            or after == 0.0
            or (before > 0.0) != (after > 0.0)
        ):
            tangents[index] = 0.0
            continue
        before_width = coordinates[index] - coordinates[index - 1]
        after_width = coordinates[index + 1] - coordinates[index]
        weight_1 = 2.0 * after_width + before_width
        weight_2 = after_width + 2.0 * before_width
        tangents[index] = (weight_1 + weight_2) / (
            weight_1 / before + weight_2 / after
        )

    # Fritsch-Carlson limiting prevents cubic overshoot between valid controls.
    for index, delta in enumerate(deltas):
        if abs(delta) < 1e-12:
            tangents[index] = 0.0
            tangents[index + 1] = 0.0
            continue
        alpha = tangents[index] / delta
        beta = tangents[index + 1] / delta
        magnitude = alpha * alpha + beta * beta
        if magnitude > 9.0:
            scale = 3.0 / sqrt(magnitude)
            tangents[index] = scale * alpha * delta
            tangents[index + 1] = scale * beta * delta

    return _Curve(coordinates, values, tuple(tangents))


def _sample_curve_segment(
    curve: _Curve,
    segment: int,
    coordinate: float,
) -> tuple[float, float]:
    """Return curve value and dy derivative within one control segment."""

    width = curve.coordinates[segment + 1] - curve.coordinates[segment]
    t = max(0.0, min(1.0, (coordinate - curve.coordinates[segment]) / width))
    t2 = t * t
    t3 = t2 * t
    h00 = 2.0 * t3 - 3.0 * t2 + 1.0
    h10 = t3 - 2.0 * t2 + t
    h01 = -2.0 * t3 + 3.0 * t2
    h11 = t3 - t2
    value = (
        h00 * curve.values[segment]
        + h10 * width * curve.tangents[segment]
        + h01 * curve.values[segment + 1]
        + h11 * width * curve.tangents[segment + 1]
    )
    derivative = (
        (6.0 * t2 - 6.0 * t) * curve.values[segment] / width
        + (3.0 * t2 - 4.0 * t + 1.0) * curve.tangents[segment]
        + (-6.0 * t2 + 6.0 * t) * curve.values[segment + 1] / width
        + (3.0 * t2 - 2.0 * t) * curve.tangents[segment + 1]
    )
    return value, derivative


def _integrate_segments(
    coordinates: tuple[float, ...],
    integrand: Callable[[float, int], float],
) -> tuple[float, ...]:
    """Fixed quadrature keeps browser and API metrics deterministic and aligned."""

    integrals: list[float] = []
    for segment, upper in enumerate(coordinates[1:]):
        lower = coordinates[segment]
        midpoint = 0.5 * (lower + upper)
        half_width = 0.5 * (upper - lower)
        integral = sum(
            weight * integrand(midpoint + half_width * node, segment)
            for node, weight in zip(_GAUSS_NODES, _GAUSS_WEIGHTS)
        )
        integrals.append(half_width * integral)
    return tuple(integrals)


def _rounded(value: float, digits: int = 8) -> float:
    """Remove floating-point noise while retaining useful polar precision."""

    rounded = round(float(value), digits)
    return 0.0 if rounded == 0 else rounded


def _canonical_number(value: float) -> float:
    value = round(float(value), 12)
    return 0.0 if value == 0 else value


def design_hash(request: RapidAnalyzeRequest) -> str:
    """Hash the complete, unit-attached design state in a stable JSON encoding."""

    payload = {
        "condition": {
            key: (
                int(value)
                if key == "alpha_samples"
                else _canonical_number(float(value))
            )
            for key, value in request.condition.model_dump().items()
        },
        "design": {
            key: _canonical_number(float(value))
            for key, value in request.design.model_dump().items()
        },
        "family_id": request.family_id,
        "geometry_decoder": {
            "id": GEOMETRY_DECODER_ID,
            "version": GEOMETRY_DECODER_VERSION,
        },
        "performance_model": {"id": MODEL_ID, "version": MODEL_VERSION},
    }
    canonical_json = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _decode_geometry(design: BwbV1Design) -> _Geometry:
    c1 = design.c1_m
    chords = (
        c1,
        c1 * design.c2_ratio,
        c1 * design.c3_ratio,
        c1 * design.c4_ratio,
    )
    segment_spans = (
        c1 * design.b1_ratio,
        c1 * design.b2_ratio,
        c1 * design.b3_ratio,
    )

    inner_sweep = radians(design.sweep_inner_deg)
    outer_sweep = radians(design.sweep_outer_deg)
    x0 = 0.0
    x1 = segment_spans[0] * tan(inner_sweep)
    # x3_ratio is a clean-room kink-shaping control.  Scaling its chordwise
    # offset keeps the entire declared box suitable for a smooth conceptual
    # planform without claiming equivalence to an external geometry decoder.
    kink_offset = 0.25 * c1 * design.x3_ratio
    transition_sweep = 0.55 * inner_sweep + 0.45 * outer_sweep
    x2 = x1 + segment_spans[1] * tan(transition_sweep) + kink_offset
    x3 = x2 + segment_spans[2] * tan(outer_sweep)
    leading_edge_x = (x0, x1, x2, x3)
    span_coordinates = (
        0.0,
        segment_spans[0],
        segment_spans[0] + segment_spans[1],
        sum(segment_spans),
    )
    chord_curve = _monotone_curve(span_coordinates, chords, flatten_root=True)
    leading_edge_curve = _monotone_curve(
        span_coordinates,
        leading_edge_x,
        flatten_root=True,
    )
    half_segment_areas = _integrate_segments(
        span_coordinates,
        lambda coordinate, segment: _sample_curve_segment(
            chord_curve,
            segment,
            coordinate,
        )[0],
    )
    chord_squared_segments = _integrate_segments(
        span_coordinates,
        lambda coordinate, segment: _sample_curve_segment(
            chord_curve,
            segment,
            coordinate,
        )[0]
        ** 2,
    )
    half_area = sum(half_segment_areas)
    reference_area = 2.0 * half_area
    semi_span = sum(segment_spans)
    span = 2.0 * semi_span
    aspect_ratio = span**2 / reference_area
    chord_squared_integral = sum(chord_squared_segments)
    mean_aerodynamic_chord = chord_squared_integral / half_area

    local_sweeps = tuple(
        atan2(leading_edge_x[index + 1] - leading_edge_x[index], segment_spans[index])
        for index in range(3)
    )
    sweep_cosine_segments = _integrate_segments(
        span_coordinates,
        lambda coordinate, segment: (
            _sample_curve_segment(chord_curve, segment, coordinate)[0]
            * cos(
                atan2(
                    _sample_curve_segment(
                        leading_edge_curve,
                        segment,
                        coordinate,
                    )[1],
                    1.0,
                )
            )
        ),
    )
    weighted_cosine = sum(sweep_cosine_segments) / half_area
    effective_sweep = acos(max(0.0, min(1.0, weighted_cosine)))
    kink_severity = abs(local_sweeps[1] - 0.5 * (local_sweeps[0] + local_sweeps[2]))

    leading_edge_segments = _integrate_segments(
        span_coordinates,
        lambda coordinate, segment: hypot(
            1.0,
            _sample_curve_segment(
                leading_edge_curve,
                segment,
                coordinate,
            )[1],
        ),
    )
    trailing_edge_segments = _integrate_segments(
        span_coordinates,
        lambda coordinate, segment: hypot(
            1.0,
            _sample_curve_segment(
                leading_edge_curve,
                segment,
                coordinate,
            )[1]
            + _sample_curve_segment(chord_curve, segment, coordinate)[1],
        ),
    )
    leading_edge_length = sum(leading_edge_segments)
    trailing_edge_length = sum(trailing_edge_segments)
    edge_path_ratio = (leading_edge_length + trailing_edge_length) / (2.0 * semi_span)
    twist_surface_factor = 1.0 + 0.5 * tan(radians(design.twist_tip_deg)) ** 2
    wetted_area = (
        2.0
        * reference_area
        * (1.0 + 0.06 * design.thickness_ratio + 0.02 * (edge_path_ratio - 1.0))
        * twist_surface_factor
    )

    # The same smooth chord-squared integral drives both MAC and volume.
    volume_proxy = 2.0 * 0.62 * design.thickness_ratio * chord_squared_integral

    return _Geometry(
        reference_area_m2=reference_area,
        span_m=span,
        semi_span_m=semi_span,
        aspect_ratio=aspect_ratio,
        mean_aerodynamic_chord_m=mean_aerodynamic_chord,
        wetted_area_m2=wetted_area,
        taper_ratio=design.c4_ratio,
        volume_proxy_m3=volume_proxy,
        effective_sweep_deg=effective_sweep * 180.0 / pi,
        kink_severity=kink_severity,
        outer_area_fraction=half_segment_areas[-1] / half_area,
    )


def _isa_properties(altitude_m: float) -> tuple[float, float, float]:
    temperature_k = 288.15 - 0.0065 * altitude_m
    pressure_pa = 101_325.0 * (temperature_k / 288.15) ** 5.25588
    density_kg_m3 = pressure_pa / (287.05 * temperature_k)
    viscosity_pa_s = (
        1.716e-5
        * (temperature_k / 273.15) ** 1.5
        * (273.15 + 110.4)
        / (temperature_k + 110.4)
    )
    speed_of_sound_m_s = sqrt(1.4 * 287.05 * temperature_k)
    return density_kg_m3, viscosity_pa_s, speed_of_sound_m_s


def _range_checks(
    values: dict[str, Any],
    bounds: dict[str, tuple[float, float, str]],
    prefix: str,
) -> list[dict[str, object]]:
    checks = []
    for name, (minimum, maximum, unit) in bounds.items():
        value = float(values[name])
        checks.append(
            {
                "name": f"{prefix}.{name}",
                "value": value,
                "minimum": minimum,
                "maximum": maximum,
                "unit": unit,
                "status": "pass" if minimum <= value <= maximum else "fail",
            }
        )
    return checks


def _domain_status(
    request: RapidAnalyzeRequest,
    geometry: _Geometry,
    summary: dict[str, float],
) -> dict[str, object]:
    checks = _range_checks(request.design.model_dump(), BWB_V1_DESIGN_BOUNDS, "design")
    checks.extend(
        _range_checks(
            request.condition.model_dump(),
            BWB_V1_CONDITION_BOUNDS,
            "condition",
        )
    )
    chord_margin = min(
        request.design.c2_ratio - request.design.c3_ratio,
        request.design.c3_ratio - request.design.c4_ratio,
    )
    checks.extend(
        [
            {
                "name": "design.chord_order",
                "value": chord_margin,
                "minimum": 0.01,
                "maximum": 1.0,
                "unit": "-",
                "status": "pass",
            },
            {
                "name": "condition.alpha_order",
                "value": request.condition.alpha_max_deg - request.condition.alpha_min_deg,
                "minimum": 0.0,
                "maximum": 30.0,
                "unit": "deg",
                "status": "pass",
            },
        ]
    )
    derived_ranges = (
        ("derived.aspect_ratio", geometry.aspect_ratio, 2.0, 12.0, "-"),
        ("derived.mach", summary["mach"], 0.05, 0.55, "-"),
        (
            "derived.reynolds_number",
            summary["reynolds_number"],
            5.0e4,
            1.0e8,
            "-",
        ),
    )
    checks.extend(
        {
            "name": name,
            "value": value,
            "minimum": minimum,
            "maximum": maximum,
            "unit": unit,
            "status": "pass" if minimum <= value <= maximum else "fail",
        }
        for name, value, minimum, maximum, unit in derived_ranges
    )
    status = (
        "in_domain"
        if all(check["status"] == "pass" for check in checks)
        else "out_of_domain"
    )
    return {"status": status, "checks": checks}


def _polar(
    design: BwbV1Design,
    condition: BwbAnalysisCondition,
    geometry: _Geometry,
) -> tuple[dict[str, list[float]], dict[str, float], list[str]]:
    density, viscosity, speed_of_sound = _isa_properties(condition.altitude_m)
    speed_m_s = condition.speed_kmh / 3.6
    reynolds_number = (
        density * speed_m_s * geometry.mean_aerodynamic_chord_m / viscosity
    )
    mach = speed_m_s / speed_of_sound

    effective_sweep_rad = radians(geometry.effective_sweep_deg)
    taper = design.c4_ratio
    oswald_efficiency = (
        0.90
        - 0.12 * (1.0 - taper) ** 2
        - 0.10 * geometry.kink_severity
        - 0.0015 * max(0.0, geometry.effective_sweep_deg - 25.0)
    )
    oswald_efficiency = max(0.62, min(0.90, oswald_efficiency))
    compressibility = sqrt(max(1.0 - mach**2, 0.70))
    two_dimensional_slope = 2.0 * pi / compressibility
    swept_slope = two_dimensional_slope * cos(effective_sweep_rad)
    cl_alpha = swept_slope / (
        1.0 + swept_slope / (pi * oswald_efficiency * geometry.aspect_ratio)
    )
    induced_drag_factor = 1.0 / (pi * oswald_efficiency * geometry.aspect_ratio)

    skin_friction = 0.455 / max(log10(reynolds_number), 1.0) ** 2.58
    thickness_form_factor = (
        1.0 + 2.7 * design.thickness_ratio + 100.0 * design.thickness_ratio**4
    )
    friction_drag = (
        skin_friction
        * thickness_form_factor
        * geometry.wetted_area_m2
        / geometry.reference_area_m2
    )
    kink_drag = 0.010 * geometry.kink_severity**2 + 0.0008 * design.x3_ratio**2
    twist_drag = 0.00004 * design.twist_tip_deg**2 * geometry.outer_area_fraction
    sweep_drag = 0.0015 * (1.0 - cos(effective_sweep_rad))
    cd0 = 0.0035 + friction_drag + kink_drag + twist_drag + sweep_drag

    effective_incidence_deg = 1.5 + 0.32 * design.twist_tip_deg
    cl_max = (
        1.05
        + 2.0 * (design.thickness_ratio - 0.08)
        + 0.10 * cos(effective_sweep_rad)
        - 0.08 * geometry.kink_severity
    )
    cl_max = max(0.90, min(1.35, cl_max))

    alpha_step = (
        condition.alpha_max_deg - condition.alpha_min_deg
    ) / (condition.alpha_samples - 1)
    alpha_values = [
        condition.alpha_min_deg + index * alpha_step
        for index in range(condition.alpha_samples)
    ]
    alpha_values[0] = condition.alpha_min_deg
    alpha_values[-1] = condition.alpha_max_deg

    cl_values: list[float] = []
    cd_values: list[float] = []
    ld_values: list[float] = []
    for alpha_deg in alpha_values:
        linear_cl = cl_alpha * radians(alpha_deg + effective_incidence_deg)
        cl = cl_max * tanh(linear_cl / cl_max)
        saturation_excess = max(0.0, abs(linear_cl) - 0.82 * cl_max)
        separation_drag = 0.055 * saturation_excess**2
        cd = cd0 + induced_drag_factor * cl**2 + separation_drag
        cl_values.append(cl)
        cd_values.append(cd)
        ld_values.append(cl / cd)

    maximum_ld_index = max(range(len(ld_values)), key=ld_values.__getitem__)
    cl_at_zero_alpha = cl_max * tanh(
        cl_alpha * radians(effective_incidence_deg) / cl_max
    )
    summary = {
        "reynolds_number": _rounded(reynolds_number, 2),
        "mach": _rounded(mach, 6),
        "cl_alpha_per_rad": _rounded(cl_alpha, 8),
        "cl_at_zero_alpha": _rounded(cl_at_zero_alpha, 8),
        "cd0": _rounded(cd0, 8),
        "induced_drag_factor": _rounded(induced_drag_factor, 8),
        "max_ld": _rounded(ld_values[maximum_ld_index], 8),
        "alpha_at_max_ld_deg": _rounded(alpha_values[maximum_ld_index], 6),
    }

    warnings = [
        "Conceptual estimate only; do not use for certification or detailed design.",
        "Clean-room model: no MIT data, weights, source code, or nTop assets are used.",
    ]
    if condition.alpha_min_deg < -6.0 or condition.alpha_max_deg > 12.0:
        warnings.append(
            "High-angle points use an empirical smooth saturation and carry increased uncertainty."
        )
    if geometry.aspect_ratio < 2.0 or geometry.aspect_ratio > 12.0:
        warnings.append(
            "Out of declared analysis domain: derived aspect ratio must remain between 2 and 12."
        )
    if mach < 0.05 or mach > 0.55:
        warnings.append(
            "Out of declared analysis domain: Mach number must remain between 0.05 and 0.55."
        )
    if reynolds_number < 5.0e4 or reynolds_number > 1.0e8:
        warnings.append(
            "Out of declared analysis domain: Reynolds number must remain between 5e4 and 1e8."
        )

    polar = {
        "alpha_deg": [_rounded(value, 6) for value in alpha_values],
        "cl": [_rounded(value, 8) for value in cl_values],
        "cd": [_rounded(value, 8) for value in cd_values],
        "ld": [_rounded(value, 8) for value in ld_values],
    }
    return polar, summary, warnings


def analyze_bwb(request: RapidAnalyzeRequest) -> RapidAnalyzeResponse:
    """Analyze one validated BWB design with reproducible low-order equations."""

    geometry = _decode_geometry(request.design)
    polar, summary, warnings = _polar(request.design, request.condition, geometry)
    return RapidAnalyzeResponse.model_validate(
        {
            "family_id": request.family_id,
            "design_hash": design_hash(request),
            "domain_status": _domain_status(request, geometry, summary),
            "geometry": {
                "reference_area_m2": _rounded(geometry.reference_area_m2, 6),
                "span_m": _rounded(geometry.span_m, 6),
                "semi_span_m": _rounded(geometry.semi_span_m, 6),
                "aspect_ratio": _rounded(geometry.aspect_ratio, 8),
                "mean_aerodynamic_chord_m": _rounded(
                    geometry.mean_aerodynamic_chord_m, 6
                ),
                "wetted_area_m2": _rounded(geometry.wetted_area_m2, 6),
                "taper_ratio": _rounded(geometry.taper_ratio, 8),
                "volume_proxy_m3": _rounded(geometry.volume_proxy_m3, 6),
            },
            "polar": polar,
            "summary": summary,
            "warnings": warnings,
            "provenance": {
                "model_id": MODEL_ID,
                "model_version": MODEL_VERSION,
                "geometry_decoder_id": GEOMETRY_DECODER_ID,
                "geometry_decoder_version": GEOMETRY_DECODER_VERSION,
                "methodology": (
                    "Project-original clean-room shape-preserving cubic BWB loft integration "
                    "with ISA atmosphere, "
                    "finite-wing lift-curve slope, turbulent skin-friction drag, parabolic "
                    "induced drag, and empirical high-angle saturation. No external model "
                    "weights or BWB datasets are loaded."
                ),
                "scope": "whole_aircraft_longitudinal_polar",
                "uses_external_weights": False,
                "uses_mit_assets": False,
            },
            "fidelity": FIDELITY,
        }
    )
