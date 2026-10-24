"""Tests for the pure routing core. Offline (FakeLLMClient), no network.

Builds an AppContext from the committed compare fixtures (real processed JSON) and a
synthetic sample bill, and exercises each route through route().
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from app_server.app import AppContext, route
from backend.analyze.store import ReferenceStore
from backend.compare.store import Store as CompareStore
from backend.extract.llm_client import FakeLLMClient
from pipeline import jsonio

REPO = Path(__file__).resolve().parents[2]
COMPARE_FIXTURES = REPO / "backend" / "compare" / "tests" / "fixtures" / "processed"
SAMPLE_BILL = REPO / "synthetic" / "samples" / "bill-duplicate-1.json"


@pytest.fixture
def ctx():
    bill = jsonio.read_json(SAMPLE_BILL)
    return AppContext(
        compare_store=CompareStore.load(COMPARE_FIXTURES),
        analyze_store=ReferenceStore.from_dicts(
            price_references=bill.get("price_references", []),
            quantity_limits=bill.get("quantity_limits", []),
            bundle_pairs=bill.get("bundle_pairs", []),
        ),
        client=FakeLLMClient(default=""),  # offline
        model_is_real=False,
    )


def test_health(ctx):
    status, payload = route(ctx, "GET", "/health", {}, None)
    assert status == 200
    assert payload["status"] == "ok"
    assert payload["model"] == "offline-fallback"


def test_procedures(ctx):
    status, payload = route(ctx, "GET", "/procedures", {}, None)
    assert status == 200
    assert "procedures" in payload and "framing_note" in payload


def test_compare_known_code(ctx):
    status, payload = route(ctx, "GET", "/compare", {"code": ["99213"]}, None)
    assert status == 200
    assert payload["found"] is True
    assert payload["hospitals"]


def test_compare_missing_code(ctx):
    status, payload = route(ctx, "GET", "/compare", {}, None)
    assert status == 400
    assert "error" in payload


def test_analyze_ground_truth(ctx):
    bill = jsonio.read_json(SAMPLE_BILL)
    status, payload = route(ctx, "POST", "/analyze", {}, {"line_items": bill["line_items"]})
    assert status == 200
    got = {(f["line_item_id"], f["flag_type"]) for f in payload["flags"]}
    expected = {(e["line_item_id"], e["flag_type"]) for e in bill["expected_flags"]}
    assert got == expected
    # offline explain -> every flag still carries an explanation (fallback wording) or null,
    # and the analysis succeeded either way.
    assert "line_items" in payload and "price_references" in payload


def test_analyze_bad_body(ctx):
    status, payload = route(ctx, "POST", "/analyze", {}, {"line_items": {"not": "a list"}})
    assert status == 400
    assert "error" in payload


def test_analyze_non_object_body(ctx):
    status, payload = route(ctx, "POST", "/analyze", {}, None)
    assert status == 400


def test_extract_offline_returns_result(ctx):
    doc = base64.b64encode(b"fake bill bytes").decode("ascii")
    status, payload = route(ctx, "POST", "/extract", {},
                            {"content_type": "text/plain", "document_base64": doc})
    assert status == 200
    # offline fake -> extraction unavailable fallback, but a well-formed result.
    assert "line_items" in payload and "warnings" in payload


def test_extract_bad_base64(ctx):
    status, payload = route(ctx, "POST", "/extract", {},
                            {"content_type": "text/plain", "document_base64": "!!!notb64"})
    assert status == 400


def test_letter_offline(ctx):
    status, payload = route(ctx, "POST", "/letter", {}, {
        "letter_type": "itemized_bill",
        "patient": {"name": "A. Patient", "hospital": "General"},
    })
    assert status == 200
    assert "draft" in payload
    assert payload["draft"]["subject"] and payload["draft"]["body"]


def test_letter_bad_type(ctx):
    status, payload = route(ctx, "POST", "/letter", {}, {"letter_type": "nonsense"})
    assert status == 400


def test_unknown_route(ctx):
    status, payload = route(ctx, "GET", "/nope", {}, None)
    assert status == 404
    assert "routes" in payload
