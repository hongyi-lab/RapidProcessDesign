from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from math import isfinite, log, sqrt
from random import Random
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
from services.api.app.services.rapid_design.families.registry import FamilyRegistry, registry

GRAVITY_M_S2 = 9.80665
DEMO_MODEL_ID = "mission-demo-transparent-mass-breguet"
DEMO_MODEL_VERSION = "1.0.0"

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
    return {
        "candidate_id": candidate_identifier,
        "family_id": family_id,
        "preset_id": preset_id,
        "feasible": all(bool(constraint["satisfied"]) for constraint in constraints),
        "objective": _rounded(objective),
        "design": {key: _rounded(value, 12) for key, value in design.items()},
        "sizing": {key: _rounded(value, 12) for key, value in sizing.items()},
        "geometry_state": geometry_state,
        "design_hash": analysis_payload["design_hash"],
        "condition": condition.model_dump(mode="json"),
        "analysis_summary": summary,
        "metrics": metrics,
        "constraints": constraints,
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
            invalid_evaluations += 1
            record: dict[str, object] = {
                "evaluation": index + 1,
                "iteration": iteration,
                "candidate_id": identifier,
                "valid": False,
                "error": str(exc),
            }
        else:
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
                "design_hash": candidate["design_hash"],
                "metrics": candidate["metrics"],
            }
        records.append(record)
        if on_progress:
            on_progress(index + 1, total_evaluations, record)

    if is_cancelled and is_cancelled():
        raise InterruptedError("mission demo search cancelled")
    if not valid_candidates:
        raise RuntimeError("mission demo search produced no valid evaluations")

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
    for candidate in ranked:
        vector = _normalized_geometry_vector(candidate, profile, validated_inputs)
        if all(
            _normalized_distance(vector, selected_vector)
            >= profile.diversity_threshold
            for selected_vector in selected_vectors
        ):
            selected.append(candidate)
            selected_vectors.append(vector)
        if len(selected) == profile.candidate_count:
            break
    if len(selected) < profile.candidate_count:
        raise RuntimeError(
            "mission demo search budget did not produce enough diverse valid candidates"
        )
    for rank, candidate in enumerate(selected, start=1):
        candidate["rank"] = rank

    any_feasible = any(bool(candidate["feasible"]) for candidate in selected)
    profile_hash = mission_demo_profile_hash(profile)
    return {
        "schema_version": "1.0",
        "job_id": job_id,
        "status": "feasible" if any_feasible else "no_feasible_solution_found",
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
            "invalid": invalid_evaluations,
            "records": records,
        },
        "candidates": selected,
        "warnings": [
            profile.disclaimer,
            "Candidates are ranked only within this fixed demo budget and are not formal or global optima.",
        ],
        "provenance": {
            "model_id": DEMO_MODEL_ID,
            "model_version": DEMO_MODEL_VERSION,
            "analysis_source": "current family registry Analyze response",
            "geometry_source": "exact candidate GeometryState from the same Analyze evaluation",
            "search_profile_hash": profile_hash,
            "uses_formal_optimization_spec": False,
        },
    }
