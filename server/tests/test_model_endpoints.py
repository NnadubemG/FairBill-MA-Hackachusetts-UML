"""Extract/letter endpoint behavior with Anthropic mocked.

Covers: missing-model-config -> 503 ApiError (Req 4.4), and a successful
extract that parses mocked model JSON into the contract shape.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from contracts import ExtractResponse


def _fresh_client(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import app.config as config

    config._settings = None  # type: ignore[attr-defined]
    from app.main import app

    return TestClient(app)


def test_extract_missing_model_returns_503(monkeypatch):
    # Key present but no EXTRACT_MODEL_ID -> endpoint-specific 503, service up.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("EXTRACT_MODEL_ID", raising=False)
    client = _fresh_client(monkeypatch)
    r = client.post("/api/extract", json={"text": "some bill text"})
    assert r.status_code == 503
    assert r.json()["error"] == "extract_model_not_configured"
    # Service still healthy.
    assert client.get("/api/health").status_code == 200


def test_extract_parses_model_json(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("EXTRACT_MODEL_ID", "claude-test")
    import app.config as config

    config._settings = None  # type: ignore[attr-defined]

    from app import anthropic_client

    def fake_complete(**kwargs):
        return (
            '{"line_items":[{"code":"99213","description":"Office visit",'
            '"units":1,"charge":30000,"confidence":0.92,'
            '"needs_confirmation":false}],"overall_confidence":0.9}'
        )

    monkeypatch.setattr(anthropic_client, "complete", fake_complete)

    from app.main import app

    client = TestClient(app)
    r = client.post("/api/extract", json={"text": "bill"})
    assert r.status_code == 200
    model = ExtractResponse.model_validate(r.json())
    assert model.line_items[0].code == "99213"
    assert model.line_items[0].charge == 30000
    assert 0.0 <= model.overall_confidence <= 1.0


def test_extract_bad_model_output_returns_502(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("EXTRACT_MODEL_ID", "claude-test")
    import app.config as config

    config._settings = None  # type: ignore[attr-defined]

    from app import anthropic_client

    monkeypatch.setattr(
        anthropic_client, "complete", lambda **kw: "not json at all"
    )

    from app.main import app

    client = TestClient(app)
    r = client.post("/api/extract", json={"text": "bill"})
    assert r.status_code == 502
    assert r.json()["error"] == "extract_bad_model_output"
