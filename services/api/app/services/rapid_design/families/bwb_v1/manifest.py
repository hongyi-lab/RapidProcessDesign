from services.api.app.schemas.rapid_design import (
    BWB_V1_CONDITION_BOUNDS,
    BWB_V1_DESIGN_BOUNDS,
    RapidFamilyManifest,
)
from services.api.app.services.rapid_design.families.bwb_v1.presets import (
    DEFAULT_BWB_DESIGN,
)

_DESIGN_LABELS = {
    "c1_m": "Root chord",
    "c2_ratio": "Inner chord ratio",
    "c3_ratio": "Outer-kink chord ratio",
    "c4_ratio": "Tip chord ratio",
    "b1_ratio": "Inner span ratio",
    "b2_ratio": "Middle span ratio",
    "b3_ratio": "Outer span ratio",
    "x3_ratio": "Kink offset ratio",
    "sweep_inner_deg": "Inner sweep",
    "sweep_outer_deg": "Outer sweep",
    "thickness_ratio": "Reference thickness ratio",
    "twist_tip_deg": "Tip twist",
}

_DESIGN_STEPS = {
    "c1_m": 0.1,
    "sweep_inner_deg": 1.0,
    "sweep_outer_deg": 1.0,
    "twist_tip_deg": 0.25,
}

_CONDITION_DEFAULTS = {
    "altitude_m": 2000.0,
    "speed_kmh": 220.0,
    "alpha_min_deg": -4.0,
    "alpha_max_deg": 12.0,
    "alpha_samples": 33.0,
}

_CONDITION_LABELS = {
    "altitude_m": "Altitude",
    "speed_kmh": "Speed",
    "alpha_min_deg": "Minimum angle of attack",
    "alpha_max_deg": "Maximum angle of attack",
    "alpha_samples": "Polar samples",
}


def bwb_v1_manifest() -> RapidFamilyManifest:
    return RapidFamilyManifest.model_validate(
        {
            "family_id": "bwb_v1",
            "display_name": "Blended Wing Body V1",
            "description": "Smooth clean-room blended-wing-body concept family.",
            "version": "1.1.0",
            "default_preset_id": "balanced_concept",
            "presets": [
                {
                    "preset_id": "balanced_concept",
                    "label": "Balanced concept",
                    "description": "Released BWB baseline migrated to GeometryState.",
                    "design": dict(DEFAULT_BWB_DESIGN),
                }
            ],
            "design_parameters": [
                {
                    "key": key,
                    "label": _DESIGN_LABELS[key],
                    "unit": unit,
                    "minimum": minimum,
                    "maximum": maximum,
                    "step": _DESIGN_STEPS.get(key, 0.01),
                    "default": DEFAULT_BWB_DESIGN[key],
                    "group": "geometry",
                }
                for key, (minimum, maximum, unit) in BWB_V1_DESIGN_BOUNDS.items()
            ],
            "condition_parameters": [
                {
                    "key": key,
                    "label": _CONDITION_LABELS[key],
                    "unit": unit,
                    "minimum": minimum,
                    "maximum": maximum,
                    "step": 1.0 if key == "alpha_samples" else (100.0 if key == "altitude_m" else 1.0),
                    "default": _CONDITION_DEFAULTS[key],
                    "group": "flight_condition",
                }
                for key, (minimum, maximum, unit) in BWB_V1_CONDITION_BOUNDS.items()
            ],
            "capabilities": {"geometry": True, "analyze": True, "optimize": False},
            "analysis": {
                "model_id": "clean-room-bwb-low-order",
                "fidelity": "conceptual_low_order",
                "description": "Deterministic conceptual whole-aircraft longitudinal polar.",
            },
            "optimization_status": "pending_teacher_decision",
        }
    )

