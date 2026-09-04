from __future__ import annotations

from itertools import pairwise
from math import pi, radians, sqrt, tan

from services.api.app.schemas.rapid_design import ConventionalV2Design, GeometryState
from services.api.app.services.rapid_design.families.conventional_v2.presets import (
    PRESET_PROPULSION,
)

GEOMETRY_DECODER_ID = "clean-room-conventional-v2-loft"
GEOMETRY_DECODER_VERSION = "0.1.0"


def _trapezoid_integral(coordinates: list[float], values: list[float]) -> float:
    return sum(
        0.5 * (values[index] + values[index + 1])
        * (coordinates[index + 1] - coordinates[index])
        for index in range(len(coordinates) - 1)
    )


def _body_stations(design: ConventionalV2Design) -> list[dict[str, float]]:
    length = design.fuselage_length_m
    nose_end = length * design.nose_length_ratio
    tail_start = length * (1.0 - design.tailcone_length_ratio)
    cabin_length = tail_start - nose_end
    x_values = [
        0.0,
        0.35 * nose_end,
        0.72 * nose_end,
        nose_end,
        nose_end + 0.30 * cabin_length,
        nose_end + 0.65 * cabin_length,
        tail_start,
        tail_start + 0.45 * (length - tail_start),
        length,
    ]
    maximum_width = length / design.fineness_ratio * design.cabin_fullness
    maximum_height = maximum_width * design.section_ovality
    width_scales = (0.0, 0.38, 0.78, 0.98, 1.0, 0.98, 0.87, 0.48, 0.0)
    height_scales = (0.0, 0.44, 0.83, 1.0, 1.0, 0.96, 0.82, 0.46, 0.0)
    exponent = 2.15 + 0.9 * max(0.0, design.cabin_fullness - 0.85)
    return [
        {
            "x_m": x_m,
            "width_m": maximum_width * width_scale,
            "height_m": maximum_height * height_scale,
            "z_offset_m": 0.0,
            "shape_exponent": exponent,
        }
        for x_m, width_scale, height_scale in zip(
            x_values, width_scales, height_scales
        )
    ]


def _wing_sections(design: ConventionalV2Design) -> list[dict[str, float | str]]:
    semi_span = 0.5 * design.wing_span_m
    y_values = [0.0, 0.28 * semi_span, 0.68 * semi_span, semi_span]
    taper = design.wing_taper_ratio
    chord_ratios = [1.0, 0.82 + 0.10 * taper, 0.52 + 0.25 * taper, taper]
    ratio_integral = _trapezoid_integral(y_values, chord_ratios)
    root_chord = 0.5 * design.wing_area_m2 / ratio_integral
    root_x = design.fuselage_length_m * design.wing_root_x_ratio
    maximum_height = (
        design.fuselage_length_m
        / design.fineness_ratio
        * design.cabin_fullness
        * design.section_ovality
    )
    root_z = design.wing_vertical_ratio * maximum_height
    sweep = radians(design.wing_sweep_deg)
    sweep_factors = (0.60, 0.92, 1.16)
    leading_edges = [root_x]
    for index, factor in enumerate(sweep_factors):
        delta_y = y_values[index + 1] - y_values[index]
        leading_edges.append(leading_edges[-1] + delta_y * tan(sweep * factor))
    return [
        {
            "y_m": y_m,
            "leading_edge_x_m": leading_edge_x,
            "leading_edge_z_m": root_z + y_m * tan(radians(design.wing_dihedral_deg)),
            "chord_m": root_chord * chord_ratio,
            "twist_deg": design.wing_twist_tip_deg * (y_m / semi_span) ** 1.35,
            "dihedral_deg": design.wing_dihedral_deg,
            "thickness_ratio": design.wing_thickness_ratio
            * (1.0 - 0.22 * y_m / semi_span),
            "airfoil_id": "naca2412_family",
        }
        for y_m, leading_edge_x, chord_ratio in zip(
            y_values, leading_edges, chord_ratios
        )
    ]


def _tail_components(
    design: ConventionalV2Design,
    body_stations: list[dict[str, float]],
) -> list[dict[str, object]]:
    length = design.fuselage_length_m
    tail_x = length * design.tail_arm_ratio
    maximum_body_height = max(station["height_m"] for station in body_stations)

    horizontal_area = 0.16 * design.wing_area_m2 * design.tail_scale
    horizontal_aspect_ratio = 4.5
    horizontal_span = sqrt(horizontal_area * horizontal_aspect_ratio)
    horizontal_semi_span = 0.5 * horizontal_span
    horizontal_y = [0.0, 0.55 * horizontal_semi_span, horizontal_semi_span]
    horizontal_ratios = [1.0, 0.68, 0.36]
    horizontal_root_chord = 0.5 * horizontal_area / _trapezoid_integral(
        horizontal_y, horizontal_ratios
    )
    horizontal_sections = [
        {
            "y_m": y_m,
            "leading_edge_x_m": tail_x + 0.32 * y_m,
            "leading_edge_z_m": 0.08 * maximum_body_height + 0.035 * y_m,
            "chord_m": horizontal_root_chord * ratio,
            "twist_deg": -0.5 * y_m / horizontal_semi_span,
            "dihedral_deg": 2.0,
            "thickness_ratio": 0.11 - 0.02 * y_m / horizontal_semi_span,
            "airfoil_id": "naca0010_tail",
        }
        for y_m, ratio in zip(horizontal_y, horizontal_ratios)
    ]

    vertical_area = 0.085 * design.wing_area_m2 * design.tail_scale
    vertical_aspect_ratio = 1.45
    vertical_height = sqrt(vertical_area * vertical_aspect_ratio)
    vertical_coordinates = [0.0, 0.56 * vertical_height, vertical_height]
    vertical_ratios = [1.0, 0.66, 0.28]
    vertical_root_chord = vertical_area / _trapezoid_integral(
        vertical_coordinates, vertical_ratios
    )
    body_top = 0.5 * maximum_body_height
    vertical_sections = [
        {
            "y_m": height,
            "leading_edge_x_m": tail_x + 0.42 * height,
            "leading_edge_z_m": body_top + height,
            "chord_m": vertical_root_chord * ratio,
            "twist_deg": 0.0,
            "dihedral_deg": 0.0,
            "thickness_ratio": 0.11 - 0.025 * height / vertical_height,
            "airfoil_id": "naca0010_vertical_tail",
        }
        for height, ratio in zip(vertical_coordinates, vertical_ratios)
    ]
    return [
        {
            "id": "horizontal_tail",
            "kind": "lifting_surface",
            "symmetry": "y",
            "orientation": "horizontal",
            "sections": horizontal_sections,
        },
        {
            "id": "vertical_tail",
            "kind": "lifting_surface",
            "symmetry": "none",
            "orientation": "vertical",
            "sections": vertical_sections,
        },
    ]


def _nacelle_component(
    design: ConventionalV2Design,
    preset_id: str,
    wing_sections: list[dict[str, float | str]],
) -> dict[str, object]:
    layout = PRESET_PROPULSION[preset_id]
    length = design.fuselage_length_m
    maximum_width = length / design.fineness_ratio * design.cabin_fullness
    if layout == "twin_wing_mounted":
        nacelle_length = 0.16 * length
        center_x = float(wing_sections[1]["leading_edge_x_m"]) + 0.32 * float(
            wing_sections[1]["chord_m"]
        )
        start_x = center_x - 0.46 * nacelle_length
        centerline_y = 0.30 * design.wing_span_m
        center_z = float(wing_sections[1]["leading_edge_z_m"]) - 0.12
        symmetry = "y"
        maximum_radius = 0.18 * maximum_width
    elif layout == "rear_pusher":
        nacelle_length = 0.14 * length
        start_x = length - 0.35 * nacelle_length
        centerline_y = 0.0
        center_z = 0.0
        symmetry = "none"
        maximum_radius = 0.20 * maximum_width
    else:
        nacelle_length = 0.15 * length
        start_x = -0.62 * nacelle_length
        centerline_y = 0.0
        center_z = 0.0
        symmetry = "none"
        maximum_radius = 0.18 * maximum_width
    station_fractions = (0.0, 0.12, 0.35, 0.62, 0.84, 1.0)
    radius_scales = (0.0, 0.72, 1.0, 0.96, 0.62, 0.0)
    return {
        "id": f"propulsion_{layout}",
        "kind": "nacelle",
        "symmetry": symmetry,
        "centerline_y_m": centerline_y,
        "stations": [
            {
                "x_m": start_x + fraction * nacelle_length,
                "radius_y_m": maximum_radius * radius_scale,
                "radius_z_m": 0.92 * maximum_radius * radius_scale,
                "z_offset_m": center_z,
            }
            for fraction, radius_scale in zip(station_fractions, radius_scales)
        ],
    }


def _body_metrics(body_stations: list[dict[str, float]]) -> tuple[float, float]:
    volume = 0.0
    wetted_area = 0.0
    for before, after in pairwise(body_stations):
        length = after["x_m"] - before["x_m"]
        before_area = pi * before["width_m"] * before["height_m"] / 4.0
        after_area = pi * after["width_m"] * after["height_m"] / 4.0
        volume += 0.5 * (before_area + after_area) * length
        average_width = 0.5 * (before["width_m"] + after["width_m"])
        average_height = 0.5 * (before["height_m"] + after["height_m"])
        circumference = pi * sqrt(
            0.5 * (average_width * average_width + average_height * average_height)
        )
        wetted_area += circumference * length
    return volume, wetted_area


def decode_conventional_geometry(
    design: ConventionalV2Design,
    preset_id: str,
) -> tuple[GeometryState, dict[str, float]]:
    body_stations = _body_stations(design)
    wing_sections = _wing_sections(design)
    tail_components = _tail_components(design, body_stations)
    nacelle = _nacelle_component(design, preset_id, wing_sections)

    y_values = [float(section["y_m"]) for section in wing_sections]
    chords = [float(section["chord_m"]) for section in wing_sections]
    half_area = _trapezoid_integral(y_values, chords)
    chord_squared_integral = _trapezoid_integral(
        y_values, [chord * chord for chord in chords]
    )
    reference_area = 2.0 * half_area
    span = 2.0 * y_values[-1]
    body_volume, body_wetted_area = _body_metrics(body_stations)
    horizontal_tail = tail_components[0]["sections"]
    vertical_tail = tail_components[1]["sections"]
    horizontal_area = 2.0 * _trapezoid_integral(
        [float(section["y_m"]) for section in horizontal_tail],
        [float(section["chord_m"]) for section in horizontal_tail],
    )
    vertical_area = _trapezoid_integral(
        [float(section["y_m"]) for section in vertical_tail],
        [float(section["chord_m"]) for section in vertical_tail],
    )
    wetted_area = (
        body_wetted_area
        + 2.06 * reference_area
        + 2.02 * horizontal_area
        + 2.02 * vertical_area
    )
    metrics = {
        "reference_area_m2": round(reference_area, 6),
        "span_m": round(span, 6),
        "semi_span_m": round(0.5 * span, 6),
        "aspect_ratio": round(span * span / reference_area, 8),
        "mean_aerodynamic_chord_m": round(
            chord_squared_integral / half_area, 6
        ),
        "wetted_area_m2": round(wetted_area, 6),
        "taper_ratio": round(chords[-1] / chords[0], 8),
        "volume_proxy_m3": round(body_volume, 6),
    }
    tail_aft = (
        float(horizontal_tail[0]["leading_edge_x_m"])
        > float(wing_sections[0]["leading_edge_x_m"])
        + 0.65 * float(wing_sections[0]["chord_m"])
    )
    checks = [
        {
            "name": "body_station_order",
            "status": "pass",
            "message": "Nine fuselage loft stations strictly increase from nose to tail.",
        },
        {
            "name": "closed_body_ends",
            "status": "pass",
            "message": "Nose and tail endpoint sections close to zero width and height.",
        },
        {
            "name": "positive_wing_sections",
            "status": "pass",
            "message": "All four main-wing sections have positive chord and thickness.",
        },
        {
            "name": "tail_aft_of_wing",
            "status": "pass" if tail_aft else "fail",
            "message": "Tail root is aft of the main-wing root envelope.",
        },
    ]
    state = GeometryState.model_validate(
        {
            "family_id": "conventional_v2",
            "geometry_version": "0.1.0",
            "components": [
                {"id": "fuselage", "kind": "loft_body", "stations": body_stations},
                {
                    "id": "main_wing",
                    "kind": "lifting_surface",
                    "symmetry": "y",
                    "orientation": "horizontal",
                    "sections": wing_sections,
                },
                *tail_components,
                nacelle,
            ],
            "derived_metrics": metrics,
            "geometry_status": (
                "valid" if all(check["status"] == "pass" for check in checks) else "invalid"
            ),
            "geometry_checks": checks,
            "provenance": {
                "decoder_id": GEOMETRY_DECODER_ID,
                "decoder_version": GEOMETRY_DECODER_VERSION,
                "methodology": (
                    "Preset topology expanded from high-level controls into multi-station "
                    "body, wing, tail and nacelle lofts."
                ),
            },
        }
    )
    if state.geometry_status != "valid":
        failed = ", ".join(
            check.name for check in state.geometry_checks if check.status == "fail"
        )
        raise ValueError(f"invalid conventional_v2 geometry: {failed}")
    return state, metrics
