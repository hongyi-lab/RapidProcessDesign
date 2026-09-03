import time

import pytest
from fastapi.testclient import TestClient

from services.api.app.schemas.aircraft_spec import AircraftSpec
from services.api.app.services.rapid_design.config_loader import (
    load_rapid_design_config,
    validated_inputs,
)
from services.api.app.services.rapid_design.evaluator import evaluate_design
from services.api.app.services.rapid_design.job_runner import RapidDesignJobRunner
from services.api.app.services.rapid_design.model_adapter import AerodynamicModelAdapter
from services.api.app.services.rapid_design.optimizer import optimize_design
from services.api.app.services.rapid_design.result_store import RapidDesignResultStore


def _fast_config():
    config = load_rapid_design_config()
    return config.model_copy(
        update={
            "aerodynamics": config.aerodynamics.model_copy(update={"backend": "analytic"}),
            "optimizer": config.optimizer.model_copy(
                update={"max_iterations": 2, "population_size": 3}
            ),
        }
    )


def test_config_defines_adjustable_requirements_and_constraints():
    config = load_rapid_design_config()
    keys = {item.key for item in config.inputs}
    assert {
        "required_range_km",
        "payload_mass_kg",
        "cruise_speed_kmh",
        "cruise_altitude_m",
        "max_fuel_mass_kg",
        "max_takeoff_mass_kg",
        "target_lift_to_drag",
    } == keys
    assert {item.kind for item in config.inputs} == {"requirement", "constraint"}


def test_input_validation_fills_defaults_and_rejects_out_of_range():
    config = load_rapid_design_config()
    values = validated_inputs(config, {"required_range_km": 900})
    assert values["required_range_km"] == 900
    assert values["payload_mass_kg"] == 100
    with pytest.raises(ValueError, match="required_range_km"):
        validated_inputs(config, {"required_range_km": 20})


def test_neuralfoil_adapter_returns_published_model_output():
    config = load_rapid_design_config()
    model = AerodynamicModelAdapter(config.aerodynamics)
    result = model.evaluate(
        camber=0.02,
        camber_position=0.4,
        thickness=0.12,
        reynolds_number=1_200_000,
        required_lift_coefficient=0.45,
    )
    assert result.profile_drag_coefficient > 0
    assert result.max_lift_coefficient > result.lift_coefficient
    assert 0 <= result.analysis_confidence <= 1
    assert model.provenance["name"] == "NeuralFoil"
    assert model.provenance["license"] == "MIT"


def test_optimizer_returns_constraints_and_aerospec_geometry():
    config = _fast_config()
    result = optimize_design(
        job_id="unit-test-job",
        inputs=validated_inputs(config, {}),
        config=config,
    )
    assert result["status"] == "feasible"
    assert all(item["satisfied"] for item in result["constraints"])
    assert len(result["convergence"]) == 2
    AircraftSpec.model_validate(result["aircraft_spec"])


def test_evaluator_reports_infeasible_range_explicitly():
    config = _fast_config()
    inputs = validated_inputs(config, {"required_range_km": 3000})
    design = {
        item.key: (
            item.minimum + min(item.maximum, inputs.get(item.input_upper_bound, item.maximum))
        )
        / 2
        for item in config.design_variables
    }
    result = evaluate_design(
        design,
        inputs,
        config,
        AerodynamicModelAdapter(config.aerodynamics),
    )
    range_constraint = next(item for item in result["constraints"] if item["name"] == "range")
    assert range_constraint["satisfied"] is False
    assert range_constraint["margin"] < 0


def test_api_job_persists_and_returns_result(tmp_path, monkeypatch):
    from services.api.app.main import app
    from services.api.app.routers import rapid_design as rapid_router

    local_runner = RapidDesignJobRunner(
        config=_fast_config(),
        store=RapidDesignResultStore(tmp_path / "rapid-design"),
    )
    monkeypatch.setattr(rapid_router, "runner", local_runner)
    client = TestClient(app)

    response = client.post("/api/rapid-design/jobs", json={"inputs": {}})
    assert response.status_code == 202
    job = response.json()
    for _ in range(100):
        job = client.get(f"/api/rapid-design/jobs/{job['id']}").json()
        if job["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.03)

    assert job["status"] == "succeeded"
    result_response = client.get(f"/api/rapid-design/jobs/{job['id']}/result")
    assert result_response.status_code == 200
    assert result_response.json()["model_provenance"]["name"] == "analytic-test-model"
    assert (tmp_path / "rapid-design" / "jobs" / job["id"] / "result.json").exists()
    assert (tmp_path / "rapid-design" / "jobs" / job["id"] / "config.json").exists()
