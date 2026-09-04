from copy import deepcopy

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    from services.api.app.main import app

    return TestClient(app)


@pytest.fixture
def analyze_payload() -> dict[str, object]:
    return {
        "family_id": "bwb_v1",
        "design": {
            "c1_m": 6.0,
            "c2_ratio": 0.78,
            "c3_ratio": 0.48,
            "c4_ratio": 0.18,
            "b1_ratio": 0.32,
            "b2_ratio": 0.45,
            "b3_ratio": 0.70,
            "x3_ratio": 0.25,
            "sweep_inner_deg": 38.0,
            "sweep_outer_deg": 28.0,
            "thickness_ratio": 0.12,
            "twist_tip_deg": -2.0,
        },
        "condition": {
            "altitude_m": 2000.0,
            "speed_kmh": 220.0,
            "alpha_min_deg": -4.0,
            "alpha_max_deg": 12.0,
            "alpha_samples": 33,
        },
    }


def test_bwb_analyze_returns_clean_room_aircraft_polar(
    client: TestClient,
    analyze_payload: dict[str, object],
):
    response = client.post("/api/rapid-design/analyze", json=analyze_payload)

    assert response.status_code == 200
    result = response.json()
    assert result["family_id"] == "bwb_v1"
    assert result["domain_status"]["status"] == "in_domain"
    assert result["geometry"]["reference_area_m2"] > 0
    assert result["geometry"]["aspect_ratio"] > 0
    assert result["summary"]["reynolds_number"] > 0
    assert result["summary"]["max_ld"] > 0
    assert result["fidelity"] == "conceptual_low_order"
    assert result["provenance"]["uses_external_weights"] is False
    assert result["provenance"]["uses_mit_assets"] is False
    assert result["provenance"]["geometry_decoder_id"] == "clean-room-bwb-loft"
    assert result["provenance"]["geometry_decoder_version"] == "1.0.0"
    assert "Clean-room" in " ".join(result["warnings"])


def test_smooth_geometry_matches_browser_known_values_for_default_and_extreme(
    client: TestClient,
    analyze_payload: dict[str, object],
):
    extreme_design = {
        "c1_m": 6.0,
        "c2_ratio": 0.55,
        "c3_ratio": 0.25,
        "c4_ratio": 0.08,
        "b1_ratio": 0.15,
        "b2_ratio": 0.80,
        "b3_ratio": 1.20,
        "x3_ratio": 0.0,
        "sweep_inner_deg": 20.0,
        "sweep_outer_deg": 15.0,
        "thickness_ratio": 0.12,
        "twist_tip_deg": 0.0,
    }
    expected_cases = (
        (
            analyze_payload["design"],
            {
                "reference_area_m2": 57.488283,
                "span_m": 17.64,
                "semi_span_m": 8.82,
                "aspect_ratio": 5.41274819,
                "mean_aerodynamic_chord_m": 3.929971,
                "wetted_area_m2": 116.127898,
                "taper_ratio": 0.18,
                "volume_proxy_m3": 16.80899,
            },
        ),
        (
            extreme_design,
            {
                "reference_area_m2": 42.869631,
                "span_m": 25.8,
                "semi_span_m": 12.9,
                "aspect_ratio": 15.52707545,
                "mean_aerodynamic_chord_m": 2.395523,
                "wetted_area_m2": 86.514229,
                "taper_ratio": 0.08,
                "volume_proxy_m3": 7.640522,
            },
        ),
    )

    for design, expected in expected_cases:
        payload = deepcopy(analyze_payload)
        payload["design"] = design
        response = client.post("/api/rapid-design/analyze", json=payload)

        assert response.status_code == 200
        assert response.json()["geometry"] == expected


def test_derived_domain_checks_report_out_of_domain_without_blocking_analysis(
    client: TestClient,
    analyze_payload: dict[str, object],
):
    payload = deepcopy(analyze_payload)
    assert isinstance(payload["design"], dict)
    payload["design"].update(
        {
            "c2_ratio": 0.55,
            "c3_ratio": 0.25,
            "c4_ratio": 0.08,
            "b1_ratio": 0.60,
            "b2_ratio": 0.80,
            "b3_ratio": 1.20,
        }
    )

    response = client.post("/api/rapid-design/analyze", json=payload)

    assert response.status_code == 200
    result = response.json()
    checks = {check["name"]: check for check in result["domain_status"]["checks"]}
    assert result["domain_status"]["status"] == "out_of_domain"
    assert checks["derived.aspect_ratio"]["status"] == "fail"
    assert checks["derived.mach"]["status"] == "pass"
    assert checks["derived.reynolds_number"]["status"] == "pass"
    assert any("aspect ratio" in warning for warning in result["warnings"])


@pytest.mark.parametrize(
    ("path", "invalid_value"),
    [
        (("design", "c1_m"), 1.99),
        (("design", "sweep_outer_deg"), 45.01),
        (("condition", "altitude_m"), 11_001.0),
        (("condition", "alpha_samples"), 82),
    ],
)
def test_bwb_analyze_rejects_values_outside_hard_ranges(
    client: TestClient,
    analyze_payload: dict[str, object],
    path: tuple[str, str],
    invalid_value: float,
):
    payload = deepcopy(analyze_payload)
    section = payload[path[0]]
    assert isinstance(section, dict)
    section[path[1]] = invalid_value

    response = client.post("/api/rapid-design/analyze", json=payload)

    assert response.status_code == 422


def test_bwb_analyze_rejects_invalid_relations_and_family(
    client: TestClient,
    analyze_payload: dict[str, object],
):
    bad_chords = deepcopy(analyze_payload)
    assert isinstance(bad_chords["design"], dict)
    bad_chords["design"]["c3_ratio"] = 0.60
    bad_chords["design"]["c2_ratio"] = 0.58
    assert client.post("/api/rapid-design/analyze", json=bad_chords).status_code == 422

    bad_alpha = deepcopy(analyze_payload)
    assert isinstance(bad_alpha["condition"], dict)
    bad_alpha["condition"]["alpha_min_deg"] = 10.0
    bad_alpha["condition"]["alpha_max_deg"] = 5.0
    assert client.post("/api/rapid-design/analyze", json=bad_alpha).status_code == 422

    bad_family = deepcopy(analyze_payload)
    bad_family["family_id"] = "conventional_uav_v1"
    assert client.post("/api/rapid-design/analyze", json=bad_family).status_code == 422


def test_bwb_analyze_polar_arrays_match_requested_sample_count(
    client: TestClient,
    analyze_payload: dict[str, object],
):
    payload = deepcopy(analyze_payload)
    assert isinstance(payload["condition"], dict)
    payload["condition"]["alpha_samples"] = 17

    result = client.post("/api/rapid-design/analyze", json=payload).json()

    assert result["polar"]["alpha_deg"][0] == -4.0
    assert result["polar"]["alpha_deg"][-1] == 12.0
    assert {len(values) for values in result["polar"].values()} == {17}


def test_bwb_analyze_hash_is_stable_for_equivalent_requests(
    client: TestClient,
    analyze_payload: dict[str, object],
):
    first = client.post("/api/rapid-design/analyze", json=analyze_payload)
    reordered = {
        "condition": dict(reversed(list(analyze_payload["condition"].items()))),
        "design": dict(reversed(list(analyze_payload["design"].items()))),
        "family_id": "bwb_v1",
    }
    second = client.post("/api/rapid-design/analyze", json=reordered)

    assert first.status_code == second.status_code == 200
    assert first.json()["design_hash"] == second.json()["design_hash"]
    assert first.json() == second.json()


def test_bwb_hash_versions_geometry_decoder_and_performance_model(
    analyze_payload: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
):
    from services.api.app.schemas.rapid_design import RapidAnalyzeRequest
    from services.api.app.services.rapid_design import bwb_analysis

    request = RapidAnalyzeRequest.model_validate(analyze_payload)
    baseline_hash = bwb_analysis.design_hash(request)

    monkeypatch.setattr(bwb_analysis, "GEOMETRY_DECODER_VERSION", "test-version")
    geometry_version_hash = bwb_analysis.design_hash(request)
    monkeypatch.setattr(bwb_analysis, "GEOMETRY_DECODER_VERSION", "1.0.0")
    monkeypatch.setattr(bwb_analysis, "MODEL_VERSION", "test-version")
    performance_version_hash = bwb_analysis.design_hash(request)

    assert geometry_version_hash != baseline_hash
    assert performance_version_hash != baseline_hash
    assert geometry_version_hash != performance_version_hash


def test_each_open_bwb_variable_changes_geometry_and_aircraft_polar(
    client: TestClient,
    analyze_payload: dict[str, object],
):
    baseline = client.post("/api/rapid-design/analyze", json=analyze_payload).json()
    increments = {
        "c1_m": 0.1,
        "c2_ratio": 0.01,
        "c3_ratio": 0.01,
        "c4_ratio": 0.01,
        "b1_ratio": 0.01,
        "b2_ratio": 0.01,
        "b3_ratio": 0.01,
        "x3_ratio": 0.01,
        "sweep_inner_deg": 1.0,
        "sweep_outer_deg": 1.0,
        "thickness_ratio": 0.005,
        "twist_tip_deg": 0.25,
    }

    for name, increment in increments.items():
        payload = deepcopy(analyze_payload)
        assert isinstance(payload["design"], dict)
        payload["design"][name] += increment
        response = client.post("/api/rapid-design/analyze", json=payload)

        assert response.status_code == 200, name
        result = response.json()
        assert result["geometry"] != baseline["geometry"], name
        assert result["polar"] != baseline["polar"], name
        assert result["design_hash"] != baseline["design_hash"], name
