"""Steady, level, constant-speed/altitude propeller cruise with fuel burn.

Three mass stations are trimmed with the same aerodynamic model as Analyze.
Climb, descent, wind, fuel-CG migration and propeller/engine maps are not modeled.
"""

from __future__ import annotations

from math import isfinite

from services.api.app.schemas.rapid_design import GeometryState
from services.api.app.services.rapid_design.families.conventional_v2.aerodynamics import (
    AircraftAerodynamics,
)


def integrate_range_km(*, usable_fuel_kg, speed_kmh, shaft_powers_kw, bsfc_kg_per_kwh):
    """Simpson integration of V / fuel_flow over mass, with explicit kW/hour units."""
    if len(shaft_powers_kw) != 3:
        raise ValueError("cruise integration requires start, midpoint and end power")
    if not all(isfinite(p) and p > 0 for p in shaft_powers_kw):
        raise ValueError("cruise shaft powers must be finite and positive")
    distance_per_kg = [speed_kmh / (bsfc_kg_per_kwh * p) for p in shaft_powers_kw]
    return usable_fuel_kg / 6 * (
        distance_per_kg[0] + 4 * distance_per_kg[1] + distance_per_kg[2]
    )


def evaluate_cruise(*, geometry_state, condition, model, inputs, takeoff_mass_kg,
                    final_mass_kg, propulsion_count, polar, max_ld):
    aircraft = AircraftAerodynamics(GeometryState.model_validate(geometry_state), condition)
    cg_fraction = inputs.get("cg_percent_mac", 25.0) / 100
    points = aircraft.trim(
        [takeoff_mass_kg, (takeoff_mass_kg + final_mass_kg) / 2, final_mass_kg],
        cg_mac_fraction=cg_fraction, elevator_limit_deg=model.elevator_limit_deg,
    )
    density = float(aircraft.atmosphere.density())
    available_power = (
        inputs.get("shaft_power_per_engine_kw", 180.0) * propulsion_count
        * model.continuous_power_fraction * (density / 1.225)**model.power_lapse_exponent
    )
    for point in points:
        point["shaft_power_required_kw"] = (
            point["drag_n"] * (condition.speed_kmh / 3.6) / (model.propeller_efficiency * 1000)
        )
        point["fuel_flow_kg_h"] = point["shaft_power_required_kw"] * model.bsfc_kg_per_kwh
    trim_ok = all(point["status"] == "supported" for point in points)
    minimum_margin = min(point["static_margin"] for point in points)
    stability_ok = trim_ok and minimum_margin >= model.minimum_static_margin
    required_power = max(point["shaft_power_required_kw"] for point in points)
    power_ok = required_power <= available_power
    supported = trim_ok and stability_ok and power_ok
    reason = next((point["reason_code"] for point in points if point["status"] != "supported"),
                  "static_margin_not_supported" if not stability_ok
                  else "insufficient_power" if not power_ok else "matched")
    achieved_range = integrate_range_km(
        usable_fuel_kg=takeoff_mass_kg - final_mass_kg, speed_kmh=condition.speed_kmh,
        shaft_powers_kw=[point["shaft_power_required_kw"] for point in points],
        bsfc_kg_per_kwh=model.bsfc_kg_per_kwh,
    ) if supported else 0.0
    start = points[0]
    matched = {**start, "method": "bounded_neuralfoil_aerosandbox_trim", "bracket_indices": []}
    diagnostic = {
        "status": "supported" if supported else "unsupported", "reason_code": reason,
        "reference_state": {
            "mass_basis": "mission_demo_takeoff_mass", "mass_kg": takeoff_mass_kg,
            "altitude_m": condition.altitude_m, "speed_kmh": condition.speed_kmh,
            "density_kg_m3": density,
            "dynamic_pressure_pa": 0.5 * density * (condition.speed_kmh / 3.6)**2,
            "reference_area_m2": aircraft.area,
        },
        "required_cl": start["required_cl"],
        "polar_support": {
            "min_cl": min(polar["cl"]), "max_cl": max(polar["cl"]),
            "alpha_min_deg": condition.alpha_min_deg, "alpha_max_deg": condition.alpha_max_deg,
            "sample_count": len(polar["cl"]),
        },
        "matched_working_point": matched if start["status"] == "supported" else None,
        "comparison": {
            "max_ld": max_ld,
            "ld_at_reference_state": start["ld"] if start["status"] == "supported" else None,
            # Compatibility field: representative midpoint, not a constant used in integration.
            "range_model_ld": points[1]["ld"] if supported else 0.0,
        },
        "checks": {
            "trim": trim_ok, "static_margin": stability_ok, "power": power_ok,
            "minimum_static_margin": minimum_margin,
            "required_static_margin": model.minimum_static_margin,
            "shaft_power_available_kw": available_power,
            "shaft_power_required_kw": required_power,
        },
        "assumptions": {
            "cg_percent_mac": cg_fraction * 100,
            "cg_x_m": float(aircraft.reference[0]) + (cg_fraction - 0.25) * aircraft.chord,
            "elevator_hinge_fraction": 0.75, "elevator_limit_deg": model.elevator_limit_deg,
            "shaft_power_per_engine_kw": inputs.get("shaft_power_per_engine_kw", 180.0),
            "propeller_efficiency": model.propeller_efficiency,
            "bsfc_kg_per_kwh": model.bsfc_kg_per_kwh,
            "continuous_power_fraction": model.continuous_power_fraction,
            "power_lapse_exponent": model.power_lapse_exponent,
        },
        "mass_stations": points,
        "integration_method": "three_mass_station_simpson_fuel_flow",
        "enters_score": True, "enters_range_estimate": True,
        "scope": "Steady level cruise with three fuel-mass trim states, fixed assumed CG, "
                 "constant propeller efficiency/BSFC and density-lapsed shaft power. "
                 "No climb, descent, propwash, thrust-line moment or engine map is modeled. "
                 "Unsupported cruise has no range estimate.",
    }
    metrics = {
        "cruise_lift_to_drag": points[1]["ld"] if trim_ok else 0.0,
        "minimum_cruise_lift_to_drag": min(point["ld"] for point in points) if trim_ok else 0.0,
        "achieved_range_km": achieved_range,
        "cruise_trim_supported": float(trim_ok), "cruise_supported": float(supported),
        "minimum_static_margin": minimum_margin,
        "shaft_power_required_kw": required_power, "shaft_power_available_kw": available_power,
        "power_margin_kw": available_power - required_power,
    }
    return diagnostic, metrics
