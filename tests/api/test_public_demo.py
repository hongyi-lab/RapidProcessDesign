import time

import pytest
from fastapi.testclient import TestClient

from services.api.app.public_demo import COOKIE_NAME, create_app

BASE = "/api/rapid-design"


@pytest.fixture
def public_app(tmp_path):
    app = create_app(tmp_path)
    yield app
    app.state.demo_runner.shutdown()


def wait_for_result(client, job_id):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        status = client.get(f"{BASE}/demo/jobs/{job_id}").json()
        if status["status"] == "succeeded":
            return client.get(f"{BASE}/demo/jobs/{job_id}/result").json()
        assert status["status"] not in {"failed", "cancelled"}, status
        time.sleep(0.03)
    pytest.fail("public demo generation did not finish")


def test_public_surface_excludes_private_workspaces_and_legacy(public_app):
    client = TestClient(public_app, base_url="https://demo.test")
    for path in ("/health", f"{BASE}/families", f"{BASE}/demo/config"):
        response = client.get(path)
        assert response.status_code == 200
        assert "set-cookie" not in response.headers
    for path in ("/api/conversations", "/api/settings", f"{BASE}/config", f"{BASE}/jobs"):
        assert client.get(path).status_code == 404
    assert client.post(f"{BASE}/jobs", json={"inputs": {}}).status_code == 404


@pytest.mark.parametrize("preset", ["long_endurance_uav", "fast_cruise_recon", "payload_utility"])
def test_generated_jobs_events_and_results_belong_to_their_browser(public_app, preset):
    owner = TestClient(public_app, base_url="https://demo.test")
    stranger = TestClient(public_app, base_url="https://demo.test")
    assert stranger.get(f"{BASE}/demo/jobs").json()["jobs"] == []
    created = owner.post(f"{BASE}/demo/jobs", json={
        "mode": "demo",
        "family_id": "conventional_v2", "preset_id": preset,
        "inputs": {"required_range_km": 1000, "payload_mass_kg": 150},
    })
    assert created.status_code == 202, created.text
    cookie = created.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    job_id = created.json()["id"]
    result = wait_for_result(owner, job_id)
    assert result["candidates"]
    assert all(candidate["geometry_state"]["components"] for candidate in result["candidates"])
    assert owner.get(f"{BASE}/demo/jobs").json()["jobs"][0]["id"] == job_id
    assert stranger.get(f"{BASE}/demo/jobs").json()["jobs"] == []
    for suffix in ("", "/result", "/events"):
        response = stranger.get(f"{BASE}/demo/jobs/{job_id}{suffix}")
        assert response.status_code == 404
        assert response.headers["cache-control"] == "no-store"
    assert stranger.post(f"{BASE}/demo/jobs/{job_id}/cancel").status_code == 404
    events = owner.get(f"{BASE}/demo/jobs/{job_id}/events")
    assert events.status_code == 200 and "event: completed" in events.text

    restored = TestClient(public_app, base_url="https://demo.test")
    restored.cookies.set(COOKIE_NAME, owner.cookies.get(COOKIE_NAME))
    assert restored.get(f"{BASE}/demo/jobs/{job_id}/result").status_code == 200


def test_analyze_remains_available_without_registration(public_app):
    client = TestClient(public_app, base_url="https://demo.test")
    response = client.post(f"{BASE}/analyze", json={
        "family_id": "conventional_v2", "preset_id": "fast_cruise_recon",
        "design": {}, "condition": {
            "altitude_m": 2000, "speed_kmh": 220,
            "alpha_min_deg": -4, "alpha_max_deg": 12, "alpha_samples": 25,
        },
    })
    assert response.status_code == 200, response.text
    assert response.json()["geometry_state"]["components"]


def test_busy_demo_rejects_extra_work(public_app, monkeypatch):
    client = TestClient(public_app, base_url="https://demo.test")
    monkeypatch.setattr(public_app.state.demo_runner, "list_recent", lambda **_: [
        {"id": str(index), "status": "queued"} for index in range(4)
    ])
    response = client.post(f"{BASE}/demo/jobs", json={
        "mode": "demo",
        "family_id": "conventional_v2", "preset_id": "fast_cruise_recon", "inputs": {},
    })
    assert response.status_code == 503
    assert "busy" in response.json()["detail"]
