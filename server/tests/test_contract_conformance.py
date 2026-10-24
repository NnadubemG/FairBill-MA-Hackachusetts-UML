"""TC-2: Contract conformance.

Each endpoint's response validates against its `/contracts` response type, and a
payload that violates the contract is rejected with a 422 ApiError.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from contracts import (
    AnalyzeResponse,
    CompareResponse,
    ProceduresResponse,
)

client = TestClient(app)


def test_analyze_response_matches_contract():
    payload = {
        "line_items": [
            {
                "code": "99213",
                "description": "Office visit",
                "units": 1,
                "charge": 30000,
                "confidence": 0.9,
                "needs_confirmation": False,
            }
        ]
    }
    r = client.post("/api/analyze", json=payload)
    assert r.status_code == 200
    # Validates (raises if the shape is wrong).
    model = AnalyzeResponse.model_validate(r.json())
    assert model.results[0].line_index == 0


def test_procedures_response_matches_contract():
    r = client.get("/api/procedures")
    assert r.status_code == 200
    ProceduresResponse.model_validate(r.json())


def test_compare_response_matches_contract():
    r = client.get("/api/compare", params={"code": "99213", "charged": 30000})
    assert r.status_code == 200
    model = CompareResponse.model_validate(r.json())
    assert model.code == "99213"
    # 30000 charged vs 9200 medicare reference -> ratio computed.
    assert model.ratio_to_medicare is not None


def test_invalid_payload_is_422_api_error():
    # confidence out of [0,1] violates the contract constraint.
    bad = {
        "line_items": [
            {
                "description": "x",
                "confidence": 5.0,
                "needs_confirmation": False,
            }
        ]
    }
    r = client.post("/api/analyze", json=bad)
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "validation_error"


def test_unknown_field_rejected_extra_forbid():
    # extra="forbid" on the contract base model should reject unknown fields.
    bad = {
        "line_items": [
            {
                "description": "x",
                "confidence": 0.5,
                "needs_confirmation": False,
                "surprise": 1,
            }
        ]
    }
    r = client.post("/api/analyze", json=bad)
    assert r.status_code == 422
