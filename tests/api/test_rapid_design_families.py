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
    assert len(components["fuselage"]["stations"]) >= 12
    assert len(components["main_wing"]["sections"]) >= 6
    tail_surfaces = [
        component
        for component in state["components"]
        if component["kind"] == "lifting_surface" and component["id"] != "main_wing"
    ]
    assert tail_surfaces
    assert all(len(component["sections"]) >= 4 for component in tail_surfaces)
    if preset_id == "long_endurance_uav":
        assert {component["id"] for component in tail_surfaces} == {"v_tail"}
        assert tail_surfaces[0]["sections"][-1]["leading_edge_z_m"] > 1.0
    else:
        assert any(component["orientation"] == "vertical" for component in tail_surfaces)
    assert any(component["kind"] == "nacelle" for component in state["components"])
    assert "wing_root_fairing" in components
    assert state["provenance"]["archetype_id"]
    assert state["provenance"]["reference_basis"]
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


def _normalized_geometry_signature(result: dict) -> tuple:
    components = {
        component["id"]: component
        for component in result["geometry_state"]["components"]
    }
    body = components["fuselage"]["stations"]
    length = body[-1]["x_m"] - body[0]["x_m"]
    maximum_width = max(station["width_m"] for station in body)
    maximum_height = max(station["height_m"] for station in body)
    body_signature = tuple(
        (
            round((station["x_m"] - body[0]["x_m"]) / length, 3),
            round(station["width_m"] / maximum_width, 3),
            round(station["height_m"] / maximum_height, 3),
            round(station["z_offset_m"] / maximum_height, 3),
            round(station["shape_exponent"], 2),
        )
        for station in body
    )
    wing = components["main_wing"]["sections"]
    semi_span = wing[-1]["y_m"]
    root_chord = wing[0]["chord_m"]
    root_x = wing[0]["leading_edge_x_m"]
    wing_signature = tuple(
        (
            round(section["y_m"] / semi_span, 3),
            round(section["chord_m"] / root_chord, 3),
            round((section["leading_edge_x_m"] - root_x) / semi_span, 3),
            section["airfoil_id"],
        )
        for section in wing
    )
    tail_topology = tuple(
        sorted(
            component["id"]
            for component in result["geometry_state"]["components"]
            if component["kind"] == "lifting_surface" and component["id"] != "main_wing"
        )
    )
    return body_signature, wing_signature, tail_topology


def test_archetype_grammar_remains_distinct_for_the_same_continuous_design(
    client: TestClient,
    condition: dict[str, float | int],
):
    manifest = client.get("/api/rapid-design/families/conventional_v2").json()
    shared_design = next(
        preset["design"]
        for preset in manifest["presets"]
        if preset["preset_id"] == "long_endurance_uav"
    )
    signatures = set()
    for preset_id in (
        "long_endurance_uav",
        "fast_cruise_recon",
        "payload_utility",
    ):
        response = client.post(
            "/api/rapid-design/analyze",
            json={
                "family_id": "conventional_v2",
                "preset_id": preset_id,
                "design": shared_design,
                "condition": condition,
            },
        )
        assert response.status_code == 200, response.text
        signatures.add(_normalized_geometry_signature(response.json()))
    assert len(signatures) == 3


def test_conventional_manifest_documents_archetype_and_public_ratio_basis(
    client: TestClient,
):
    manifest = client.get("/api/rapid-design/families/conventional_v2").json()
    assert manifest["version"] == "0.2.0"
    for preset in manifest["presets"]:
        assert preset["archetype_id"]
        reference = preset["reference_basis"]
        assert reference["source_url"].startswith("https://")
        assert reference["published_length_m"] > 0
        assert reference["published_span_m"] > 0
        assert "anchor" in reference["usage_note"].lower()


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
