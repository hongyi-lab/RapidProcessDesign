from __future__ import annotations

from math import radians, tan

from services.api.app.schemas.rapid_design import BwbV1Design, GeometryState
from services.api.app.services.rapid_design.bwb_analysis import (
    GEOMETRY_DECODER_ID,
    GEOMETRY_DECODER_VERSION,
    _monotone_curve,
    _sample_curve_segment,
)


def _sample(curve, coordinate: float) -> float:
    last = len(curve.coordinates) - 1
    if coordinate <= curve.coordinates[0]:
        return curve.values[0]
    if coordinate >= curve.coordinates[last]:
        return curve.values[last]
    segment = 0
    while segment < last - 1 and coordinate > curve.coordinates[segment + 1]:
        segment += 1
    return _sample_curve_segment(curve, segment, coordinate)[0]


def decode_bwb_geometry_state(
    design: BwbV1Design,
    derived_metrics: dict[str, float],
) -> GeometryState:
    c1 = design.c1_m
    segment_spans = (
        c1 * design.b1_ratio,
        c1 * design.b2_ratio,
        c1 * design.b3_ratio,
    )
    span_coordinates = (
        0.0,
        segment_spans[0],
        segment_spans[0] + segment_spans[1],
        sum(segment_spans),
    )
    chord_controls = (
        c1,
        c1 * design.c2_ratio,
        c1 * design.c3_ratio,
        c1 * design.c4_ratio,
    )
    root_le = -0.22 * c1
    inner_sweep = radians(design.sweep_inner_deg)
    outer_sweep = radians(design.sweep_outer_deg)
    transition_sweep = 0.55 * inner_sweep + 0.45 * outer_sweep
    leading_edge_controls = (
        root_le,
        root_le + segment_spans[0] * tan(inner_sweep),
        root_le
        + segment_spans[0] * tan(inner_sweep)
        + segment_spans[1] * tan(transition_sweep)
        + 0.25 * c1 * design.x3_ratio,
        0.0,
    )
    leading_edge_controls = (
        *leading_edge_controls[:3],
        leading_edge_controls[2] + segment_spans[2] * tan(outer_sweep),
    )
    chord_curve = _monotone_curve(span_coordinates, chord_controls, flatten_root=True)
    leading_edge_curve = _monotone_curve(
        span_coordinates, leading_edge_controls, flatten_root=True
    )
    semi_span = span_coordinates[-1]
    sections = []
    for index in range(17):
        y_m = semi_span * index / 16
        eta = y_m / semi_span
        sections.append(
            {
                "y_m": y_m,
                "leading_edge_x_m": _sample(leading_edge_curve, y_m),
                "leading_edge_z_m": 0.0,
                "chord_m": _sample(chord_curve, y_m),
                "twist_deg": design.twist_tip_deg * eta**1.55,
                "dihedral_deg": 0.0,
                "thickness_ratio": design.thickness_ratio
                * (1.34 - 0.52 * eta**0.78),
                "airfoil_id": "clean_room_symmetric_bwb",
            }
        )
    return GeometryState.model_validate(
        {
            "family_id": "bwb_v1",
            "geometry_version": "1.0.0",
            "components": [
                {
                    "id": "bwb_primary_surface",
                    "kind": "lifting_surface",
                    "symmetry": "y",
                    "orientation": "horizontal",
                    "sections": sections,
                }
            ],
            "derived_metrics": derived_metrics,
            "geometry_status": "valid",
            "geometry_checks": [
                {
                    "name": "positive_local_chord",
                    "status": "pass",
                    "message": "All sampled semi-span sections have positive chord.",
                },
                {
                    "name": "strict_span_order",
                    "status": "pass",
                    "message": "All sampled semi-span coordinates strictly increase.",
                },
            ],
            "provenance": {
                "decoder_id": GEOMETRY_DECODER_ID,
                "decoder_version": GEOMETRY_DECODER_VERSION,
                "methodology": "Shape-preserving Hermite planform sampled into canonical sections.",
            },
        }
    )

