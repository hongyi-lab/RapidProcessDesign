import json
import time
from itertools import combinations
from math import isfinite, sqrt
from pathlib import Path
from threading import Event

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from services.api.app.schemas.rapid_design import (
    ConventionalV2Design,
    GeometryState,
    MissionDemoProfile,
    RapidAnalyzeRequest,
)
from services.api.app.services.rapid_design.config_loader import (
    DEFAULT_CONFIG_PATH,
    MISSION_DEMO_PROFILE_PATH,
    load_mission_demo_profile,
    load_rapid_design_config,
    mission_demo_profile_hash,
    validated_mission_demo_inputs,
)
from services.api.app.services.rapid_design.families.registry import registry
from services.api.app.services.rapid_design.mission_demo import search_mission_demo
from services.api.app.services.rapid_design.mission_demo_job_runner import (
    MissionDemoJobRunner,
    MissionDemoResultStore,
)


def _fast_profile() -> MissionDemoProfile:
    profile = load_mission_demo_profile()
    return profile.model_copy(
        update={
            "optimizer": profile.optimizer.model_copy(
                update={"iterations": 2, "evaluations_per_iteration": 6}
            )
        },
        deep=True,
    )


def _default_inputs(profile: MissionDemoProfile) -> dict[str, float]:
    return validated_mission_demo_inputs(profile, {})


def _numeric_values(value):
    if isinstance(value, dict):
        for nested in value.values():
            yield from _numeric_values(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _numeric_values(nested)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        yield float(value)


def _candidate_vector(
    candidate: dict,
    profile: MissionDemoProfile,
) -> list[float]:
    return [
            (candidate["design"][variable.key] - variable.minimum)
            / (variable.maximum - variable.minimum)
        for variable in profile.geometry_variables
    ]


def _distance(left: list[float], right: list[float]) -> float:
    return sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def _wait_for_terminal(
    client: TestClient,
    job_id: str,
    *,
    timeout_s: float = 30.0,
) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        response = client.get(f"/api/rapid-design/demo/jobs/{job_id}")
        assert response.status_code == 200
        job = response.json()
        if job["status"] in {"succeeded", "failed", "cancelled"}:
            return job
        time.sleep(0.01)
    raise AssertionError("demo job did not reach a terminal state")


def _demo_app(runner: MissionDemoJobRunner) -> FastAPI:
    from services.api.app.routers import rapid_design as rapid_router

    app = FastAPI()
    app.include_router(rapid_router.router)
    app.dependency_overrides[rapid_router.get_demo_runner] = lambda: runner
    return app


def test_mission_demo_profile_is_versioned_native_and_isolated_from_legacy():
    profile = load_mission_demo_profile()
    legacy = load_rapid_design_config()

    assert MISSION_DEMO_PROFILE_PATH != DEFAULT_CONFIG_PATH
    assert profile.profile_id == "mission_demo_v1"
    assert profile.profile_version == "2.0.0"
    assert profile.mode == "demo_only"
    assert profile.formal_status == "pending_teacher_decision"
    assert profile.supported_family_ids == ["conventional_v2"]
    assert profile.candidate_count == 3
    assert len(mission_demo_profile_hash(profile)) == 64
    assert {variable.key for variable in profile.geometry_variables} <= set(
        ConventionalV2Design.model_fields
    )
    assert [variable.key for variable in profile.sizing_variables] == ["fuel_mass_kg"]
    assert not hasattr(legacy, "profile_id")
    assert registry.manifest("conventional_v2").capabilities.optimize is False
    assert (
        registry.manifest("conventional_v2").optimization_status
        == "pending_teacher_decision"
    )


def test_mission_demo_profile_rejects_missing_evaluator_inputs():
    payload = load_mission_demo_profile().model_dump(mode="python")
    payload["inputs"] = [
        item for item in payload["inputs"] if item["key"] != "cruise_altitude_m"
    ]

    with pytest.raises(ValidationError, match="missing: cruise_altitude_m"):
        MissionDemoProfile.model_validate(payload)


@pytest.mark.parametrize(
    "preset_id",
    ["long_endurance_uav", "fast_cruise_recon", "payload_utility"],
)
def test_demo_search_returns_three_diverse_schema_valid_candidates(preset_id: str):
    profile = _fast_profile()
    inputs = _default_inputs(profile)
    result = search_mission_demo(
        job_id="schema-check",
        family_id="conventional_v2",
        preset_id=preset_id,
        inputs=inputs,
        profile=profile,
    )

    assert result["search"]["evaluations"] == 12
    assert result["search"]["evaluations"] > profile.candidate_count
    assert len(result["search"]["records"]) == 12
    assert len(result["candidates"]) == profile.candidate_count
    assert [candidate["rank"] for candidate in result["candidates"]] == [1, 2, 3]
    assert len({candidate["candidate_id"] for candidate in result["candidates"]}) == 3
    assert len({candidate["design_hash"] for candidate in result["candidates"]}) == 3

    vectors = [
        _candidate_vector(candidate, profile)
        for candidate in result["candidates"]
    ]
    for left, right in combinations(vectors, 2):
        assert _distance(left, right) >= profile.diversity_threshold

    for candidate in result["candidates"]:
        ConventionalV2Design.model_validate(candidate["design"])
        state = GeometryState.model_validate(candidate["geometry_state"])
        assert candidate["family_id"] == "conventional_v2"
        assert candidate["preset_id"] == preset_id
        assert state.family_id == "conventional_v2"
        assert state.geometry_status == "valid"
        assert all(check.status == "pass" for check in state.geometry_checks)
        assert all(isfinite(value) for value in _numeric_values(candidate["geometry_state"]))
        assert candidate["analysis_summary"]["max_ld"] > 0


def test_demo_search_is_deterministic_and_candidate_reanalyzes_exactly():
    profile = _fast_profile()
    inputs = _default_inputs(profile)
    arguments = {
        "family_id": "conventional_v2",
        "preset_id": "long_endurance_uav",
        "inputs": inputs,
        "profile": profile,
    }
    first = search_mission_demo(job_id="first-job", **arguments)
    second = search_mission_demo(job_id="second-job", **arguments)

    assert [candidate["candidate_id"] for candidate in first["candidates"]] == [
        candidate["candidate_id"] for candidate in second["candidates"]
    ]
    assert [candidate["design_hash"] for candidate in first["candidates"]] == [
        candidate["design_hash"] for candidate in second["candidates"]
    ]
    assert [candidate["design"] for candidate in first["candidates"]] == [
        candidate["design"] for candidate in second["candidates"]
    ]

    for candidate in first["candidates"]:
        repeated = registry.analyze(
            RapidAnalyzeRequest(
                family_id=candidate["family_id"],
                preset_id=candidate["preset_id"],
                design=candidate["design"],
                condition=candidate["condition"],
            )
        ).model_dump(mode="json")
        assert repeated["design_hash"] == candidate["design_hash"]
        assert repeated["geometry_state"] == candidate["geometry_state"]
        assert repeated["analysis"]["summary"] == candidate["analysis_summary"]


def test_not_connected_metrics_never_enter_the_score():
    profile = _fast_profile()
    result = search_mission_demo(
        job_id="coverage-check",
        family_id="conventional_v2",
        preset_id="fast_cruise_recon",
        inputs=_default_inputs(profile),
        profile=profile,
    )
    coverage = result["metric_coverage"]["metrics"]
    disconnected = {
        metric["key"] for metric in coverage if metric["status"] == "not_connected"
    }
    allowed = {
        metric["key"]
        for metric in coverage
        if metric["used_in_score"] and metric["status"] != "not_connected"
    }
    assert disconnected
    for candidate in result["candidates"]:
        score_keys = {
            term["metric_key"] for term in candidate["score_breakdown"]["terms"]
        }
        assert score_keys <= allowed
        assert score_keys.isdisjoint(disconnected)


def test_impossible_demo_requirements_return_current_score_ranked_candidates():
    profile = _fast_profile()
    result = search_mission_demo(
        job_id="no-feasible-check",
        family_id="conventional_v2",
        preset_id="payload_utility",
        inputs={
            "required_range_km": 3000,
            "target_lift_to_drag": 40,
            "max_takeoff_mass_kg": 300,
        },
        profile=profile,
    )

    assert result["status"] == "no_feasible_solution_found"
    assert all(not candidate["feasible"] for candidate in result["candidates"])
    assert [candidate["objective"] for candidate in result["candidates"]] == sorted(
        candidate["objective"] for candidate in result["candidates"]
    )


def test_demo_search_accepts_a_fixed_fuel_bound_without_dividing_by_zero():
    profile = _fast_profile()
    result = search_mission_demo(
        job_id="fixed-fuel-bound",
        family_id="conventional_v2",
        preset_id="long_endurance_uav",
        inputs={"max_fuel_mass_kg": 25},
        profile=profile,
    )

    assert len(result["candidates"]) == profile.candidate_count
    assert {
        candidate["sizing"]["fuel_mass_kg"] for candidate in result["candidates"]
    } == {25.0}


def test_demo_search_checks_cancellation_before_the_first_evaluation():
    profile = _fast_profile()
    progress_calls = []
    with pytest.raises(InterruptedError, match="cancelled"):
        search_mission_demo(
            job_id="cancel-before-evaluation",
            family_id="conventional_v2",
            preset_id="long_endurance_uav",
            inputs=_default_inputs(profile),
            profile=profile,
            is_cancelled=lambda: True,
            on_progress=lambda *args: progress_calls.append(args),
        )
    assert progress_calls == []


def test_demo_api_lifecycle_sse_result_and_isolated_persistence(tmp_path: Path):
    profile = _fast_profile()
    store = MissionDemoResultStore(tmp_path / "demo_jobs")
    runner = MissionDemoJobRunner(profile=profile, store=store)
    app = _demo_app(runner)
    try:
        with TestClient(app) as client:
            config_response = client.get("/api/rapid-design/demo/config")
            assert config_response.status_code == 200
            assert config_response.json()["profile_id"] == "mission_demo_v1"

            response = client.post(
                "/api/rapid-design/demo/jobs",
                json={
                    "mode": "demo",
                    "family_id": "conventional_v2",
                    "preset_id": "long_endurance_uav",
                    "inputs": {},
                },
            )
            assert response.status_code == 202
            created = response.json()
            assert created["mode"] == "demo"
            assert created["formal_status"] == "pending_teacher_decision"
            job = _wait_for_terminal(client, created["id"])
            assert job["status"] == "succeeded"

            events_response = client.get(
                f"/api/rapid-design/demo/jobs/{created['id']}/events"
            )
            assert events_response.status_code == 200
            event_names = [
                line.removeprefix("event: ")
                for line in events_response.text.splitlines()
                if line.startswith("event: ")
            ]
            assert event_names[0] == "queued"
            assert "progress" in event_names
            assert event_names[-1] == "completed"

            result_response = client.get(
                f"/api/rapid-design/demo/jobs/{created['id']}/result"
            )
            assert result_response.status_code == 200
            result = result_response.json()
            assert result["profile"]["hash"] == mission_demo_profile_hash(profile)
            assert result["search"]["evaluations"] == 12
            assert len(result["candidates"]) == 3
            assert client.get("/api/rapid-design/demo/jobs/missing").status_code == 404

        job_dir = tmp_path / "demo_jobs" / created["id"]
        assert (job_dir / "request.json").exists()
        assert (job_dir / "profile.json").exists()
        assert (job_dir / "status.json").exists()
        assert (job_dir / "result.json").exists()
        assert json.loads((job_dir / "request.json").read_text(encoding="utf-8"))[
            "mode"
        ] == "demo"
        assert not (tmp_path / "jobs").exists()
    finally:
        runner.shutdown()


def test_demo_api_cancel_is_cooperative_and_terminal(tmp_path: Path):
    started = Event()

    def cancellable_search(**kwargs):
        started.set()
        while not kwargs["is_cancelled"]():
            time.sleep(0.005)
        raise InterruptedError("cancelled by test")

    runner = MissionDemoJobRunner(
        profile=_fast_profile(),
        store=MissionDemoResultStore(tmp_path / "demo_jobs"),
        search=cancellable_search,
    )
    app = _demo_app(runner)
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/rapid-design/demo/jobs",
                json={
                    "mode": "demo",
                    "family_id": "conventional_v2",
                    "preset_id": "long_endurance_uav",
                    "inputs": {},
                },
            ).json()
            assert started.wait(timeout=1.0)
            cancelled = client.post(
                f"/api/rapid-design/demo/jobs/{created['id']}/cancel"
            )
            assert cancelled.status_code == 200
            assert cancelled.json()["stage"] == "cancelling"
            terminal = _wait_for_terminal(client, created["id"])
            assert terminal["status"] == "cancelled"
            assert (
                client.get(
                    f"/api/rapid-design/demo/jobs/{created['id']}/result"
                ).status_code
                == 409
            )
    finally:
        runner.shutdown()


def test_demo_api_persists_background_failure(tmp_path: Path):
    def failing_search(**_kwargs):
        raise RuntimeError("controlled demo evaluator failure")

    runner = MissionDemoJobRunner(
        profile=_fast_profile(),
        store=MissionDemoResultStore(tmp_path / "demo_jobs"),
        search=failing_search,
    )
    app = _demo_app(runner)
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/rapid-design/demo/jobs",
                json={
                    "mode": "demo",
                    "family_id": "conventional_v2",
                    "preset_id": "long_endurance_uav",
                    "inputs": {},
                },
            ).json()
            terminal = _wait_for_terminal(client, created["id"])
            assert terminal["status"] == "failed"
            assert terminal["error"] == "controlled demo evaluator failure"
            result_response = client.get(
                f"/api/rapid-design/demo/jobs/{created['id']}/result"
            )
            assert result_response.status_code == 500
            status_path = tmp_path / "demo_jobs" / created["id"] / "status.json"
            persisted = json.loads(status_path.read_text(encoding="utf-8"))
            assert persisted["status"] == "failed"
    finally:
        runner.shutdown()


def test_demo_api_rejects_bwb_unknown_preset_and_extra_fields(tmp_path: Path):
    runner = MissionDemoJobRunner(
        profile=_fast_profile(),
        store=MissionDemoResultStore(tmp_path / "demo_jobs"),
    )
    app = _demo_app(runner)
    try:
        with TestClient(app) as client:
            base = {
                "mode": "demo",
                "family_id": "conventional_v2",
                "preset_id": "long_endurance_uav",
                "inputs": {},
            }
            bwb = client.post(
                "/api/rapid-design/demo/jobs",
                json={**base, "family_id": "bwb_v1", "preset_id": "balanced_concept"},
            )
            unknown = client.post(
                "/api/rapid-design/demo/jobs",
                json={**base, "preset_id": "not-a-preset"},
            )
            extra = client.post(
                "/api/rapid-design/demo/jobs",
                json={**base, "design": {}},
            )

            assert bwb.status_code == 422
            assert bwb.json()["detail"]["code"] == "unsupported_family"
            assert unknown.status_code == 422
            assert unknown.json()["detail"]["code"] == "unknown_preset"
            assert extra.status_code == 422
    finally:
        runner.shutdown()


def test_legacy_and_formal_contracts_remain_unchanged():
    from services.api.app.routers.rapid_design import router

    paths = {route.path for route in router.routes}
    assert "/api/rapid-design/config" in paths
    assert "/api/rapid-design/jobs" in paths
    assert "/api/rapid-design/demo/config" in paths
    assert "/api/rapid-design/demo/jobs" in paths
    assert load_rapid_design_config().schema_version == "1.0"
    for manifest in registry.manifests():
        assert manifest.capabilities.optimize is False
        assert manifest.optimization_status == "pending_teacher_decision"
