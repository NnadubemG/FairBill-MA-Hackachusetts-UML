"""Tests for the deterministic fallback and privacy (spec task 8).

Covers T9 (model raises -> empty + warning, no raise), property P3 (any failing
client -> ExtractionResult, never raises), and privacy PR1 (no bill bytes, request
body, or line content is logged).
"""

from __future__ import annotations

import json
import logging

from hypothesis import given, settings
from hypothesis import strategies as st

from backend.extract.llm_client import LLMError, FakeLLMClient
from backend.extract.handler import WARN_EXTRACTION_UNAVAILABLE, extract
from backend.extract.models import ExtractionResult

PNG_BYTES = b"\x89PNG secret bill bytes"
CT = "image/png"


# --- T9: model call raises -> fallback -------------------------------------

def test_t9_model_raises_returns_empty_with_warning():
    client = FakeLLMClient(raise_on_invoke=LLMError("model API down"))
    result = extract(PNG_BYTES, CT, client=client)
    assert isinstance(result, ExtractionResult)
    assert result.line_items == []
    assert result.line_confidence == []
    assert result.warnings == [WARN_EXTRACTION_UNAVAILABLE]


def test_fallback_on_unsupported_media_type():
    # Bad content type raises inside prompt building -> same safe fallback.
    client = FakeLLMClient(default="{}")
    result = extract(b"data", "text/plain", client=client)
    assert result.line_items == []
    assert result.warnings == [WARN_EXTRACTION_UNAVAILABLE]


def test_fallback_on_no_scripted_response():
    # FakeLLMClient with nothing scripted raises LLMError -> fallback.
    client = FakeLLMClient()
    result = extract(PNG_BYTES, CT, client=client)
    assert result.line_items == []
    assert result.warnings == [WARN_EXTRACTION_UNAVAILABLE]


# --- Property P3: never raises on model failure ----------------------------

@settings(max_examples=50)
@given(st.text(max_size=20))
def test_p3_failing_client_never_raises(msg):
    client = FakeLLMClient(raise_on_invoke=RuntimeError(msg or "boom"))
    result = extract(PNG_BYTES, CT, client=client)  # must not raise
    assert isinstance(result, ExtractionResult)
    assert result.line_items == []


@settings(max_examples=50)
@given(st.binary(max_size=40), st.sampled_from(["image/png", "image/jpeg", "application/pdf"]))
def test_p3_arbitrary_bytes_with_failing_client(data, ct):
    client = FakeLLMClient(raise_on_invoke=ValueError("nope"))
    result = extract(data, ct, client=client)
    assert isinstance(result, ExtractionResult)
    assert result.warnings == [WARN_EXTRACTION_UNAVAILABLE]


# --- Privacy PR1: no bill content logged -----------------------------------

def test_pr1_no_bill_content_logged(caplog):
    secret_desc = "PATIENT JANE DOE ACCT 55512345 X-ray"
    raw = json.dumps({
        "line_items": [
            {"id": "1", "description": secret_desc, "billed_amount": 100,
             "code": "99213", "code_system": "CPT"}
        ],
        "confidence_hints": {"1": "high"},
    })
    client = FakeLLMClient(default=raw)

    with caplog.at_level(logging.DEBUG):
        result = extract(b"\x89PNG raw bill bytes with JANE DOE", CT, client=client)

    # The line was extracted...
    assert len(result.line_items) == 1
    # ...but nothing sensitive reached the logs.
    log_text = caplog.text
    assert "JANE DOE" not in log_text
    assert "55512345" not in log_text
    assert secret_desc not in log_text


def test_pr1_no_content_logged_on_failure(caplog):
    client = FakeLLMClient(raise_on_invoke=LLMError("boom JANE DOE"))
    with caplog.at_level(logging.DEBUG):
        extract(b"raw bytes JANE DOE 55512345", CT, client=client)
    # Even the exception message (which here contains a name) is not logged.
    assert "JANE DOE" not in caplog.text
    assert "55512345" not in caplog.text
