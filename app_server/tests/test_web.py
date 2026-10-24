"""Tests for the web layer: /samples, static file serving, and the Lambda adapter.

Offline and pure: no sockets, no network. The Lambda handler is given a prebuilt
context so no real model client or AWS call is involved.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

import app_server.lambda_handler as lh
from app_server.app import (
    SECURITY_HEADERS,
    AppContext,
    load_samples,
    route,
    static_file,
)
from backend.analyze.store import ReferenceStore
from backend.compare.store import Store as CompareStore
from backend.extract.llm_client import FakeLLMClient

REPO = Path(__file__).resolve().parents[2]
COMPARE_FIXTURES = REPO / "backend" / "compare" / "tests" / "fixtures" / "processed"


@pytest.fixture
def ctx():
    return AppContext(
        compare_store=CompareStore.load(COMPARE_FIXTURES),
        analyze_store=ReferenceStore.from_dicts(price_references=[], quantity_limits=[], bundle_pairs=[]),
        client=FakeLLMClient(default=""),
        model_is_real=False,
        samples=load_samples(),
    )


# ---------------------------------------------------------------- samples
def test_samples_are_labeled_and_exclude_injection_fixture():
    samples = load_samples()
    assert samples, "synthetic samples should load"
    scenarios = {s["scenario"] for s in samples}
    assert "injection" not in scenarios
    for s in samples:
        assert s["label"].startswith("Sample:")
        assert s["line_items"]
        # Only line items + metadata leave the server; no synthetic answers.
        assert set(s) == {"id", "label", "scenario", "metadata", "line_items"}


def test_samples_route(ctx):
    status, payload = route(ctx, "GET", "/samples", {}, None)
    assert status == 200
    assert payload["samples"] and "fictional" in payload["note"]


def test_sample_bill_analyzes_against_real_store(ctx):
    sample = next(s for s in load_samples() if s["scenario"] == "duplicate")
    status, payload = route(ctx, "POST", "/analyze", {}, {"line_items": sample["line_items"]})
    assert status == 200
    assert any(f["flag_type"] == "duplicate_line_item" for f in payload["flags"])


# ---------------------------------------------------------------- static files
def test_root_serves_app_shell():
    ct, body = static_file("/")
    assert ct.startswith("text/html")
    assert b"/app/main.mjs" in body


@pytest.mark.parametrize("path", ["/app/main.mjs", "/app/styles.css", "/src/compare/compare.mjs"])
def test_public_assets_served(path):
    assert static_file(path) is not None


@pytest.mark.parametrize(
    "path",
    [
        "/../pipeline/config.py",
        "/app/../../pipeline/config.py",
        "/app/..%2f..%2fREADME.md",
        "/src/compare/tests/render.test.mjs",
        "/app/tests/logic.test.mjs",
        "/src/compare/README.md",
        "/data/processed/prices.json",
        "/app/missing.css",
        "/.env",
        "/app/../../data/processed/prices.json",
        "/app/../index.html",
        "/app/.hidden.css",
        "/app\\..\\index.html",
    ],
)
def test_private_or_unsafe_paths_rejected(path):
    assert static_file(path) is None


def test_traversal_with_custom_root(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "ok.css").write_text("a{}")
    (tmp_path / "secret.css").write_text("x")
    assert static_file("/app/ok.css", tmp_path) is not None
    assert static_file("/app/../secret.css", tmp_path) is None


# ---------------------------------------------------------------- lambda adapter
def _event(method, path, body=None, query="", b64=False):
    raw = json.dumps(body) if body is not None else None
    if raw is not None and b64:
        raw = base64.b64encode(raw.encode()).decode()
    return {
        "rawPath": path,
        "rawQueryString": query,
        "requestContext": {"http": {"method": method}},
        "body": raw,
        "isBase64Encoded": b64,
    }


@pytest.fixture
def lam(ctx, monkeypatch):
    monkeypatch.setattr(lh, "_CTX", ctx)
    return lh.handler


def test_lambda_health_and_security_headers(lam):
    res = lam(_event("GET", "/health"))
    assert res["statusCode"] == 200
    assert json.loads(res["body"])["status"] == "ok"
    for k in SECURITY_HEADERS:
        assert k in res["headers"]
    assert res["headers"]["Cache-Control"] == "no-store"


def test_lambda_serves_static(lam):
    res = lam(_event("GET", "/"))
    assert res["statusCode"] == 200
    assert res["headers"]["Content-Type"].startswith("text/html")
    assert "FairBill" in res["body"]


def test_lambda_compare_query(lam):
    res = lam(_event("GET", "/compare", query="code=99213"))
    assert res["statusCode"] == 200
    assert json.loads(res["body"])["found"] is True


def test_lambda_post_base64_body(lam):
    items = [{"id": "1", "description": "Visit", "billed_amount": 100.0, "code": "99213"}]
    res = lam(_event("POST", "/analyze", {"line_items": items}, b64=True))
    assert res["statusCode"] == 200
    assert json.loads(res["body"])["line_items"][0]["id"] == "1"


def test_lambda_bad_json(lam):
    ev = _event("POST", "/analyze")
    ev["body"] = "{not json"
    assert lam(ev)["statusCode"] == 400


def test_lambda_body_too_large(lam):
    ev = _event("POST", "/extract")
    ev["body"] = "x" * (lh.MAX_BODY_BYTES + 1)
    assert lam(ev)["statusCode"] == 413


def test_lambda_internal_error_is_generic(lam, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("secret detail")
    monkeypatch.setattr(lh, "route", boom)
    res = lam(_event("GET", "/health"))
    assert res["statusCode"] == 500
    assert "secret" not in res["body"]


def test_secret_loader_noop_without_arn(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_SECRET_ARN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    lh._load_api_key_from_secret()
    import os
    assert "ANTHROPIC_API_KEY" not in os.environ
