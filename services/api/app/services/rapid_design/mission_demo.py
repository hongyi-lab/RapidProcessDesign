from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from math import isfinite, log, sqrt
from random import Random
from time import perf_counter
from typing import Any

from pydantic import ValidationError

from services.api.app.schemas.rapid_design import (
    BwbAnalysisCondition,
    MissionDemoProfile,
    MissionDemoVariableDefinition,
    RapidAnalyzeRequest,
)
from services.api.app.services.rapid_design.config_loader import (
    mission_demo_profile_hash,
    validated_mission_demo_inputs,
)
from services.api.app.services.rapid_design.evaluator import isa_density_and_viscosity
from services.api.app.services.rapid_design.families.registry import FamilyRegistry, registry

GRAVITY_M_S2 = 9.80665
DEMO_MODEL_ID = "mission-demo-transparent-mass-breguet"
DEMO_MODEL_VERSION = "1.1.0"

ProgressCallback = Callable[[int, int, dict[str, object]], None]
CancelCheck = Callable[[], bool]


class MissionDemoRequestError(ValueError):
    def __init__(self, code: str, message: str, *, field: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field

    def detail(self) -> dict[str, str]:
        detail = {"code": self.code, "message": self.message}
        if self.field is not None:
            detail["field"] = self.field
        return detail


def _rounded(value: float, digits: int = 10) -> float:
    rounded = round(float(value), digits)
    return 0.0 if rounded == 0 else rounded


def _stable_hash(payload: object) -> str:
    canonical = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _preset_design(
    *, family_registry: FamilyRegistry, family_id: str, preset_id: str
) -> dict[str, float]:
    if family_id != "conventional_v2":
        raise MissionDemoRequestError(
            "unsupported_family",
            "Mission Demo v1 supports only conventional_v2; no family conversion is performed.",
            field="family_id",
        )
    manifest = family_registry.manifest("conventional_v2")
    for preset in manifest.presets:
        if preset.preset_id == preset_id:
            return dict(preset.design)
    raise MissionDemoRequestError(
        "unknown_preset",
        f"unknown conventional_v2 preset: {preset_id}",
        field="preset_id",
    )


def validate_mission_demo_submission(
    *,
    profile: MissionDemoProfile,
    family_id: str,
    preset_id: str,
    supplied_inputs: dict[str, float],
    family_registry: FamilyRegistry = registry,
) -> dict[str, float]:
    _preset_design(
        family_registry=family_registry,
        family_id=family_id,
        preset_id=preset_id,
    )
    try:
        return validated_mission_demo_inputs(profile, supplied_inputs)
    except ValueError as exc:
        raise MissionDemoRequestError(
            "invalid_inputs",
            str(exc),
            field="inputs",
        ) from exc


def _condition(profile: MissionDemoProfile, inputs: dict[str, float]) -> BwbAnalysisCondition:
    model = profile.mission_model
    return BwbAnalysisCondition(
        altitude_m=inputs["cruise_altitude_m"],
        speed_kmh=inputs["cruise_speed_kmh"],
        alpha_min_deg=model.alpha_min_deg,
        alpha_max_deg=model.alpha_max_deg,
        alpha_samples=model.alpha_samples,
    )


def _geometry_bounds_are_native(
    profile: MissionDemoProfile,
    family_registry: FamilyRegistry,
) -> None:
    manifest = family_registry.manifest("conventional_v2")
    definitions = {item.key: item for item in manifest.design_parameters}
    for variable in profile.geometry_variables:
        definition = definitions.get(variable.key)
        if definition is None:
            raise RuntimeError(
                f"mission demo profile variable is not native to conventional_v2: {variable.key}"
            )
        if (
            variable.minimum < definition.minimum
            or variable.maximum > definition.maximum
        ):
            raise RuntimeError(
                f"mission demo profile range exceeds the family range: {variable.key}"
            )


def _effective_bounds(
    variable: MissionDemoVariableDefinition,
    inputs: dict[str, float],
) -> tuple[float, float]:
    maximum = variable.maximum
    if variable.input_upper_bound is not None:
        maximum = min(maximum, inputs[variable.input_upper_bound])
    if maximum < variable.minimum:
        raise MissionDemoRequestError(
            "empty_search_range",
            f"empty search range for {variable.key}",
            field=f"inputs.{variable.input_upper_bound}",
        )
    return variable.minimum, maximum


def _grid_value(
    random: Random,
    variable: MissionDemoVariableDefinition,
    inputs: dict[str, float],
) -> float:
    minimum, maximum = _effective_bounds(variable, inputs)
    steps = int((maximum - minimum) / variable.step + 1e-10)
    return _rounded(minimum + random.randint(0, steps) * variable.step, 12)


def _midpoint_grid_value(
    variable: MissionDemoVariableDefinition,
    inputs: dict[str, float],
) -> float:
    minimum, maximum = _effective_bounds(variable, inputs)
    steps = int((maximum - minimum) / variable.step + 1e-10)
    return _rounded(minimum + (steps // 2) * variable.step, 12)


def _boundary_grid_value(
    variable: MissionDemoVariableDefinition,
    inputs: dict[str, float],
    *,
    upper: bool,
) -> float:
    minimum, maximum = _effective_bounds(variable, inputs)
    steps = int((maximum - minimum) / variable.step + 1e-10)
    selected_step = steps if upper else 0
    return _rounded(minimum + selected_step * variable.step, 12)


def _candidate_id(
    *,
    profile: MissionDemoProfile,
    family_id: str,
    preset_id: str,
    design: dict[str, float],
    sizing: dict[str, float],
) -> str:
    digest = _stable_hash(
        {
            "profile_id": profile.profile_id,
            "profile_version": profile.profile_version,
            "profile_hash": mission_demo_profile_hash(profile),
            "family_id": family_id,
            "preset_id": preset_id,
            "design": design,
            "sizing": sizing,
        }
    )
    return f"demo-{digest[:20]}"


def _propulsion_count(components: list[dict[str, Any]]) -> int:
    count = 0
    for component in components:
        if component.get("kind") == "propeller":
            count += 2 if component.get("symmetry") == "y" else 1
    if count <= 0:
        raise ValueError("canonical geometry contains no propeller component")
    return count


def _geometry_fingerprint(
    *,
    design: dict[str, float],
    geometry_state: dict[str, object],
) -> str:
    """Hash actual geometry-defining data, never condition or provenance metadata."""

    return _stable_hash(
        {
            "family_id": geometry_state["family_id"],
            "design": {
                key: _rounded(value, 12) for key, value in design.items()
            },
            "geometry_state": {
                "components": geometry_state["components"],
                "derived_metrics": geometry_state["derived_metrics"],
            },
        }
    )


def _cruise_consistency_diagnostic(
    *,
    takeoff_mass_kg: float,
    reference_area_m2: float,
    condition: BwbAnalysisCondition,
    polar: dict[str, list[float]],
    max_ld: float,
) -> dict[str, object]:
    """Match the Demo takeoff state to the sampled polar without extrapolation."""

    density_kg_m3, _viscosity_pa_s = isa_density_and_viscosity(
        condition.altitude_m
    )
    speed_m_s = condition.speed_kmh / 3.6
    dynamic_pressure_pa = 0.5 * density_kg_m3 * speed_m_s**2
    required_cl = (
        takeoff_mass_kg
        * GRAVITY_M_S2
        / (dynamic_pressure_pa * reference_area_m2)
    )
    alphas = [float(value) for value in polar["alpha_deg"]]
    cls = [float(value) for value in polar["cl"]]
    cds = [float(value) for value in polar["cd"]]
    if not cls or not (len(alphas) == len(cls) == len(cds)):
        raise ValueError("Analyze polar is empty or has inconsistent arrays")
    if not all(isfinite(value) for value in [*alphas, *cls, *cds]):
        raise ValueError("Analyze polar contains non-finite values")

    minimum_cl = min(cls)
    maximum_cl = max(cls)
    matched: dict[str, object] | None = None
    tolerance = 1e-12
    if minimum_cl - tolerance <= required_cl <= maximum_cl + tolerance:
        for index, sampled_cl in enumerate(cls):
            if abs(required_cl - sampled_cl) <= tolerance:
                sampled_cd = cds[index]
                if sampled_cd <= 0.0:
                    raise ValueError("Analyze polar contains non-positive drag")
                matched = {
                    "alpha_deg": _rounded(alphas[index], 6),
                    "cl": _rounded(required_cl),
                    "cd": _rounded(sampled_cd),
                    "ld": _rounded(required_cl / sampled_cd),
                    "method": "exact_sample",
                    "bracket_indices": [index, index],
                }
                break
        if matched is None:
            for index in range(len(cls) - 1):
                left_cl = cls[index]
                right_cl = cls[index + 1]
                if not (
                    min(left_cl, right_cl) <= required_cl <= max(left_cl, right_cl)
                ):
                    continue
                delta_cl = right_cl - left_cl
                if abs(delta_cl) <= tolerance:
                    continue
                fraction = (required_cl - left_cl) / delta_cl
                alpha_deg = alphas[index] + fraction * (
                    alphas[index + 1] - alphas[index]
                )
                cd = cds[index] + fraction * (cds[index + 1] - cds[index])
                if cd <= 0.0:
                    raise ValueError("Analyze polar interpolation produced non-positive drag")
                matched = {
                    "alpha_deg": _rounded(alpha_deg, 6),
                    "cl": _rounded(required_cl),
                    "cd": _rounded(cd),
                    "ld": _rounded(required_cl / cd),
                    "method": "linear_interpolation_in_sampled_cl_bracket",
                    "bracket_indices": [index, index + 1],
                }
                break

    matched_ld = None if matched is None else matched["ld"]
    return {
        "status": "supported" if matched is not None else "unsupported",
        "reason_code": "matched" if matched is not None else "lift_not_supported",
        "reference_state": {
            "mass_basis": "mission_demo_takeoff_mass",
            "mass_kg": _rounded(takeoff_mass_kg),
            "altitude_m": _rounded(condition.altitude_m),
            "speed_kmh": _rounded(condition.speed_kmh),
            "density_kg_m3": _rounded(density_kg_m3),
            "dynamic_pressure_pa": _rounded(dynamic_pressure_pa),
            "reference_area_m2": _rounded(reference_area_m2),
        },
        "required_cl": _rounded(required_cl),
        "polar_support": {
            "min_cl": _rounded(minimum_cl),
            "max_cl": _rounded(maximum_cl),
            "alpha_min_deg": _rounded(min(alphas), 6),
            "alpha_max_deg": _rounded(max(alphas), 6),
            "sample_count": len(cls),
        },
        "matched_working_point": matched,
        "comparison": {
            "max_ld": _rounded(max_ld),
            "ld_at_reference_state": matched_ld,
            "range_model_ld": _rounded(max_ld),
        },
        "enters_score": False,
        "enters_range_estimate": False,
        "scope": (
            "Lift-demand consistency at the Demo takeoff-mass reference state only; "
            "not trim, stability, propulsion matching or mission integration."
        ),
    }


def _constraint(
    *,
    name: str,
    label: str,
    metric_key: str,
    actual: float,
    limit: float,
    unit: str,
    operator: str,
) -> dict[str, object]:
    if operator == ">=":
        margin = actual - limit
    elif operator == "<=":
        margin = limit - actual
    else:
        raise ValueError(f"unsupported constraint operator: {operator}")
    return {
        "name": name,
        "label": label,
        "metric_key": metric_key,
        "actual": _rounded(actual),
        "limit": _rounded(limit),
        "margin": _rounded(margin),
        "unit": unit,
        "operator": operator,
        "satisfied": margin >= 0.0,
    }


def _evaluate_candidate(
    *,
    profile: MissionDemoProfile,
    family_id: str,
    preset_id: str,
    design: dict[str, float],
    sizing: dict[str, float],
    inputs: dict[str, float],
    condition: BwbAnalysisCondition,
    family_registry: FamilyRegistry,
) -> dict[str, object]:
    analysis = family_registry.analyze(
        RapidAnalyzeRequest(
            family_id="conventional_v2",
            preset_id=preset_id,
            design=design,
            condition=condition,
        )
    )
    analysis_payload = analysis.model_dump(mode="json")
    geometry_state = analysis_payload["geometry_state"]
    if geometry_state["geometry_status"] != "valid":
        raise ValueError("candidate canonical geometry is invalid")
    geometry_metrics = analysis_payload["geometry_metrics"]
    summary = analysis_payload["analysis"]["summary"]
    polar = analysis_payload["analysis"]["polar"]
    propulsion_count = _propulsion_count(geometry_state["components"])

    model = profile.mission_model
    reference_area = float(geometry_metrics["reference_area_m2"])
    span = float(geometry_metrics["span_m"])
    wetted_area = float(geometry_metrics["wetted_area_m2"])
    lift_to_drag = float(summary["max_ld"])
    fuel_mass = float(sizing["fuel_mass_kg"])
    payload_mass = inputs["payload_mass_kg"]

    wing_mass = model.wing_areal_density_kg_m2 * reference_area
    wetted_mass = model.wetted_area_density_kg_m2 * wetted_area
    span_mass = model.wing_span_penalty_kg_m * span
    systems_mass = (
        model.systems_base_mass_kg
        + model.systems_payload_fraction * payload_mass
    )
    propulsion_mass = model.propulsion_mass_per_unit_kg * propulsion_count
    empty_without_gear = (
        wing_mass + wetted_mass + span_mass + systems_mass + propulsion_mass
    )
    takeoff_mass = (
        empty_without_gear + payload_mass + fuel_mass
    ) / (1.0 - model.landing_gear_fraction)
    landing_gear_mass = model.landing_gear_fraction * takeoff_mass
    empty_mass = empty_without_gear + landing_gear_mass
    usable_fuel = fuel_mass * (1.0 - model.reserve_fuel_fraction)
    final_mass = max(takeoff_mass - usable_fuel, empty_mass + payload_mass)
    speed_m_s = inputs["cruise_speed_kmh"] / 3.6
    achieved_range_km = (
        speed_m_s
        / model.equivalent_tsfc_per_second
        * lift_to_drag
        * log(takeoff_mass / final_mass)
        / 1000.0
    )
    domain_value = 1.0 if analysis_payload["domain_status"]["status"] == "in_domain" else 0.0

    metrics = {
        "reference_area_m2": _rounded(reference_area),
        "span_m": _rounded(span),
        "aspect_ratio": _rounded(float(geometry_metrics["aspect_ratio"])),
        "wetted_area_m2": _rounded(wetted_area),
        "max_lift_to_drag": _rounded(lift_to_drag),
        "cd0": _rounded(float(summary["cd0"])),
        "takeoff_mass_kg": _rounded(takeoff_mass),
        "empty_mass_kg": _rounded(empty_mass),
        "fuel_mass_kg": _rounded(fuel_mass),
        "achieved_range_km": _rounded(achieved_range_km),
        "propulsion_count": propulsion_count,
        "wing_mass_kg": _rounded(wing_mass),
        "wetted_area_mass_kg": _rounded(wetted_mass),
        "span_mass_kg": _rounded(span_mass),
        "systems_mass_kg": _rounded(systems_mass),
        "propulsion_mass_kg": _rounded(propulsion_mass),
        "landing_gear_mass_kg": _rounded(landing_gear_mass),
    }
    if not all(
        isfinite(float(value))
        for value in metrics.values()
        if isinstance(value, (int, float))
    ):
        raise ValueError("demo mission model produced a non-finite metric")

    constraints = [
        _constraint(
            name="range",
            label="Required range",
            metric_key="mission.achieved_range_km",
            actual=achieved_range_km,
            limit=inputs["required_range_km"],
            unit="km",
            operator=">=",
        ),
        _constraint(
            name="lift_to_drag",
            label="Target lift-to-drag ratio",
            metric_key="analysis.max_ld",
            actual=lift_to_drag,
            limit=inputs["target_lift_to_drag"],
            unit="-",
            operator=">=",
        ),
        _constraint(
            name="takeoff_mass",
            label="Maximum takeoff mass",
            metric_key="mission.takeoff_mass_kg",
            actual=takeoff_mass,
            limit=inputs["max_takeoff_mass_kg"],
            unit="kg",
            operator="<=",
        ),
        _constraint(
            name="fuel_mass",
            label="Maximum fuel mass",
            metric_key="sizing.fuel_mass_kg",
            actual=fuel_mass,
            limit=inputs["max_fuel_mass_kg"],
            unit="kg",
            operator="<=",
        ),
        _constraint(
            name="analysis_domain",
            label="Analyze declared domain",
            metric_key="mission.analysis_domain",
            actual=domain_value,
            limit=1.0,
            unit="state",
            operator=">=",
        ),
    ]
    normalizers = {
        "range": max(inputs["required_range_km"], 1.0),
        "lift_to_drag": max(inputs["target_lift_to_drag"], 1.0),
        "takeoff_mass": max(inputs["max_takeoff_mass_kg"], 1.0),
        "fuel_mass": max(inputs["max_fuel_mass_kg"], 1.0),
        "analysis_domain": 1.0,
    }
    violation_terms = []
    constraint_violation = 0.0
    for constraint in constraints:
        normalized_violation = min(
            0.0,
            float(constraint["margin"]) / normalizers[str(constraint["name"])],
        )
        squared_violation = normalized_violation * normalized_violation
        contribution = profile.optimizer.constraint_penalty * squared_violation
        constraint_violation += squared_violation
        violation_terms.append(
            {
                "metric_key": constraint["metric_key"],
                "value": constraint["actual"],
                "normalized_value": _rounded(normalized_violation),
                "weight": profile.optimizer.constraint_penalty,
                "contribution": _rounded(contribution),
            }
        )

    normalized_takeoff_mass = takeoff_mass / inputs["max_takeoff_mass_kg"]
    objective = (
        normalized_takeoff_mass
        + profile.optimizer.constraint_penalty * constraint_violation
    )
    score_terms = [
        {
            "metric_key": "mission.takeoff_mass_kg",
            "value": _rounded(takeoff_mass),
            "normalized_value": _rounded(normalized_takeoff_mass),
            "weight": 1.0,
            "contribution": _rounded(normalized_takeoff_mass),
        },
        *violation_terms,
    ]
    scored_coverage = {
        metric.key
        for metric in profile.metric_coverage.metrics
        if metric.used_in_score and metric.status != "not_connected"
    }
    term_keys = {str(term["metric_key"]) for term in score_terms}
    if not term_keys <= scored_coverage:
        missing = ", ".join(sorted(term_keys - scored_coverage))
        raise RuntimeError(f"score uses metrics absent from profile coverage: {missing}")

    warnings = list(analysis_payload["warnings"])
    warnings.extend(
        [
            profile.disclaimer,
            "Tail and propulsion geometry have only the partial connections declared in metric_coverage.",
        ]
    )
    candidate_identifier = _candidate_id(
        profile=profile,
        family_id=family_id,
        preset_id=preset_id,
        design=design,
        sizing=sizing,
    )
    geometry_fingerprint = _geometry_fingerprint(
        design=design,
        geometry_state=geometry_state,
    )
    cruise_consistency = _cruise_consistency_diagnostic(
        takeoff_mass_kg=takeoff_mass,
        reference_area_m2=reference_area,
        condition=condition,
        polar=polar,
        max_ld=lift_to_drag,
    )
    feasible = all(bool(constraint["satisfied"]) for constraint in constraints)
    return {
        "candidate_id": candidate_identifier,
        "family_id": family_id,
        "preset_id": preset_id,
        "feasible": feasible,
        "objective": _rounded(objective),
        "design": {key: _rounded(value, 12) for key, value in design.items()},
        "sizing": {key: _rounded(value, 12) for key, value in sizing.items()},
        "geometry_state": geometry_state,
        "design_hash": analysis_payload["design_hash"],
        "geometry_fingerprint": geometry_fingerprint,
        "condition": condition.model_dump(mode="json"),
        "analysis_summary": summary,
        "metrics": metrics,
        "constraints": constraints,
        "qualification": {
            "geometry_valid": True,
            "demo_constraints_satisfied": feasible,
            "engineering_validation": "not_performed",
        },
        "cruise_consistency": cruise_consistency,
        "score_breakdown": {
            "objective": _rounded(objective),
            "normalized_takeoff_mass": _rounded(normalized_takeoff_mass),
            "constraint_penalty": profile.optimizer.constraint_penalty,
            "constraint_violation": _rounded(constraint_violation),
            "terms": score_terms,
        },
        "domain_status": analysis_payload["domain_status"],
        "warnings": warnings,
        "provenance": {
            "mission_demo_model_id": DEMO_MODEL_ID,
            "mission_demo_model_version": DEMO_MODEL_VERSION,
            "analyze": analysis_payload["provenance"],
            "geometry": geometry_state["provenance"],
        },
    }


def evaluate_mission_demo_candidate(
    *,
    profile: MissionDemoProfile,
    family_id: str,
    preset_id: str,
    design: dict[str, float],
    sizing: dict[str, float],
    inputs: dict[str, float],
    family_registry: FamilyRegistry = registry,
) -> dict[str, object]:
    """Re-evaluate one fixed candidate through the same Demo calculation chain.

    The fixed sizing is checked against the profile's absolute sizing range, not
    the current mission input's sampling upper bound.  This is intentional: a
    response audit can lower ``max_fuel_mass_kg`` and observe the resulting fuel
    constraint violation without silently changing the candidate being tested.
    """

    validated_inputs = validate_mission_demo_submission(
        profile=profile,
        family_id=family_id,
        preset_id=preset_id,
        supplied_inputs=inputs,
        family_registry=family_registry,
    )
    _geometry_bounds_are_native(profile, family_registry)
    resolved_design = _preset_design(
        family_registry=family_registry,
        family_id=family_id,
        preset_id=preset_id,
    )
    resolved_design.update(design)
    for variable in profile.geometry_variables:
        try:
            value = float(resolved_design[variable.key])
        except (KeyError, TypeError, ValueError) as exc:
            raise MissionDemoRequestError(
                "invalid_fixed_design",
                f"invalid fixed design value for {variable.key}",
                field=f"design.{variable.key}",
            ) from exc
        if not isfinite(value) or not variable.minimum <= value <= variable.maximum:
            raise MissionDemoRequestError(
                "invalid_fixed_design",
                f"fixed design value is outside the profile range: {variable.key}",
                field=f"design.{variable.key}",
            )
        resolved_design[variable.key] = value

    expected_sizing_keys = {variable.key for variable in profile.sizing_variables}
    if set(sizing) != expected_sizing_keys:
        raise MissionDemoRequestError(
            "invalid_fixed_sizing",
            "fixed sizing keys must exactly match the profile sizing variables",
            field="sizing",
        )
    resolved_sizing: dict[str, float] = {}
    for variable in profile.sizing_variables:
        try:
            value = float(sizing[variable.key])
        except (TypeError, ValueError) as exc:
            raise MissionDemoRequestError(
                "invalid_fixed_sizing",
                f"invalid fixed sizing value for {variable.key}",
                field=f"sizing.{variable.key}",
            ) from exc
        if not isfinite(value) or not variable.minimum <= value <= variable.maximum:
            raise MissionDemoRequestError(
                "invalid_fixed_sizing",
                f"fixed sizing value is outside the profile range: {variable.key}",
                field=f"sizing.{variable.key}",
            )
        resolved_sizing[variable.key] = value

    return _evaluate_candidate(
        profile=profile,
        family_id=family_id,
        preset_id=preset_id,
        design=resolved_design,
        sizing=resolved_sizing,
        inputs=validated_inputs,
        condition=_condition(profile, validated_inputs),
        family_registry=family_registry,
    )


def _normalized_geometry_vector(
    candidate: dict[str, object],
    profile: MissionDemoProfile,
    inputs: dict[str, float],
) -> list[float]:
    design = candidate["design"]
    assert isinstance(design, dict)
    values = []
    for variable in profile.geometry_variables:
        minimum, maximum = _effective_bounds(variable, inputs)
        if maximum == minimum:
            values.append(0.0)
        else:
            values.append(
                (float(design[variable.key]) - minimum) / (maximum - minimum)
            )
    return values


def _normalized_distance(left: list[float], right: list[float]) -> float:
    return sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def search_mission_demo(
    *,
    job_id: str,
    family_id: str,
    preset_id: str,
    inputs: dict[str, float],
    profile: MissionDemoProfile,
    on_progress: ProgressCallback | None = None,
    is_cancelled: CancelCheck | None = None,
    family_registry: FamilyRegistry = registry,
) -> dict[str, object]:
    search_started = perf_counter()
    validated_inputs = validate_mission_demo_submission(
        profile=profile,
        family_id=family_id,
        preset_id=preset_id,
        supplied_inputs=inputs,
        family_registry=family_registry,
    )
    _geometry_bounds_are_native(profile, family_registry)
    preset_design = _preset_design(
        family_registry=family_registry,
        family_id=family_id,
        preset_id=preset_id,
    )
    condition = _condition(profile, validated_inputs)
    random = Random(profile.optimizer.seed)
    total_evaluations = (
        profile.optimizer.iterations * profile.optimizer.evaluations_per_iteration
    )
    records: list[dict[str, object]] = []
    valid_candidates: list[dict[str, object]] = []
    invalid_evaluations = 0

    for index in range(total_evaluations):
        if is_cancelled and is_cancelled():
            raise InterruptedError("mission demo search cancelled")
        design = dict(preset_design)
        sizing: dict[str, float] = {}
        if index == 0:
            for variable in profile.geometry_variables:
                value = float(design[variable.key])
                if not variable.minimum <= value <= variable.maximum:
                    raise RuntimeError(
                        f"preset value is outside the mission demo profile: {variable.key}"
                    )
            for variable in profile.sizing_variables:
                sizing[variable.key] = _midpoint_grid_value(variable, validated_inputs)
        elif index in {1, 2, 3}:
            all_variables = [
                *profile.geometry_variables,
                *profile.sizing_variables,
            ]
            for variable_index, variable in enumerate(all_variables):
                upper = index == 2 or (index == 3 and variable_index % 2 == 0)
                value = _boundary_grid_value(
                    variable,
                    validated_inputs,
                    upper=upper,
                )
                if variable in profile.geometry_variables:
                    design[variable.key] = value
                else:
                    sizing[variable.key] = value
        else:
            for variable in profile.geometry_variables:
                design[variable.key] = _grid_value(random, variable, validated_inputs)
            for variable in profile.sizing_variables:
                sizing[variable.key] = _grid_value(random, variable, validated_inputs)

        identifier = _candidate_id(
            profile=profile,
            family_id=family_id,
            preset_id=preset_id,
            design=design,
            sizing=sizing,
        )
        iteration = index // profile.optimizer.evaluations_per_iteration + 1
        evaluation_started = perf_counter()
        try:
            candidate = _evaluate_candidate(
                profile=profile,
                family_id=family_id,
                preset_id=preset_id,
                design=design,
                sizing=sizing,
                inputs=validated_inputs,
                condition=condition,
                family_registry=family_registry,
            )
        except (ArithmeticError, ValidationError, ValueError) as exc:
            elapsed_ms = _rounded((perf_counter() - evaluation_started) * 1000.0, 3)
            invalid_evaluations += 1
            record: dict[str, object] = {
                "evaluation": index + 1,
                "iteration": iteration,
                "candidate_id": identifier,
                "valid": False,
                "error_code": "invalid_candidate_evaluation",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "elapsed_ms": elapsed_ms,
                "design": {
                    key: _rounded(value, 12) for key, value in design.items()
                },
                "sizing": {
                    key: _rounded(value, 12) for key, value in sizing.items()
                },
            }
        else:
            elapsed_ms = _rounded((perf_counter() - evaluation_started) * 1000.0, 3)
            candidate["evaluation_elapsed_ms"] = elapsed_ms
            valid_candidates.append(candidate)
            record = {
                "evaluation": index + 1,
                "iteration": iteration,
                "candidate_id": candidate["candidate_id"],
                "valid": True,
                "feasible": candidate["feasible"],
                "objective": candidate["objective"],
                "constraint_violation": candidate["score_breakdown"][
                    "constraint_violation"
                ],
                "elapsed_ms": elapsed_ms,
                "design": candidate["design"],
                "sizing": candidate["sizing"],
                "design_hash": candidate["design_hash"],
                "geometry_fingerprint": candidate["geometry_fingerprint"],
                "metrics": candidate["metrics"],
                "constraints": candidate["constraints"],
                "score_breakdown": candidate["score_breakdown"],
                "cruise_consistency": candidate["cruise_consistency"],
            }
        records.append(record)
        if on_progress:
            on_progress(index + 1, total_evaluations, record)

    if is_cancelled and is_cancelled():
        raise InterruptedError("mission demo search cancelled")

    ranked = sorted(
        valid_candidates,
        key=lambda candidate: (
            not bool(candidate["feasible"]),
            float(candidate["objective"]),
            str(candidate["candidate_id"]),
        ),
    )
    selected: list[dict[str, object]] = []
    selected_vectors: list[list[float]] = []
    selection_decisions: list[dict[str, object]] = []
    feasible_valid_count = sum(
        1 for candidate in valid_candidates if bool(candidate["feasible"])
    )
    for ranked_position, candidate in enumerate(ranked, start=1):
        vector = _normalized_geometry_vector(candidate, profile, validated_inputs)
        distances = [
            _normalized_distance(vector, selected_vector)
            for selected_vector in selected_vectors
        ]
        minimum_distance = min(distances) if distances else None
        selected_rank: int | None = None
        if len(selected) >= profile.candidate_count:
            reason_code = "excluded_top_k_capacity"
            explanation = (
                "Not returned because the requested candidate count was already filled."
            )
        elif (
            minimum_distance is not None
            and minimum_distance < profile.diversity_threshold
        ):
            reason_code = "excluded_geometry_similarity"
            explanation = (
                "Not returned because its normalized geometry distance to an already "
                "selected candidate is below the configured diversity threshold."
            )
        else:
            selected.append(candidate)
            selected_vectors.append(vector)
            selected_rank = len(selected)
            if bool(candidate["feasible"]):
                reason_code = "selected_feasible_first_objective"
                explanation = (
                    "Selected in feasible-first/objective order and passed the geometry "
                    "diversity threshold."
                )
            elif feasible_valid_count == 0:
                reason_code = "selected_current_score_best_infeasible"
                explanation = (
                    "Selected by the current objective among candidates that do not "
                    "satisfy all connected Demo constraints; this is not a "
                    "minimum-violation claim."
                )
            else:
                reason_code = "selected_infeasible_after_feasible"
                explanation = (
                    "Selected after feasible candidates in feasible-first/objective order "
                    "and passed the geometry diversity threshold."
                )

        decision = {
            "candidate_id": candidate["candidate_id"],
            "ranked_position": ranked_position,
            "selected": selected_rank is not None,
            "selected_rank": selected_rank,
            "reason_code": reason_code,
            "explanation": explanation,
            "feasible": candidate["feasible"],
            "objective": candidate["objective"],
            "geometry_fingerprint": candidate["geometry_fingerprint"],
            "minimum_geometry_distance_to_selected": (
                None if minimum_distance is None else _rounded(minimum_distance)
            ),
        }
        selection_decisions.append(decision)
        if selected_rank is not None:
            candidate["rank"] = selected_rank
            candidate["selection"] = {
                key: value
                for key, value in decision.items()
                if key
                in {
                    "selected",
                    "selected_rank",
                    "ranked_position",
                    "reason_code",
                    "explanation",
                    "minimum_geometry_distance_to_selected",
                }
            }

    any_feasible = any(bool(candidate["feasible"]) for candidate in selected)
    profile_hash = mission_demo_profile_hash(profile)
    if not valid_candidates:
        result_status = "no_valid_candidates"
    elif any_feasible:
        result_status = "feasible"
    else:
        result_status = "no_feasible_solution_found"
    if not selected:
        selection_outcome = "none"
    elif len(selected) < profile.candidate_count:
        selection_outcome = "partial"
    else:
        selection_outcome = "complete"

    warnings = [
        profile.disclaimer,
        "Candidates are ranked only within this fixed demo budget and are not formal or global optima.",
        "Engineering validation has not been performed; geometry validity and connected Demo constraints are reported separately.",
    ]
    if selection_outcome == "partial":
        warnings.append(
            f"Only {len(selected)} of {profile.candidate_count} requested geometrically "
            "diverse valid candidates were found; the available candidates are returned."
        )
    elif selection_outcome == "none":
        warnings.append(
            "No valid candidate evaluation was produced; this is distinct from a valid "
            "candidate that does not satisfy the connected Demo constraints."
        )
    if valid_candidates and not any_feasible:
        warnings.append(
            "No valid candidate satisfied every connected Demo constraint. Rank 1 is the "
            "current-score-best unsatisfied candidate under the unchanged objective, not "
            "necessarily the candidate with minimum aggregate violation."
        )

    search_elapsed_ms = _rounded((perf_counter() - search_started) * 1000.0, 3)
    return {
        "schema_version": "1.0",
        "job_id": job_id,
        "status": result_status,
        "mode": "demo",
        "formal_status": profile.formal_status,
        "profile": {
            "id": profile.profile_id,
            "version": profile.profile_version,
            "hash": profile_hash,
        },
        "family_id": family_id,
        "preset_id": preset_id,
        "inputs": validated_inputs,
        "condition": condition.model_dump(mode="json"),
        "metric_coverage": profile.metric_coverage.model_dump(mode="json"),
        "ranking_rule": {
            "feasible_first": True,
            "primary": "objective_ascending",
            "tie_breaker": "candidate_id_ascending",
            "objective_definition": (
                "normalized_takeoff_mass_plus_weighted_squared_constraint_violations"
            ),
            "no_feasible_rank_one_semantics": (
                "current_score_best_unsatisfied_candidate_not_minimum_violation"
            ),
            "diversity": {
                "method": "normalized_euclidean",
                "threshold": profile.diversity_threshold,
                "variables": [
                    variable.key for variable in profile.geometry_variables
                ],
            },
        },
        "search": {
            "method": profile.optimizer.method,
            "seed": profile.optimizer.seed,
            "iterations": profile.optimizer.iterations,
            "evaluations": len(records),
            "valid": len(valid_candidates),
            "invalid": invalid_evaluations,
            "elapsed_ms": search_elapsed_ms,
            "records": records,
        },
        "selection": {
            "requested_count": profile.candidate_count,
            "returned_count": len(selected),
            "valid_candidate_count": len(valid_candidates),
            "feasible_valid_count": feasible_valid_count,
            "infeasible_valid_count": len(valid_candidates) - feasible_valid_count,
            "outcome": selection_outcome,
            "decisions": selection_decisions,
        },
        "candidates": selected,
        "warnings": warnings,
        "provenance": {
            "model_id": DEMO_MODEL_ID,
            "model_version": DEMO_MODEL_VERSION,
            "analysis_source": "current family registry Analyze response",
            "geometry_source": "exact candidate GeometryState from the same Analyze evaluation",
            "geometry_fingerprint_scope": (
                "family, actual design, GeometryState components and derived metrics; "
                "flight condition and provenance metadata excluded"
            ),
            "cruise_consistency_scope": (
                "diagnostic only; existing max-L/D range estimate and score are unchanged"
            ),
            "search_profile_hash": profile_hash,
            "uses_formal_optimization_spec": False,
        },
    }
