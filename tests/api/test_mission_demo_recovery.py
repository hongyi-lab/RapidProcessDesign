import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.api.app.schemas.rapid_design import MissionDemoProfile
from services.api.app.services.rapid_design.config_loader import (
    load_mission_demo_profile,
    mission_demo_profile_hash,
    validated_mission_demo_inputs,
)
from services.api.app.services.rapid_design.mission_demo_job_runner import (
    MissionDemoJobRunner,
    MissionDemoResultStore,
)


def _app(runner: MissionDemoJobRunner) -> FastAPI:
    from services.api.app.routers import rapid_design as rapid_router

    app = FastAPI()
    app.include_router(rapid_router.router)
    app.dependency_overrides[rapid_router.get_demo_runner] = lambda: runner
    return app


def _result_for(
    *,
    job_id: str,
    family_id: str,
    preset_id: str,
    inputs: dict[str, float],
    profile: MissionDemoProfile,
    status: str = "feasible",
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "job_id": job_id,
        "status": status,
        "mode": "demo",
        "formal_status": profile.formal_status,
        "profile": {
            "id": profile.profile_id,
            "version": profile.profile_version,
            "hash": mission_demo_profile_hash(profile),
        },
        "family_id": family_id,
        "preset_id": preset_id,
        "inputs": inputs,
        "candidates": [],
    }


def _completed_search(**kwargs) -> dict[str, object]:
    return _result_for(
        job_id=kwargs["job_id"],
        family_id=kwargs["family_id"],
        preset_id=kwargs["preset_id"],
        inputs=kwargs["inputs"],
        profile=kwargs["profile"],
    )


def _wait(runner: MissionDemoJobRunner, job_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        job = runner.get(job_id)
        assert job is not None
        if job["status"] in {"succeeded", "failed", "cancelled", "interrupted"}:
            return job
        time.sleep(0.005)
    raise AssertionError("Demo job did not become terminal")


def _persist_status(
    store: MissionDemoResultStore,
    profile: MissionDemoProfile,
    *,
    job_id: str,
    status: str,
    stage: str | None = None,
) -> dict[str, object]:
    inputs = validated_mission_demo_inputs(profile, {})
    timestamp = "2026-09-05T00:00:00+00:00"
    job: dict[str, object] = {
        "id": job_id,
        "status": status,
        "progress": 0.5,
        "stage": stage or status,
        "error": None,
        "created_at": timestamp,
        "updated_at": timestamp,
        "mode": "demo",
        "family_id": "conventional_v2",
        "preset_id": "long_endurance_uav",
        "profile_id": profile.profile_id,
        "profile_version": profile.profile_version,
        "formal_status": profile.formal_status,
        "inputs": inputs,
    }
    store.write_json(
        job_id,
        "request.json",
        {
            "mode": "demo",
            "family_id": job["family_id"],
            "preset_id": job["preset_id"],
            "inputs": inputs,
        },
    )
    store.write_json(
        job_id,
        "profile.json",
        {
            **profile.model_dump(mode="json"),
            "profile_hash": mission_demo_profile_hash(profile),
        },
    )
    store.write_json(job_id, "status.json", job)
    return job


def test_completed_job_is_queryable_after_runner_restart(tmp_path: Path):
    profile = load_mission_demo_profile()
    store = MissionDemoResultStore(tmp_path / "demo_jobs")
    first = MissionDemoJobRunner(
        profile=profile,
        store=store,
        search=_completed_search,
    )
    created = first.create(
        family_id="conventional_v2",
        preset_id="long_endurance_uav",
        supplied_inputs={},
    )
    completed = _wait(first, str(created["id"]))
    assert completed["status"] == "succeeded"
    first.shutdown()

    calls = 0

    def must_not_resume(**_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("persisted jobs must not restart search")

    restarted = MissionDemoJobRunner(
        profile=profile,
        store=store,
        search=must_not_resume,
    )
    try:
        with TestClient(_app(restarted)) as client:
            job_response = client.get(
                f"/api/rapid-design/demo/jobs/{created['id']}"
            )
            assert job_response.status_code == 200
            assert job_response.json()["status"] == "succeeded"

            result_response = client.get(
                f"/api/rapid-design/demo/jobs/{created['id']}/result"
            )
            assert result_response.status_code == 200
            assert result_response.json()["job_id"] == created["id"]

            recent = client.get("/api/rapid-design/demo/jobs?limit=1")
            assert recent.status_code == 200
            assert recent.json()["jobs"][0]["id"] == created["id"]
            assert recent.json()["recovery"] == {
                "completed_queryable": True,
                "interrupted_resumable": False,
            }

            events = client.get(
                f"/api/rapid-design/demo/jobs/{created['id']}/events"
            )
            assert events.status_code == 200
            assert "event: recovered" in events.text
        assert calls == 0
    finally:
        restarted.shutdown()


@pytest.mark.parametrize(
    ("persisted_status", "persisted_stage"),
    [
        ("queued", "queued"),
        ("running", "evaluating"),
        ("running", "cancelling"),
    ],
)
def test_unfinished_jobs_become_interrupted_without_resuming(
    tmp_path: Path,
    persisted_status: str,
    persisted_stage: str,
):
    profile = load_mission_demo_profile()
    store = MissionDemoResultStore(tmp_path / persisted_stage)
    job_id = f"unfinished-{persisted_stage}"
    _persist_status(
        store,
        profile,
        job_id=job_id,
        status=persisted_status,
        stage=persisted_stage,
    )
    calls = 0

    def must_not_resume(**_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("interrupted jobs must not restart search")

    runner = MissionDemoJobRunner(
        profile=profile,
        store=store,
        search=must_not_resume,
    )
    try:
        with TestClient(_app(runner)) as client:
            response = client.get(f"/api/rapid-design/demo/jobs/{job_id}")
            assert response.status_code == 200
            restored = response.json()
            assert restored["status"] == "interrupted"
            assert restored["stage"] == "interrupted"
            assert "automatic resume is not supported" in restored["error"]

            result = client.get(f"/api/rapid-design/demo/jobs/{job_id}/result")
            assert result.status_code == 409
            assert result.json()["detail"] == {
                "code": "job_interrupted",
                "message": restored["error"],
                "resumable": False,
            }

            events = client.get(f"/api/rapid-design/demo/jobs/{job_id}/events")
            assert "event: interrupted" in events.text
        assert calls == 0
        persisted = store.read_json(job_id, "status.json")
        assert persisted is not None
        assert persisted["status"] == "interrupted"
    finally:
        runner.shutdown()


def test_result_artifact_wins_over_stale_running_status(tmp_path: Path):
    profile = load_mission_demo_profile()
    store = MissionDemoResultStore(tmp_path / "demo_jobs")
    job_id = "result-before-final-status"
    job = _persist_status(store, profile, job_id=job_id, status="running")
    store.write_json(
        job_id,
        "result.json",
        _result_for(
            job_id=job_id,
            family_id=str(job["family_id"]),
            preset_id=str(job["preset_id"]),
            inputs=dict(job["inputs"]),
            profile=profile,
            status="no_feasible_solution_found",
        ),
    )

    runner = MissionDemoJobRunner(profile=profile, store=store)
    try:
        recovered = runner.get(job_id)
        assert recovered is not None
        assert recovered["status"] == "succeeded"
        assert recovered["stage"] == "no_feasible_candidates"
        assert recovered["progress"] == 1.0
    finally:
        runner.shutdown()


def test_recovery_rejects_result_that_belongs_to_another_job(tmp_path: Path):
    profile = load_mission_demo_profile()
    store = MissionDemoResultStore(tmp_path / "demo_jobs")
    job_id = "owned-job"
    job = _persist_status(store, profile, job_id=job_id, status="succeeded")
    store.write_json(
        job_id,
        "result.json",
        _result_for(
            job_id="different-job",
            family_id=str(job["family_id"]),
            preset_id=str(job["preset_id"]),
            inputs=dict(job["inputs"]),
            profile=profile,
        ),
    )

    runner = MissionDemoJobRunner(profile=profile, store=store)
    try:
        with TestClient(_app(runner)) as client:
            status = client.get(f"/api/rapid-design/demo/jobs/{job_id}")
            assert status.status_code == 200
            assert status.json()["status"] == "failed"
            assert status.json()["stage"] == "recovery_error"
            assert "different job" in status.json()["error"]

            result = client.get(f"/api/rapid-design/demo/jobs/{job_id}/result")
            assert result.status_code == 500
            assert result.json()["detail"]["code"] == "persisted_result_invalid"
    finally:
        runner.shutdown()


def test_store_rejects_path_escape_and_unknown_artifact_names(tmp_path: Path):
    store = MissionDemoResultStore(tmp_path / "demo_jobs")

    for unsafe in ("", ".", "..", "../job", "job/child", "job\\child"):
        with pytest.raises(ValueError, match="invalid demo job id"):
            store.job_dir(unsafe)
    with pytest.raises(ValueError, match="invalid demo artifact name"):
        store.write_json("safe-job", "../result.json", {})


@pytest.mark.parametrize(
    ("result_status", "expected_stage"),
    [
        ("feasible", "completed"),
        ("no_feasible_solution_found", "no_feasible_candidates"),
        ("no_valid_candidates", "no_valid_candidates"),
    ],
)
def test_result_outcomes_have_distinct_terminal_stages(
    tmp_path: Path,
    result_status: str,
    expected_stage: str,
):
    profile = load_mission_demo_profile()

    def search(**kwargs):
        return _result_for(
            job_id=kwargs["job_id"],
            family_id=kwargs["family_id"],
            preset_id=kwargs["preset_id"],
            inputs=kwargs["inputs"],
            profile=kwargs["profile"],
            status=result_status,
        )

    runner = MissionDemoJobRunner(
        profile=profile,
        store=MissionDemoResultStore(tmp_path / result_status),
        search=search,
    )
    try:
        created = runner.create(
            family_id="conventional_v2",
            preset_id="long_endurance_uav",
            supplied_inputs={},
        )
        terminal = _wait(runner, str(created["id"]))
        assert terminal["status"] == "succeeded"
        assert terminal["stage"] == expected_stage
    finally:
        runner.shutdown()


def test_program_exception_is_not_reported_as_candidate_outcome(tmp_path: Path):
    def failing_search(**_kwargs):
        raise RuntimeError("evaluator exploded")

    runner = MissionDemoJobRunner(
        profile=load_mission_demo_profile(),
        store=MissionDemoResultStore(tmp_path / "demo_jobs"),
        search=failing_search,
    )
    try:
        created = runner.create(
            family_id="conventional_v2",
            preset_id="long_endurance_uav",
            supplied_inputs={},
        )
        terminal = _wait(runner, str(created["id"]))
        assert terminal["status"] == "failed"
        assert terminal["stage"] == "program_error"
        assert terminal["error"] == "evaluator exploded"
        assert runner.result(str(created["id"])) is None
    finally:
        runner.shutdown()
