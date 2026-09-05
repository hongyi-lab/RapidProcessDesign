from __future__ import annotations

from math import isclose

import pytest

from services.api.app.schemas.rapid_design import MissionDemoJobResponse
from services.api.app.services.rapid_design import mission_demo
from services.api.app.services.rapid_design.config_loader import (
    load_mission_demo_profile,
    validated_mission_demo_inputs,
)
from services.api.app.services.rapid_design.families.registry import registry
from services.api.app.services.rapid_design.mission_demo import (
    evaluate_mission_demo_candidate,
    search_mission_demo,
)


def _fast_profile():
    profile = load_mission_demo_profile()
    return profile.model_copy(
        update={
            "optimizer": profile.optimizer.model_copy(
                update={"iterations": 2, "evaluations_per_iteration": 6}
            )
        },
        deep=True,
    )


def _preset_design(preset_id: str) -> dict[str, float]:
    manifest = registry.manifest("conventional_v2")
    return dict(
        next(item for item in manifest.presets if item.preset_id == preset_id).design
    )


def test_geometry_fingerprint_excludes_condition_and_sizing_but_tracks_geometry():
    profile = _fast_profile()
    design = _preset_design("long_endurance_uav")
    default_inputs = validated_mission_demo_inputs(profile, {})
    baseline = evaluate_mission_demo_candidate(
        profile=profile,
        family_id="conventional_v2",
        preset_id="long_endurance_uav",
        design=design,
        sizing={"fuel_mass_kg": 200.0},
        inputs=default_inputs,
    )
    changed_condition_and_sizing = evaluate_mission_demo_candidate(
        profile=profile,
        family_id="conventional_v2",
        preset_id="long_endurance_uav",
        design=design,
        sizing={"fuel_mass_kg": 300.0},
        inputs={**default_inputs, "cruise_altitude_m": 5000.0},
    )
    changed_geometry = evaluate_mission_demo_candidate(
        profile=profile,
        family_id="conventional_v2",
        preset_id="long_endurance_uav",
        design={**design, "wing_span_m": design["wing_span_m"] + 0.1},
        sizing={"fuel_mass_kg": 200.0},
        inputs=default_inputs,
    )

    assert baseline["design_hash"] != changed_condition_and_sizing["design_hash"]
    assert (
        baseline["geometry_fingerprint"]
        == changed_condition_and_sizing["geometry_fingerprint"]
    )
    assert baseline["geometry_state"] == changed_condition_and_sizing["geometry_state"]
    assert baseline["geometry_fingerprint"] != changed_geometry["geometry_fingerprint"]


def test_cruise_consistency_reports_matched_ld_without_changing_range_ld():
    profile = _fast_profile()
    candidate = evaluate_mission_demo_candidate(
        profile=profile,
        family_id="conventional_v2",
        preset_id="long_endurance_uav",
        design=_preset_design("long_endurance_uav"),
        sizing={"fuel_mass_kg": 200.0},
        inputs={},
    )

    diagnostic = candidate["cruise_consistency"]
    assert diagnostic["status"] == "supported"
    assert diagnostic["reason_code"] == "matched"
    assert diagnostic["reference_state"]["mass_basis"] == "mission_demo_takeoff_mass"
    assert isclose(
        diagnostic["reference_state"]["mass_kg"],
        candidate["metrics"]["takeoff_mass_kg"],
    )
    assert diagnostic["matched_working_point"] is not None
    assert diagnostic["comparison"]["ld_at_reference_state"] == diagnostic[
        "matched_working_point"
    ]["ld"]
    assert diagnostic["comparison"]["max_ld"] == candidate["analysis_summary"][
        "max_ld"
    ]
    assert diagnostic["comparison"]["range_model_ld"] == candidate[
        "analysis_summary"
    ]["max_ld"]
    assert diagnostic["enters_score"] is False
    assert diagnostic["enters_range_estimate"] is False


def test_cruise_consistency_refuses_to_extrapolate_when_lift_is_unsupported():
    profile = _fast_profile()
    candidate = evaluate_mission_demo_candidate(
        profile=profile,
        family_id="conventional_v2",
        preset_id="long_endurance_uav",
        design=_preset_design("long_endurance_uav"),
        sizing={"fuel_mass_kg": 900.0},
        inputs={
            "payload_mass_kg": 500.0,
            "cruise_speed_kmh": 80.0,
            "cruise_altitude_m": 11000.0,
            "max_fuel_mass_kg": 900.0,
        },
    )

    diagnostic = candidate["cruise_consistency"]
    assert diagnostic["required_cl"] > diagnostic["polar_support"]["max_cl"]
    assert diagnostic["status"] == "unsupported"
    assert diagnostic["reason_code"] == "lift_not_supported"
    assert diagnostic["matched_working_point"] is None
    assert diagnostic["comparison"]["ld_at_reference_state"] is None
    assert diagnostic["comparison"]["range_model_ld"] == candidate[
        "analysis_summary"
    ]["max_ld"]


def test_fixed_candidate_helper_allows_new_input_bound_to_create_fuel_violation():
    profile = _fast_profile()
    candidate = evaluate_mission_demo_candidate(
        profile=profile,
        family_id="conventional_v2",
        preset_id="long_endurance_uav",
        design=_preset_design("long_endurance_uav"),
        sizing={"fuel_mass_kg": 200.0},
        inputs={"max_fuel_mass_kg": 25.0},
    )

    fuel = next(item for item in candidate["constraints"] if item["name"] == "fuel_mass")
    assert fuel["actual"] == 200.0
    assert fuel["limit"] == 25.0
    assert fuel["satisfied"] is False


def test_search_returns_partial_diverse_candidates_instead_of_failing(monkeypatch):
    profile = _fast_profile()
    monkeypatch.setattr(mission_demo, "_normalized_distance", lambda _left, _right: 0.0)

    result = search_mission_demo(
        job_id="partial-candidates",
        family_id="conventional_v2",
        preset_id="long_endurance_uav",
        inputs={},
        profile=profile,
    )

    assert result["selection"]["outcome"] == "partial"
    assert result["selection"]["requested_count"] == 3
    assert result["selection"]["returned_count"] == 1
    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["qualification"]["geometry_valid"] is True
    assert (
        result["candidates"][0]["qualification"]["engineering_validation"]
        == "not_performed"
    )
    assert any(
        decision["reason_code"] == "excluded_geometry_similarity"
        for decision in result["selection"]["decisions"]
    )
    assert any("Only 1 of 3" in warning for warning in result["warnings"])


class _InvalidCandidateRegistry:
    def manifest(self, family_id):
        return registry.manifest(family_id)

    def analyze(self, _request):
        raise ValueError("controlled invalid candidate")


class _BrokenRegistry(_InvalidCandidateRegistry):
    def analyze(self, _request):
        raise RuntimeError("controlled program failure")


def test_search_distinguishes_zero_valid_candidates_from_program_failure():
    profile = _fast_profile()
    no_valid = search_mission_demo(
        job_id="no-valid-candidates",
        family_id="conventional_v2",
        preset_id="long_endurance_uav",
        inputs={},
        profile=profile,
        family_registry=_InvalidCandidateRegistry(),
    )

    assert no_valid["status"] == "no_valid_candidates"
    assert no_valid["candidates"] == []
    assert no_valid["selection"]["outcome"] == "none"
    assert no_valid["search"]["valid"] == 0
    assert no_valid["search"]["invalid"] == no_valid["search"]["evaluations"]

    with pytest.raises(RuntimeError, match="controlled program failure"):
        search_mission_demo(
            job_id="program-failure",
            family_id="conventional_v2",
            preset_id="long_endurance_uav",
            inputs={},
            profile=profile,
            family_registry=_BrokenRegistry(),
        )


def test_no_feasible_result_explains_objective_ranking_without_minimum_violation_claim():
    profile = _fast_profile()
    result = search_mission_demo(
        job_id="no-feasible-copy-contract",
        family_id="conventional_v2",
        preset_id="payload_utility",
        inputs={
            "required_range_km": 3000.0,
            "target_lift_to_drag": 40.0,
            "max_takeoff_mass_kg": 300.0,
        },
        profile=profile,
    )

    assert result["status"] == "no_feasible_solution_found"
    assert (
        result["ranking_rule"]["no_feasible_rank_one_semantics"]
        == "current_score_best_unsatisfied_candidate_not_minimum_violation"
    )
    assert result["candidates"][0]["selection"]["reason_code"] == (
        "selected_current_score_best_infeasible"
    )
    assert "not necessarily" in result["warnings"][-1]


def test_demo_job_schema_accepts_explicit_interrupted_status():
    job = MissionDemoJobResponse.model_validate(
        {
            "id": "demo-interrupted",
            "status": "interrupted",
            "progress": 0.5,
            "stage": "interrupted",
            "error": "Service restarted before this task completed.",
            "created_at": "2026-09-05T00:00:00Z",
            "updated_at": "2026-09-05T00:01:00Z",
            "mode": "demo",
            "family_id": "conventional_v2",
            "preset_id": "long_endurance_uav",
            "profile_id": "mission_demo_v1",
            "profile_version": "1.0.0",
            "formal_status": "pending_teacher_decision",
        }
    )

    assert job.status == "interrupted"
