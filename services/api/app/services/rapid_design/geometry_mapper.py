from services.api.app.schemas.aircraft_spec import AircraftSpec


def _numeric(value: float, unit: str, reason: str) -> dict[str, object]:
    return {
        "value": round(float(value), 5),
        "unit": unit,
        "source": "inferred",
        "confidence": 0.76,
        "reason": reason,
    }


def _text(value: str, reason: str, confidence: float = 0.76) -> dict[str, object]:
    return {
        "value": value,
        "source": "inferred",
        "confidence": confidence,
        "reason": reason,
    }


def _naca_label(design: dict[str, float]) -> str:
    camber = max(0, min(9, round(design["airfoil_camber"] * 100)))
    position = max(0, min(9, round(design["airfoil_camber_position"] * 10)))
    thickness = max(1, min(99, round(design["airfoil_thickness"] * 100)))
    return f"NACA{camber}{position}{thickness:02d}"


def aircraft_spec_from_result(
    job_id: str,
    inputs: dict[str, float],
    evaluation: dict[str, object],
) -> dict[str, object]:
    design = evaluation["design"]
    metrics = evaluation["metrics"]
    assert isinstance(design, dict)
    assert isinstance(metrics, dict)
    spec = {
        "schema_version": "0.1",
        "aircraft": {
            "name": f"rapid-design-{job_id[:8]}",
            "type": "fixed_wing_uav",
            "layout": "conventional",
        },
        "mission": {
            "cruise_speed": {
                "value": float(inputs["cruise_speed_kmh"]),
                "unit": "km/h",
                "source": "user",
                "confidence": 1.0,
                "source_text": "Rapid Design adjustable mission input",
            },
            "payload": {
                "value": float(inputs["payload_mass_kg"]),
                "unit": "kg",
                "source": "user",
                "confidence": 1.0,
                "source_text": "Rapid Design adjustable mission input",
            },
            "priority": _text("minimum_mass_feasible_design", "Rapid Design objective"),
        },
        "fuselage": {
            "length": _numeric(design["fuselage_length_m"], "m", "optimizer output"),
            "max_diameter": _numeric(design["fuselage_diameter_m"], "m", "optimizer output"),
        },
        "wing": {
            "position": _text("high", "baseline conventional UAV arrangement"),
            "span": _numeric(metrics["span_m"], "m", "derived from area and aspect ratio"),
            "root_chord": _numeric(metrics["root_chord_m"], "m", "derived trapezoidal planform"),
            "tip_chord": _numeric(metrics["tip_chord_m"], "m", "derived trapezoidal planform"),
            "sweep": _numeric(design["sweep_deg"], "deg", "optimizer output"),
            "dihedral": _numeric(3.0, "deg", "conventional UAV visualization default"),
            "airfoil": _text(_naca_label(design), "optimized NACA four-digit parameters"),
            "sections": {
                "value": 5,
                "source": "system_default",
                "confidence": 0.8,
                "reason": "preview geometry discretization",
            },
            "planform": _text("tapered", "optimizer uses a trapezoidal wing"),
        },
        "tail": {"type": _text("conventional", "V0 optimization scope")},
        "engine": {
            "count": {
                "value": 1,
                "source": "system_default",
                "confidence": 0.7,
                "reason": "single-engine V0 concept",
            },
            "position": _text("nose", "single-engine V0 concept"),
        },
    }
    return AircraftSpec.model_validate(spec).model_dump(mode="json")
