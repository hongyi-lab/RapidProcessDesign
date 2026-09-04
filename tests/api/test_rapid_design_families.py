from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from services.api.app.schemas.rapid_design import GeometryState


@pytest.fixture
def client() -> TestClient:
    from services.api.app.main import app

    return TestClient(app)


@pytest.fixture
def condition() -> dict[str, float | int]:
    return {
        "altitude_m": 2000.0,
        "speed_kmh": 220.0,
        "alpha_min_deg": -4.0,
        "alpha_max_deg": 12.0,
        "alpha_samples": 25,
    }


def test_family_discovery_returns_two_full_manifests(client: TestClient):
    response = client.get("/api/rapid-design/families")

    assert response.status_code == 200
    families = response.json()["families"]
    assert {family["family_id"] for family in families} == {
        "bwb_v1",
        "conventional_v2",
    }
    for family in families:
        assert family["presets"]
        assert family["design_parameters"]
        assert family["condition_parameters"]
        assert family["capabilities"] == {
            "geometry": True,
            "analyze": True,
            "optimize": False,
        }
        assert family["optimization_status"] == "pending_teacher_decision"
        preset_ids = {preset["preset_id"] for preset in family["presets"]}
        assert family["default_preset_id"] in preset_ids
        assert len({item["key"] for item in family["design_parameters"]}) == len(
            family["design_parameters"]
        )


def test_family_detail_and_unknown_family(client: TestClient):
    detail = client.get("/api/rapid-design/families/conventional_v2")
    missing = client.get("/api/rapid-design/families/not_registered")

    assert detail.status_code == 200
    assert detail.json()["family_id"] == "conventional_v2"
    assert len(detail.json()["presets"]) == 3
    assert missing.status_code == 404


def test_registry_dispatches_both_families_to_common_envelope(
    client: TestClient,
    condition: dict[str, float | int],
):
    for family_id, preset_id in (
        ("bwb_v1", "balanced_concept"),
        ("conventional_v2", "long_endurance_uav"),
    ):
        response = client.post(
            "/api/rapid-design/analyze",
            json={
                "family_id": family_id,
                "preset_id": preset_id,
                "design": {},
                "condition": condition,
            },
        )

        assert response.status_code == 200
        result = response.json()
        assert result["family_id"] == family_id
        assert result["preset_id"] == preset_id
        assert result["geometry_state"]["family_id"] == family_id
        assert result["geometry_state"]["geometry_status"] == "valid"
        assert result["geometry_metrics"] == result["geometry"]
        assert result["analysis"]["polar"] == result["polar"]
        assert result["analysis"]["summary"] == result["summary"]
        assert result["fidelity"] == "conceptual_low_order"


def test_geometry_state_schema_rejects_unordered_stations():
    with pytest.raises(ValidationError, match="strictly increase"):
        GeometryState.model_validate(
            {
                "family_id": "conventional_v2",
                "geometry_version": "test",
                "components": [
                    {
                        "id": "body",
                        "kind": "loft_body",
                        "stations": [
                            {
                                "x_m": 1.0,
                                "width_m": 0.0,
                                "height_m": 0.0,
                            },
                            {
                                "x_m": 0.0,
                                "width_m": 0.0,
                                "height_m": 0.0,
                            },
                        ],
                    }
                ],
                "derived_metrics": {},
                "geometry_status": "invalid",
                "geometry_checks": [],
                "provenance": {
                    "decoder_id": "test",
                    "decoder_version": "test",
                    "methodology": "test",
                },
            }
        )


@pytest.mark.parametrize(
    "preset_id",
    ["long_endurance_uav", "fast_cruise_recon", "payload_utility"],
)
def test_conventional_presets_generate_complete_valid_geometry(
    client: TestClient,
    condition: dict[str, float | int],
    preset_id: str,
):
    response = client.post(
        "/api/rapid-design/analyze",
        json={
            "family_id": "conventional_v2",
            "preset_id": preset_id,
            "design": {},
            "condition": condition,
        },
    )

    assert response.status_code == 200
    result = response.json()
    state = result["geometry_state"]
    components = {component["id"]: component for component in state["components"]}
    assert state["geometry_status"] == "valid"
    assert all(check["status"] == "pass" for check in state["geometry_checks"])
    assert len(components["fuselage"]["stations"]) >= 8
    assert len(components["main_wing"]["sections"]) >= 4
    assert len(components["horizontal_tail"]["sections"]) >= 3
    assert len(components["vertical_tail"]["sections"]) >= 3
    assert components["vertical_tail"]["orientation"] == "vertical"
    assert any(component["kind"] == "nacelle" for component in state["components"])
    assert result["geometry_metrics"]["reference_area_m2"] > 0
    assert result["summary"]["max_ld"] > 0
    assert "Conceptual trend estimate" in " ".join(result["warnings"])


def test_conventional_presets_are_geometrically_distinct(
    client: TestClient,
    condition: dict[str, float | int],
):
    results = {}
    for preset_id in (
        "long_endurance_uav",
        "fast_cruise_recon",
        "payload_utility",
    ):
        results[preset_id] = client.post(
            "/api/rapid-design/analyze",
            json={
                "family_id": "conventional_v2",
                "preset_id": preset_id,
                "design": {},
                "condition": condition,
            },
        ).json()

    signatures = {
        (
            result["geometry_metrics"]["span_m"],
            result["geometry_metrics"]["aspect_ratio"],
            next(
                component["id"]
                for component in result["geometry_state"]["components"]
                if component["kind"] == "nacelle"
            ),
        )
        for result in results.values()
    }
    assert len(signatures) == 3


def test_every_conventional_control_changes_canonical_geometry(
    client: TestClient,
    condition: dict[str, float | int],
):
    manifest = client.get("/api/rapid-design/families/conventional_v2").json()
    preset = next(
        item
        for item in manifest["presets"]
        if item["preset_id"] == "long_endurance_uav"
    )
    baseline_payload = {
        "family_id": "conventional_v2",
        "preset_id": preset["preset_id"],
        "design": preset["design"],
        "condition": condition,
    }
    baseline = client.post(
        "/api/rapid-design/analyze", json=baseline_payload
    ).json()

    for definition in manifest["design_parameters"]:
        payload = deepcopy(baseline_payload)
        key = definition["key"]
        current = payload["design"][key]
        increment = definition["step"]
        candidate = current + increment
        if candidate > definition["maximum"]:
            candidate = current - increment
        payload["design"][key] = candidate
        response = client.post("/api/rapid-design/analyze", json=payload)

        assert response.status_code == 200, key
        result = response.json()
        assert result["design_hash"] != baseline["design_hash"], key
        assert result["geometry_state"] != baseline["geometry_state"], key


def test_preset_overrides_are_merged_and_invalid_requests_are_explicit(
    client: TestClient,
    condition: dict[str, float | int],
):
    changed = client.post(
        "/api/rapid-design/analyze",
        json={
            "family_id": "conventional_v2",
            "preset_id": "payload_utility",
            "design": {"wing_span_m": 17.0},
            "condition": condition,
        },
    )
    unknown_preset = client.post(
        "/api/rapid-design/analyze",
        json={
            "family_id": "conventional_v2",
            "preset_id": "not_a_preset",
            "design": {},
            "condition": condition,
        },
    )
    out_of_range = client.post(
        "/api/rapid-design/analyze",
        json={
            "family_id": "conventional_v2",
            "preset_id": "payload_utility",
            "design": {"wing_span_m": 31.0},
            "condition": condition,
        },
    )

    assert changed.status_code == 200
    assert changed.json()["geometry_metrics"]["span_m"] == 17.0
    assert unknown_preset.status_code == 422
    assert "unknown conventional_v2 preset" in unknown_preset.text
    assert out_of_range.status_code == 422
    assert "wing_span_m" in out_of_range.text

