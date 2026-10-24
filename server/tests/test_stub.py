"""Stub smoke tests (TC-1 and basic SPA/API behavior)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    # TC-1: health check returns 200 and minimal JSON.
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_unknown_api_path_is_json_404_not_spa():
    # /api/* must never fall back to the SPA.
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404
    assert r.json() == {"error": "not_found"}
    assert "text/html" not in r.headers.get("content-type", "")


def test_root_serves_frontend():
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert "Medical-Bill Helper" in r.text
