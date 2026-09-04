from services.api.app.schemas.rapid_design import RapidFamilyManifest
from services.api.app.services.rapid_design.families.conventional_v2.presets import (
    CONVENTIONAL_V2_PRESETS,
)

CONVENTIONAL_V2_BOUNDS: dict[str, tuple[float, float, float, str, str]] = {
    "fuselage_length_m": (6.0, 20.0, 0.1, "m", "Fuselage length"),
    "fineness_ratio": (6.0, 16.0, 0.1, "-", "Fuselage fineness ratio"),
    "nose_length_ratio": (0.08, 0.28, 0.01, "-", "Nose length ratio"),
    "cabin_fullness": (0.65, 1.25, 0.01, "-", "Cabin fullness"),
    "tailcone_length_ratio": (0.20, 0.42, 0.01, "-", "Tail-cone ratio"),
    "section_ovality": (0.70, 1.30, 0.01, "-", "Section ovality"),
    "wing_span_m": (8.0, 30.0, 0.1, "m", "Wing span"),
    "wing_area_m2": (12.0, 55.0, 0.5, "m2", "Wing area"),
    "wing_root_x_ratio": (0.25, 0.50, 0.01, "-", "Wing root position"),
    "wing_vertical_ratio": (-0.25, 0.35, 0.01, "-", "Wing vertical position"),
    "wing_sweep_deg": (0.0, 35.0, 1.0, "deg", "Wing sweep"),
    "wing_taper_ratio": (0.20, 0.60, 0.01, "-", "Wing taper ratio"),
    "wing_dihedral_deg": (0.0, 9.0, 0.25, "deg", "Wing dihedral"),
    "wing_twist_tip_deg": (-6.0, 2.0, 0.25, "deg", "Wing tip twist"),
    "wing_thickness_ratio": (0.08, 0.18, 0.005, "-", "Wing thickness ratio"),
    "tail_arm_ratio": (0.65, 0.90, 0.01, "-", "Tail arm position"),
    "tail_scale": (0.65, 1.40, 0.01, "-", "Tail size scale"),
}

_CONDITION_BOUNDS = {
    "altitude_m": (0.0, 11_000.0, 100.0, "m", "Altitude", 2000.0),
    "speed_kmh": (80.0, 500.0, 5.0, "km/h", "Speed", 220.0),
    "alpha_min_deg": (-10.0, 15.0, 0.5, "deg", "Minimum angle of attack", -4.0),
    "alpha_max_deg": (-5.0, 20.0, 0.5, "deg", "Maximum angle of attack", 12.0),
    "alpha_samples": (5.0, 81.0, 1.0, "count", "Polar samples", 33.0),
}

_PRESET_METADATA = {
    "long_endurance_uav": (
        "Long-endurance UAV",
        "Slender fuselage, high aspect ratio, low sweep, long tail arm, rear pusher.",
    ),
    "fast_cruise_recon": (
        "Fast-cruise reconnaissance",
        "Pointed nose, swept thin wing, compact tail and nose tractor.",
    ),
    "payload_utility": (
        "Payload utility",
        "Full payload body, high wing, larger tail and twin wing-mounted nacelles.",
    ),
}


def conventional_v2_manifest() -> RapidFamilyManifest:
    default_design = CONVENTIONAL_V2_PRESETS["long_endurance_uav"]
    return RapidFamilyManifest.model_validate(
        {
            "family_id": "conventional_v2",
            "display_name": "Conventional V2",
            "description": "Multi-section conventional aircraft concept geometry.",
            "version": "0.1.0",
            "default_preset_id": "long_endurance_uav",
            "presets": [
                {
                    "preset_id": preset_id,
                    "label": _PRESET_METADATA[preset_id][0],
                    "description": _PRESET_METADATA[preset_id][1],
                    "design": dict(design),
                }
                for preset_id, design in CONVENTIONAL_V2_PRESETS.items()
            ],
            "design_parameters": [
                {
                    "key": key,
                    "label": label,
                    "unit": unit,
                    "minimum": minimum,
                    "maximum": maximum,
                    "step": step,
                    "default": default_design[key],
                    "group": "geometry",
                }
                for key, (minimum, maximum, step, unit, label) in CONVENTIONAL_V2_BOUNDS.items()
            ],
            "condition_parameters": [
                {
                    "key": key,
                    "label": label,
                    "unit": unit,
                    "minimum": minimum,
                    "maximum": maximum,
                    "step": step,
                    "default": default,
                    "group": "flight_condition",
                }
                for key, (minimum, maximum, step, unit, label, default) in _CONDITION_BOUNDS.items()
            ],
            "capabilities": {"geometry": True, "analyze": True, "optimize": False},
            "analysis": {
                "model_id": "clean-room-conventional-conceptual",
                "fidelity": "conceptual_low_order",
                "description": "Transparent low-order trend model for interactive comparison only.",
            },
            "optimization_status": "pending_teacher_decision",
        }
    )

