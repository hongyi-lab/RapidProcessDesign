from math import log, pi, sqrt

from services.api.app.schemas.rapid_design import RapidDesignConfig
from services.api.app.services.rapid_design.model_adapter import AerodynamicModelAdapter

GRAVITY_M_S2 = 9.80665


def isa_density_and_viscosity(altitude_m: float) -> tuple[float, float]:
    altitude = max(0.0, min(11_000.0, altitude_m))
    temperature = 288.15 - 0.0065 * altitude
    pressure = 101_325.0 * (temperature / 288.15) ** 5.25588
    density = pressure / (287.05 * temperature)
    viscosity = 1.716e-5 * (temperature / 273.15) ** 1.5 * (273.15 + 110.4) / (temperature + 110.4)
    return density, viscosity


def _constraint(
    name: str,
    label: str,
    value: float,
    limit: float,
    margin: float,
    unit: str,
    relation: str,
) -> dict[str, object]:
    return {
        "name": name,
        "label": label,
        "value": round(value, 5),
        "limit": round(limit, 5),
        "margin": round(margin, 5),
        "unit": unit,
        "relation": relation,
        "satisfied": margin >= 0.0,
    }


def evaluate_design(
    design: dict[str, float],
    inputs: dict[str, float],
    config: RapidDesignConfig,
    model: AerodynamicModelAdapter,
) -> dict[str, object]:
    area = design["wing_area_m2"]
    aspect_ratio = design["aspect_ratio"]
    taper = design["taper_ratio"]
    sweep = design["sweep_deg"]
    fuselage_length = design["fuselage_length_m"]
    fuselage_diameter = design["fuselage_diameter_m"]
    fuel_mass = design["fuel_mass_kg"]
    payload = inputs["payload_mass_kg"]

    span = sqrt(area * aspect_ratio)
    root_chord = 2.0 * area / (span * (1.0 + taper))
    tip_chord = taper * root_chord
    mean_chord = area / span
    fuselage_wetted_area = pi * fuselage_diameter * fuselage_length * 0.88

    mass = config.mass_model
    wing_mass = (
        mass.wing_areal_density_kg_m2 * area
        + mass.wing_span_penalty_kg_m * span
        + 0.28 * sweep * area / 10.0
    )
    fuselage_mass = mass.fuselage_shell_density_kg_m2 * fuselage_wetted_area
    systems_mass = mass.systems_base_mass_kg + mass.systems_payload_fraction * payload
    empty_without_gear = wing_mass + fuselage_mass + systems_mass + mass.propulsion_base_mass_kg
    takeoff_mass = (empty_without_gear + payload + fuel_mass) / (1.0 - mass.landing_gear_fraction)
    landing_gear_mass = mass.landing_gear_fraction * takeoff_mass
    empty_mass = empty_without_gear + landing_gear_mass

    speed_m_s = inputs["cruise_speed_kmh"] / 3.6
    density, viscosity = isa_density_and_viscosity(inputs["cruise_altitude_m"])
    dynamic_pressure = 0.5 * density * speed_m_s**2
    required_cl = takeoff_mass * GRAVITY_M_S2 / max(dynamic_pressure * area, 1e-6)
    reynolds_number = density * speed_m_s * mean_chord / viscosity
    airfoil = model.evaluate(
        camber=design["airfoil_camber"],
        camber_position=design["airfoil_camber_position"],
        thickness=design["airfoil_thickness"],
        reynolds_number=reynolds_number,
        required_lift_coefficient=required_cl,
    )

    body_drag = 0.0055 + 0.0014 * fuselage_wetted_area / area
    sweep_drag = 0.000018 * sweep**2
    induced_drag = required_cl**2 / (pi * aspect_ratio * config.aerodynamics.oswald_efficiency)
    total_cd = airfoil.profile_drag_coefficient + body_drag + sweep_drag + induced_drag
    lift_to_drag = required_cl / max(total_cd, 1e-8)

    usable_fuel = fuel_mass * (1.0 - config.aerodynamics.reserve_fuel_fraction)
    final_mass = max(takeoff_mass - usable_fuel, empty_mass + payload)
    achieved_range_m = (
        speed_m_s
        / config.aerodynamics.equivalent_tsfc_per_second
        * lift_to_drag
        * log(takeoff_mass / final_mass)
    )
    achieved_range_km = achieved_range_m / 1000.0

    constraints = [
        _constraint(
            "range",
            "航程",
            achieved_range_km,
            inputs["required_range_km"],
            achieved_range_km - inputs["required_range_km"],
            "km",
            ">=",
        ),
        _constraint(
            "lift_to_drag",
            "升阻比 L/D",
            lift_to_drag,
            inputs["target_lift_to_drag"],
            lift_to_drag - inputs["target_lift_to_drag"],
            "-",
            ">=",
        ),
        _constraint(
            "takeoff_mass",
            "起飞质量",
            takeoff_mass,
            inputs["max_takeoff_mass_kg"],
            inputs["max_takeoff_mass_kg"] - takeoff_mass,
            "kg",
            "<=",
        ),
        _constraint(
            "fuel_mass",
            "燃油质量",
            fuel_mass,
            inputs["max_fuel_mass_kg"],
            inputs["max_fuel_mass_kg"] - fuel_mass,
            "kg",
            "<=",
        ),
        _constraint(
            "lift_capacity",
            "巡航升力能力",
            required_cl,
            airfoil.max_lift_coefficient,
            airfoil.max_lift_coefficient - required_cl,
            "CL",
            "<=",
        ),
        _constraint(
            "surrogate_confidence",
            "代理模型置信度",
            airfoil.analysis_confidence,
            config.aerodynamics.min_analysis_confidence,
            airfoil.analysis_confidence - config.aerodynamics.min_analysis_confidence,
            "-",
            ">=",
        ),
    ]
    feasible = all(bool(item["satisfied"]) for item in constraints)
    normalizers = {
        "range": max(inputs["required_range_km"], 1.0),
        "lift_to_drag": max(inputs["target_lift_to_drag"], 1.0),
        "takeoff_mass": max(inputs["max_takeoff_mass_kg"], 1.0),
        "fuel_mass": max(inputs["max_fuel_mass_kg"], 1.0),
        "lift_capacity": max(airfoil.max_lift_coefficient, 0.2),
        "surrogate_confidence": max(config.aerodynamics.min_analysis_confidence, 0.1),
    }
    violation = sum(
        (min(0.0, float(item["margin"])) / normalizers[str(item["name"])]) ** 2
        for item in constraints
    )
    objective = takeoff_mass / inputs["max_takeoff_mass_kg"] + 1500.0 * violation

    return {
        "feasible": feasible,
        "objective": float(objective),
        "constraint_violation": float(violation),
        "design": {key: float(value) for key, value in design.items()},
        "metrics": {
            "takeoff_mass_kg": takeoff_mass,
            "empty_mass_kg": empty_mass,
            "fuel_mass_kg": fuel_mass,
            "achieved_range_km": achieved_range_km,
            "lift_to_drag": lift_to_drag,
            "cruise_lift_coefficient": required_cl,
            "total_drag_coefficient": total_cd,
            "profile_drag_coefficient": airfoil.profile_drag_coefficient,
            "induced_drag_coefficient": induced_drag,
            "angle_of_attack_deg": airfoil.alpha_deg,
            "pitching_moment_coefficient": airfoil.moment_coefficient,
            "analysis_confidence": airfoil.analysis_confidence,
            "reynolds_number": airfoil.reynolds_number,
            "span_m": span,
            "root_chord_m": root_chord,
            "tip_chord_m": tip_chord,
        },
        "mass_breakdown_kg": {
            "wing": wing_mass,
            "fuselage": fuselage_mass,
            "systems": systems_mass,
            "propulsion": mass.propulsion_base_mass_kg,
            "landing_gear": landing_gear_mass,
            "payload": payload,
            "fuel": fuel_mass,
        },
        "constraints": constraints,
    }
