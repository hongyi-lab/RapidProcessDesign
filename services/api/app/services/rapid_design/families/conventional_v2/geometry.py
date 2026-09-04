from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from math import pi, radians, sqrt, tan

from services.api.app.schemas.rapid_design import ConventionalV2Design, GeometryState
from services.api.app.services.rapid_design.families.conventional_v2.presets import (
    PRESET_ARCHETYPES,
    PRESET_PROPULSION,
    PRESET_REFERENCE_BASIS,
)

GEOMETRY_DECODER_ID = "clean-room-conventional-v2-archetype-loft"
GEOMETRY_DECODER_VERSION = "0.2.0"


@dataclass(frozen=True)
class BodyGrammar:
    x_fractions: tuple[float, ...]
    width_scales: tuple[float, ...]
    height_scales: tuple[float, ...]
    z_scales: tuple[float, ...]
    exponents: tuple[float, ...]
    cabin_weights: tuple[float, ...]
    reference_nose_ratio: float
    reference_tailcone_ratio: float
    reference_fullness: float
    reference_ovality: float


@dataclass(frozen=True)
class WingGrammar:
    eta: tuple[float, ...]
    chord_ratios: tuple[float, ...]
    sweep_factors: tuple[float, ...]
    airfoils: tuple[str, ...]
    reference_taper: float


BODY_GRAMMARS: dict[str, BodyGrammar] = {
    "long_endurance_uav": BodyGrammar(
        x_fractions=(0.0, 0.025, 0.07, 0.13, 0.18, 0.31, 0.50, 0.64, 0.72, 0.84, 0.94, 1.0),
        width_scales=(0.0, 0.18, 0.45, 0.72, 0.88, 0.94, 0.96, 0.90, 0.74, 0.48, 0.22, 0.0),
        height_scales=(0.0, 0.20, 0.49, 0.77, 0.92, 0.98, 1.00, 0.94, 0.78, 0.53, 0.26, 0.0),
        z_scales=(0.00, 0.00, 0.01, 0.02, 0.03, 0.03, 0.02, 0.03, 0.06, 0.12, 0.19, 0.24),
        exponents=(2.0, 2.0, 2.05, 2.18, 2.35, 2.55, 2.62, 2.50, 2.30, 2.05, 1.90, 2.0),
        cabin_weights=(0.0, 0.05, 0.22, 0.55, 0.85, 1.0, 1.0, 0.90, 0.60, 0.25, 0.05, 0.0),
        reference_nose_ratio=0.18,
        reference_tailcone_ratio=0.36,
        reference_fullness=0.90,
        reference_ovality=0.86,
    ),
    "fast_cruise_recon": BodyGrammar(
        x_fractions=(0.0, 0.035, 0.085, 0.15, 0.22, 0.27, 0.39, 0.55, 0.68, 0.76, 0.86, 0.94, 1.0),
        width_scales=(0.0, 0.10, 0.28, 0.52, 0.74, 0.88, 0.94, 0.96, 0.88, 0.72, 0.51, 0.25, 0.0),
        height_scales=(0.0, 0.12, 0.32, 0.60, 0.85, 0.98, 1.00, 0.96, 0.84, 0.68, 0.48, 0.25, 0.0),
        z_scales=(0.00, 0.00, 0.01, 0.03, 0.06, 0.08, 0.07, 0.04, 0.03, 0.05, 0.09, 0.13, 0.17),
        exponents=(1.70, 1.78, 1.88, 2.02, 2.20, 2.35, 2.42, 2.38, 2.28, 2.16, 2.02, 1.88, 2.0),
        cabin_weights=(0.0, 0.02, 0.10, 0.30, 0.65, 0.90, 1.0, 1.0, 0.82, 0.52, 0.20, 0.05, 0.0),
        reference_nose_ratio=0.27,
        reference_tailcone_ratio=0.28,
        reference_fullness=0.80,
        reference_ovality=0.92,
    ),
    "payload_utility": BodyGrammar(
        x_fractions=(0.0, 0.02, 0.06, 0.12, 0.20, 0.34, 0.52, 0.68, 0.76, 0.84, 0.92, 1.0),
        width_scales=(0.0, 0.24, 0.56, 0.82, 0.96, 1.02, 1.04, 1.02, 0.94, 0.70, 0.38, 0.0),
        height_scales=(0.0, 0.30, 0.65, 0.95, 1.10, 1.18, 1.20, 1.18, 1.05, 0.78, 0.44, 0.0),
        z_scales=(0.00, -0.01, -0.02, 0.00, 0.04, 0.06, 0.06, 0.06, 0.08, 0.12, 0.18, 0.24),
        exponents=(2.0, 2.15, 2.45, 2.85, 3.35, 3.80, 4.05, 4.00, 3.60, 2.85, 2.20, 2.0),
        cabin_weights=(0.0, 0.08, 0.32, 0.68, 0.95, 1.0, 1.0, 1.0, 0.90, 0.52, 0.15, 0.0),
        reference_nose_ratio=0.12,
        reference_tailcone_ratio=0.24,
        reference_fullness=1.12,
        reference_ovality=1.22,
    ),
}

WING_GRAMMARS: dict[str, WingGrammar] = {
    "long_endurance_uav": WingGrammar(
        eta=(0.0, 0.06, 0.20, 0.48, 0.76, 1.0),
        chord_ratios=(1.0, 0.97, 0.84, 0.59, 0.38, 0.27),
        sweep_factors=(0.12, 0.28, 0.62, 1.02, 1.26),
        airfoils=("naca4415", "naca4415", "naca4414", "naca3412", "naca2411", "naca2410"),
        reference_taper=0.27,
    ),
    "fast_cruise_recon": WingGrammar(
        eta=(0.0, 0.10, 0.30, 0.56, 0.80, 1.0),
        chord_ratios=(1.0, 0.91, 0.73, 0.54, 0.36, 0.25),
        sweep_factors=(0.34, 0.72, 1.00, 1.16, 1.28),
        airfoils=("naca23012", "naca23011", "naca23010", "naca13009", "naca0009", "naca0008"),
        reference_taper=0.25,
    ),
    "payload_utility": WingGrammar(
        eta=(0.0, 0.12, 0.34, 0.58, 0.80, 1.0),
        chord_ratios=(1.0, 1.00, 0.93, 0.80, 0.66, 0.55),
        sweep_factors=(0.00, 0.12, 0.38, 0.70, 0.96),
        airfoils=("naca4418", "naca4418", "naca4417", "naca4415", "naca3413", "naca2412"),
        reference_taper=0.55,
    ),
}


def _trapezoid_integral(coordinates: list[float], values: list[float]) -> float:
    return sum(
        0.5 * (values[index] + values[index + 1])
        * (coordinates[index + 1] - coordinates[index])
        for index in range(len(coordinates) - 1)
    )


def _warp_body_fraction(
    fraction: float,
    grammar: BodyGrammar,
    design: ConventionalV2Design,
) -> float:
    reference_nose = grammar.reference_nose_ratio
    reference_tail_start = 1.0 - grammar.reference_tailcone_ratio
    nose = design.nose_length_ratio
    tail_start = 1.0 - design.tailcone_length_ratio
    if fraction <= reference_nose:
        return nose * fraction / reference_nose
    if fraction >= reference_tail_start:
        tail_fraction = (fraction - reference_tail_start) / (1.0 - reference_tail_start)
        return tail_start + tail_fraction * (1.0 - tail_start)
    cabin_fraction = (fraction - reference_nose) / (reference_tail_start - reference_nose)
    return nose + cabin_fraction * (tail_start - nose)


def _body_stations(
    design: ConventionalV2Design,
    preset_id: str,
) -> list[dict[str, float]]:
    grammar = BODY_GRAMMARS[preset_id]
    length = design.fuselage_length_m
    base_width = length / design.fineness_ratio
    fullness_delta = design.cabin_fullness - grammar.reference_fullness
    ovality_scale = design.section_ovality / grammar.reference_ovality
    stations = []
    for fraction, width, height, z, exponent, cabin_weight in zip(
        grammar.x_fractions,
        grammar.width_scales,
        grammar.height_scales,
        grammar.z_scales,
        grammar.exponents,
        grammar.cabin_weights,
    ):
        local_fullness = max(0.55, 1.0 + 0.90 * fullness_delta * cabin_weight)
        local_height_fullness = max(0.60, 1.0 + 0.62 * fullness_delta * cabin_weight)
        stations.append(
            {
                "x_m": length * _warp_body_fraction(fraction, grammar, design),
                "width_m": base_width * width * local_fullness,
                "height_m": base_width * height * ovality_scale * local_height_fullness,
                "z_offset_m": base_width * z,
                "shape_exponent": exponent,
            }
        )
    return stations


def _wing_sections(
    design: ConventionalV2Design,
    preset_id: str,
    body_stations: list[dict[str, float]],
) -> list[dict[str, float | str]]:
    grammar = WING_GRAMMARS[preset_id]
    semi_span = 0.5 * design.wing_span_m
    y_values = [eta * semi_span for eta in grammar.eta]
    taper_delta = design.wing_taper_ratio - grammar.reference_taper
    chord_ratios = [
        max(0.12, ratio + taper_delta * eta**1.15)
        for eta, ratio in zip(grammar.eta, grammar.chord_ratios)
    ]
    chord_ratios[0] = 1.0
    chord_ratios[-1] = design.wing_taper_ratio
    root_chord = 0.5 * design.wing_area_m2 / _trapezoid_integral(
        y_values, chord_ratios
    )
    root_x = design.fuselage_length_m * design.wing_root_x_ratio
    maximum_height = max(station["height_m"] for station in body_stations)
    center_z = max(body_stations, key=lambda station: station["height_m"])["z_offset_m"]
    root_z = center_z + design.wing_vertical_ratio * maximum_height
    leading_edges = [root_x]
    for index, sweep_factor in enumerate(grammar.sweep_factors):
        delta_y = y_values[index + 1] - y_values[index]
        local_sweep = radians(design.wing_sweep_deg * sweep_factor)
        leading_edges.append(leading_edges[-1] + delta_y * tan(local_sweep))
    return [
        {
            "y_m": y_m,
            "leading_edge_x_m": leading_edge_x,
            "leading_edge_z_m": root_z
            + y_m * tan(radians(design.wing_dihedral_deg)),
            "chord_m": root_chord * chord_ratio,
            "twist_deg": design.wing_twist_tip_deg * eta**1.45,
            "dihedral_deg": design.wing_dihedral_deg,
            "thickness_ratio": design.wing_thickness_ratio
            * (1.0 - 0.28 * eta**0.90),
            "airfoil_id": airfoil,
        }
        for eta, y_m, leading_edge_x, chord_ratio, airfoil in zip(
            grammar.eta,
            y_values,
            leading_edges,
            chord_ratios,
            grammar.airfoils,
        )
    ]


def _body_dimensions(
    body_stations: list[dict[str, float]],
) -> tuple[float, float, float]:
    return (
        max(station["width_m"] for station in body_stations),
        max(station["height_m"] for station in body_stations),
        max(body_stations, key=lambda station: station["height_m"])["z_offset_m"],
    )


def _surface_sections(
    *,
    y_values: list[float],
    chord_ratios: list[float],
    area: float,
    root_x: float,
    root_z: float,
    sweep_factors: list[float],
    dihedral_deg: float,
    airfoil_id: str,
    thickness_root: float = 0.11,
) -> list[dict[str, float | str]]:
    root_chord = 0.5 * area / _trapezoid_integral(y_values, chord_ratios)
    sections = []
    for index, (y_m, ratio) in enumerate(zip(y_values, chord_ratios)):
        eta = y_m / y_values[-1] if y_values[-1] else 0.0
        sweep_factor = sweep_factors[index]
        sections.append(
            {
                "y_m": y_m,
                "leading_edge_x_m": root_x + sweep_factor * y_m,
                "leading_edge_z_m": root_z + y_m * tan(radians(dihedral_deg)),
                "chord_m": root_chord * ratio,
                "twist_deg": -0.7 * eta,
                "dihedral_deg": dihedral_deg,
                "thickness_ratio": thickness_root * (1.0 - 0.22 * eta),
                "airfoil_id": airfoil_id,
            }
        )
    return sections


def _vertical_sections(
    *,
    heights: list[float],
    chord_ratios: list[float],
    area: float,
    root_x: float,
    root_z: float,
    sweep_factors: list[float],
    airfoil_id: str = "naca0010",
) -> list[dict[str, float | str]]:
    root_chord = area / _trapezoid_integral(heights, chord_ratios)
    return [
        {
            "y_m": height,
            "leading_edge_x_m": root_x + sweep_factor * height,
            "leading_edge_z_m": root_z + height,
            "chord_m": root_chord * ratio,
            "twist_deg": 0.0,
            "dihedral_deg": 0.0,
            "thickness_ratio": 0.105 - 0.025 * height / heights[-1],
            "airfoil_id": airfoil_id,
        }
        for height, ratio, sweep_factor in zip(heights, chord_ratios, sweep_factors)
    ]


def _long_endurance_tail(
    design: ConventionalV2Design,
    body_stations: list[dict[str, float]],
) -> list[dict[str, object]]:
    _width, body_height, center_z = _body_dimensions(body_stations)
    tail_area = 0.19 * design.wing_area_m2 * design.tail_scale
    span = sqrt(tail_area * 3.15)
    semi_span = 0.5 * span
    y_values = [0.0, 0.42 * semi_span, 0.75 * semi_span, semi_span]
    return [
        {
            "id": "v_tail",
            "kind": "lifting_surface",
            "symmetry": "y",
            "orientation": "horizontal",
            "sections": _surface_sections(
                y_values=y_values,
                chord_ratios=[1.0, 0.72, 0.46, 0.26],
                area=tail_area,
                root_x=design.fuselage_length_m * design.tail_arm_ratio,
                root_z=center_z + 0.18 * body_height,
                sweep_factors=[0.0, 0.30, 0.43, 0.55],
                dihedral_deg=38.0,
                airfoil_id="naca0010_vtail",
                thickness_root=0.105,
            ),
        }
    ]


def _fast_cruise_tail(
    design: ConventionalV2Design,
    body_stations: list[dict[str, float]],
) -> list[dict[str, object]]:
    _width, body_height, center_z = _body_dimensions(body_stations)
    fin_area = 0.105 * design.wing_area_m2 * design.tail_scale
    fin_height = sqrt(fin_area * 1.85)
    fin_root_x = design.fuselage_length_m * (design.tail_arm_ratio - 0.045)
    fin_root_z = center_z + 0.42 * body_height
    fin = {
        "id": "swept_fin",
        "kind": "lifting_surface",
        "symmetry": "none",
        "orientation": "vertical",
        "sections": _vertical_sections(
            heights=[0.0, 0.34 * fin_height, 0.68 * fin_height, fin_height],
            chord_ratios=[1.0, 0.78, 0.49, 0.20],
            area=fin_area,
            root_x=fin_root_x,
            root_z=fin_root_z,
            sweep_factors=[0.0, 0.26, 0.40, 0.52],
            airfoil_id="naca0009_fast_fin",
        ),
    }
    tail_area = 0.17 * design.wing_area_m2 * design.tail_scale
    span = sqrt(tail_area * 4.35)
    semi_span = 0.5 * span
    tailplane = {
        "id": "t_tailplane",
        "kind": "lifting_surface",
        "symmetry": "y",
        "orientation": "horizontal",
        "sections": _surface_sections(
            y_values=[0.0, 0.30 * semi_span, 0.66 * semi_span, semi_span],
            chord_ratios=[1.0, 0.82, 0.50, 0.24],
            area=tail_area,
            root_x=design.fuselage_length_m * design.tail_arm_ratio,
            root_z=fin_root_z + 0.86 * fin_height,
            sweep_factors=[0.0, 0.20, 0.36, 0.50],
            dihedral_deg=1.0,
            airfoil_id="naca0009_ttail",
            thickness_root=0.095,
        ),
    }
    return [fin, tailplane]


def _payload_utility_tail(
    design: ConventionalV2Design,
    body_stations: list[dict[str, float]],
) -> list[dict[str, object]]:
    _width, body_height, center_z = _body_dimensions(body_stations)
    tail_area = 0.23 * design.wing_area_m2 * design.tail_scale
    span = sqrt(tail_area * 3.65)
    semi_span = 0.5 * span
    root_x = design.fuselage_length_m * design.tail_arm_ratio
    tailplane = {
        "id": "utility_tailplane",
        "kind": "lifting_surface",
        "symmetry": "y",
        "orientation": "horizontal",
        "sections": _surface_sections(
            y_values=[0.0, 0.24 * semi_span, 0.58 * semi_span, semi_span],
            chord_ratios=[1.0, 0.92, 0.66, 0.38],
            area=tail_area,
            root_x=root_x,
            root_z=center_z + 0.05 * body_height,
            sweep_factors=[0.0, 0.05, 0.12, 0.20],
            dihedral_deg=2.5,
            airfoil_id="naca0012_utility_tail",
            thickness_root=0.12,
        ),
    }
    fin_area = 0.125 * design.wing_area_m2 * design.tail_scale
    fin_height = sqrt(fin_area * 1.28)
    utility_fin = {
        "id": "utility_fin",
        "kind": "lifting_surface",
        "symmetry": "none",
        "orientation": "vertical",
        "sections": _vertical_sections(
            heights=[0.0, 0.28 * fin_height, 0.62 * fin_height, fin_height],
            chord_ratios=[1.0, 0.90, 0.63, 0.34],
            area=fin_area,
            root_x=root_x - 0.04 * design.fuselage_length_m,
            root_z=center_z + 0.38 * body_height,
            sweep_factors=[0.0, 0.10, 0.18, 0.27],
            airfoil_id="naca0012_utility_fin",
        ),
    }
    return [tailplane, utility_fin]


def _tail_components(
    design: ConventionalV2Design,
    preset_id: str,
    body_stations: list[dict[str, float]],
) -> list[dict[str, object]]:
    if preset_id == "long_endurance_uav":
        return _long_endurance_tail(design, body_stations)
    if preset_id == "fast_cruise_recon":
        return _fast_cruise_tail(design, body_stations)
    return _payload_utility_tail(design, body_stations)


def _interpolate_wing_value(
    sections: list[dict[str, float | str]],
    y_m: float,
    key: str,
) -> float:
    for before, after in pairwise(sections):
        before_y = float(before["y_m"])
        after_y = float(after["y_m"])
        if y_m <= after_y:
            fraction = (y_m - before_y) / (after_y - before_y)
            return float(before[key]) + fraction * (float(after[key]) - float(before[key]))
    return float(sections[-1][key])


def _nacelle_component(
    design: ConventionalV2Design,
    preset_id: str,
    wing_sections: list[dict[str, float | str]],
    body_stations: list[dict[str, float]],
) -> dict[str, object]:
    layout = PRESET_PROPULSION[preset_id]
    length = design.fuselage_length_m
    maximum_width, maximum_height, _center_z = _body_dimensions(body_stations)
    if layout == "rear_pusher":
        nacelle_length = 0.15 * length
        start_x = 0.90 * length
        centerline_y = 0.0
        center_z = body_stations[-2]["z_offset_m"]
        symmetry = "none"
        maximum_radius = 0.18 * maximum_width
        fractions = (0.0, 0.12, 0.32, 0.62, 0.84, 1.0)
        radii = (0.0, 0.72, 1.0, 0.92, 0.58, 0.0)
    elif layout == "nose_tractor":
        nacelle_length = 0.22 * length
        start_x = -0.085 * length
        centerline_y = 0.0
        center_z = body_stations[2]["z_offset_m"]
        symmetry = "none"
        maximum_radius = 0.34 * maximum_width
        fractions = (0.0, 0.10, 0.25, 0.52, 0.78, 1.0)
        radii = (0.0, 0.58, 0.96, 1.0, 0.72, 0.0)
    else:
        nacelle_length = 0.20 * length
        centerline_y = 0.28 * design.wing_span_m
        wing_x = _interpolate_wing_value(
            wing_sections, centerline_y, "leading_edge_x_m"
        )
        wing_chord = _interpolate_wing_value(wing_sections, centerline_y, "chord_m")
        wing_z = _interpolate_wing_value(
            wing_sections, centerline_y, "leading_edge_z_m"
        )
        start_x = wing_x - 0.25 * nacelle_length
        center_z = wing_z - 0.30 * maximum_height
        symmetry = "y"
        maximum_radius = 0.24 * maximum_width
        fractions = (0.0, 0.10, 0.28, 0.58, 0.82, 1.0)
        radii = (0.0, 0.62, 1.0, 0.96, 0.66, 0.0)
        start_x += 0.12 * wing_chord
    return {
        "id": f"propulsion_{layout}",
        "kind": "nacelle",
        "symmetry": symmetry,
        "centerline_y_m": centerline_y,
        "stations": [
            {
                "x_m": start_x + fraction * nacelle_length,
                "radius_y_m": maximum_radius * radius,
                "radius_z_m": (0.92 if layout != "twin_wing_mounted" else 1.12)
                * maximum_radius
                * radius,
                "z_offset_m": center_z,
            }
            for fraction, radius in zip(fractions, radii)
        ],
    }


def _closed_loft_feature(
    *,
    component_id: str,
    start_x: float,
    end_x: float,
    maximum_width: float,
    maximum_height: float,
    center_z: float,
    shape_exponent: float,
) -> dict[str, object]:
    fractions = (0.0, 0.18, 0.44, 0.72, 1.0)
    scales = (0.0, 0.72, 1.0, 0.76, 0.0)
    return {
        "id": component_id,
        "kind": "loft_body",
        "stations": [
            {
                "x_m": start_x + fraction * (end_x - start_x),
                "width_m": maximum_width * scale,
                "height_m": maximum_height * scale,
                "z_offset_m": center_z,
                "shape_exponent": shape_exponent,
            }
            for fraction, scale in zip(fractions, scales)
        ],
    }


def _integration_features(
    design: ConventionalV2Design,
    preset_id: str,
    body_stations: list[dict[str, float]],
    wing_sections: list[dict[str, float | str]],
) -> list[dict[str, object]]:
    maximum_width, maximum_height, center_z = _body_dimensions(body_stations)
    root = wing_sections[0]
    root_x = float(root["leading_edge_x_m"])
    root_chord = float(root["chord_m"])
    root_z = float(root["leading_edge_z_m"])
    fairing = _closed_loft_feature(
        component_id="wing_root_fairing",
        start_x=root_x - 0.10 * root_chord,
        end_x=root_x + 0.90 * root_chord,
        maximum_width=maximum_width * (1.30 if preset_id == "payload_utility" else 1.16),
        maximum_height=max(0.10, root_chord * design.wing_thickness_ratio * 0.70),
        center_z=root_z,
        shape_exponent=3.2 if preset_id == "payload_utility" else 2.5,
    )
    if preset_id == "fast_cruise_recon":
        feature = _closed_loft_feature(
            component_id="recon_canopy",
            start_x=0.19 * design.fuselage_length_m,
            end_x=0.43 * design.fuselage_length_m,
            maximum_width=0.46 * maximum_width,
            maximum_height=0.28 * maximum_height,
            center_z=center_z + 0.43 * maximum_height,
            shape_exponent=2.1,
        )
    elif preset_id == "payload_utility":
        feature = _closed_loft_feature(
            component_id="payload_crown",
            start_x=0.17 * design.fuselage_length_m,
            end_x=0.68 * design.fuselage_length_m,
            maximum_width=0.72 * maximum_width,
            maximum_height=0.18 * maximum_height,
            center_z=center_z + 0.48 * maximum_height,
            shape_exponent=3.6,
        )
    else:
        feature = _closed_loft_feature(
            component_id="sensor_blister",
            start_x=0.08 * design.fuselage_length_m,
            end_x=0.28 * design.fuselage_length_m,
            maximum_width=0.34 * maximum_width,
            maximum_height=0.24 * maximum_height,
            center_z=center_z - 0.39 * maximum_height,
            shape_exponent=2.0,
        )
    return [fairing, feature]


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


def _lifting_area(component: dict[str, object]) -> float:
    sections = component["sections"]
    assert isinstance(sections, list)
    area = _trapezoid_integral(
        [float(section["y_m"]) for section in sections],
        [float(section["chord_m"]) for section in sections],
    )
    return 2.0 * area if component["symmetry"] == "y" else area


def decode_conventional_geometry(
    design: ConventionalV2Design,
    preset_id: str,
) -> tuple[GeometryState, dict[str, float]]:
    body_stations = _body_stations(design, preset_id)
    wing_sections = _wing_sections(design, preset_id, body_stations)
    tail_components = _tail_components(design, preset_id, body_stations)
    nacelle = _nacelle_component(
        design, preset_id, wing_sections, body_stations
    )
    features = _integration_features(
        design, preset_id, body_stations, wing_sections
    )

    main_wing: dict[str, object] = {
        "id": "main_wing",
        "kind": "lifting_surface",
        "symmetry": "y",
        "orientation": "horizontal",
        "sections": wing_sections,
    }
    y_values = [float(section["y_m"]) for section in wing_sections]
    chords = [float(section["chord_m"]) for section in wing_sections]
    half_area = _trapezoid_integral(y_values, chords)
    chord_squared_integral = _trapezoid_integral(
        y_values, [chord * chord for chord in chords]
    )
    reference_area = 2.0 * half_area
    span = 2.0 * y_values[-1]
    body_volume, body_wetted_area = _body_metrics(body_stations)
    tail_area = sum(_lifting_area(component) for component in tail_components)
    wetted_area = body_wetted_area + 2.06 * reference_area + 2.02 * tail_area
    maximum_width, maximum_height, _center_z = _body_dimensions(body_stations)
    metrics = {
        "reference_area_m2": round(reference_area, 6),
        "span_m": round(span, 6),
        "semi_span_m": round(0.5 * span, 6),
        "aspect_ratio": round(span * span / reference_area, 8),
        "mean_aerodynamic_chord_m": round(chord_squared_integral / half_area, 6),
        "wetted_area_m2": round(wetted_area, 6),
        "taper_ratio": round(chords[-1] / chords[0], 8),
        "volume_proxy_m3": round(body_volume, 6),
        "fuselage_length_m": round(design.fuselage_length_m, 6),
        "fuselage_max_width_m": round(maximum_width, 6),
        "fuselage_max_height_m": round(maximum_height, 6),
        "span_length_ratio": round(span / design.fuselage_length_m, 6),
    }

    component_ids = [
        "fuselage",
        "main_wing",
        *(str(component["id"]) for component in tail_components),
        str(nacelle["id"]),
        *(str(component["id"]) for component in features),
    ]
    tail_aft = min(
        float(component["sections"][0]["leading_edge_x_m"])
        for component in tail_components
    ) > float(wing_sections[0]["leading_edge_x_m"]) + 0.42 * float(
        wing_sections[0]["chord_m"]
    )
    closed_body = (
        body_stations[0]["width_m"] == 0.0
        and body_stations[0]["height_m"] == 0.0
        and body_stations[-1]["width_m"] == 0.0
        and body_stations[-1]["height_m"] == 0.0
    )
    positive_surfaces = all(
        float(section["chord_m"]) > 0.0
        and float(section["thickness_ratio"]) > 0.03
        for component in [main_wing, *tail_components]
        for section in component["sections"]
    )
    root_z = float(wing_sections[0]["leading_edge_z_m"])
    root_attached = abs(root_z) <= maximum_height
    layout = PRESET_PROPULSION[preset_id]
    nacelle_stations = nacelle["stations"]
    assert isinstance(nacelle_stations, list)
    propulsion_mounted = (
        layout == "rear_pusher"
        and float(nacelle_stations[0]["x_m"]) < design.fuselage_length_m
        and float(nacelle_stations[-1]["x_m"]) > design.fuselage_length_m
    ) or (
        layout == "nose_tractor"
        and float(nacelle_stations[0]["x_m"]) < 0.0
        and float(nacelle_stations[-1]["x_m"]) > 0.0
    ) or (
        layout == "twin_wing_mounted"
        and nacelle["symmetry"] == "y"
        and float(nacelle["centerline_y_m"]) > 0.0
    )
    checks = [
        {
            "name": "body_station_order",
            "status": "pass" if all(
                before["x_m"] < after["x_m"]
                for before, after in pairwise(body_stations)
            ) else "fail",
            "message": "Archetype body stations strictly increase from nose to tail.",
        },
        {
            "name": "closed_body_ends",
            "status": "pass" if closed_body else "fail",
            "message": "Primary body nose and tail sections close to zero size.",
        },
        {
            "name": "positive_lifting_sections",
            "status": "pass" if positive_surfaces else "fail",
            "message": "Main-wing and tail sections have positive chord and thickness.",
        },
        {
            "name": "unique_component_ids",
            "status": "pass" if len(component_ids) == len(set(component_ids)) else "fail",
            "message": "Canonical components have unique semantic identifiers.",
        },
        {
            "name": "tail_aft_of_wing",
            "status": "pass" if tail_aft else "fail",
            "message": "Preset-defined tail roots are aft of the main-wing envelope.",
        },
        {
            "name": "wing_root_attached",
            "status": "pass" if root_attached else "fail",
            "message": "Main-wing root remains inside the primary body attachment envelope.",
        },
        {
            "name": "propulsion_mount_relationship",
            "status": "pass" if propulsion_mounted else "fail",
            "message": f"{layout} nacelle placement matches its preset installation relationship.",
        },
        {
            "name": "junction_fairings_present",
            "status": "pass" if {"wing_root_fairing"}.issubset(component_ids) else "fail",
            "message": "A dedicated wing-root fairing covers the primary junction.",
        },
    ]
    reference = PRESET_REFERENCE_BASIS[preset_id]
    state = GeometryState.model_validate(
        {
            "family_id": "conventional_v2",
            "geometry_version": GEOMETRY_DECODER_VERSION,
            "components": [
                {"id": "fuselage", "kind": "loft_body", "stations": body_stations},
                main_wing,
                *tail_components,
                nacelle,
                *features,
            ],
            "derived_metrics": metrics,
            "geometry_status": (
                "valid" if all(check["status"] == "pass" for check in checks) else "invalid"
            ),
            "geometry_checks": checks,
            "provenance": {
                "decoder_id": GEOMETRY_DECODER_ID,
                "decoder_version": GEOMETRY_DECODER_VERSION,
                "archetype_id": PRESET_ARCHETYPES[preset_id],
                "reference_basis": [str(reference["source_url"])],
                "methodology": (
                    "Preset-specific clean-room body, wing, tail and propulsion grammar "
                    "with continuous high-level modifiers and public ratio anchors only."
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
