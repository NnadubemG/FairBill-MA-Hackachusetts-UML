"""TC-4: CORS.

With ALLOWED_ORIGINS set to one origin, that origin is echoed in
Access-Control-Allow-Origin; a disallowed origin is not; `*` is never returned.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture()
def client_with_origin(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://allowed.example")

    import app.config as config

    config._settings = None  # type: ignore[attr-defined]

    import app.main as main

    importlib.reload(main)
    from fastapi.testclient import TestClient

    yield TestClient(main.app)

    # Reset for other tests.
    config._settings = None  # type: ignore[attr-defined]
    importlib.reload(main)


def test_allowed_origin_is_echoed(client_with_origin):
    r = client_with_origin.options(
        "/api/health",
        headers={
            "Origin": "https://allowed.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    acao = r.headers.get("access-control-allow-origin")
    assert acao == "https://allowed.example"
    assert acao != "*"


def test_disallowed_origin_not_echoed(client_with_origin):
    r = client_with_origin.options(
        "/api/health",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    acao = r.headers.get("access-control-allow-origin")
    assert acao != "https://evil.example"
    assert acao != "*"
