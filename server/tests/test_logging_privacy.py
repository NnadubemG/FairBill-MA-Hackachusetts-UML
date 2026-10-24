"""TC-6: No-body logging.

A unique marker sent in a request body must not appear in logs, and the key must
never appear. Also asserts the log_error helper only emits metadata.
"""

from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from app.logging_setup import log_error
from app.main import app

client = TestClient(app)


def test_request_body_marker_not_logged(caplog):
    marker = "UNIQUE-MARKER-9f3c2a-bill-content"
    with caplog.at_level(logging.ERROR):
        # analyze will reject this (bad shape) -> 422, but the body text must
        # never be written to logs.
        client.post("/api/analyze", json={"line_items": marker})
    assert marker not in caplog.text


def test_log_error_emits_only_metadata(caplog):
    with caplog.at_level(logging.ERROR, logger="medbill"):
        log_error("/api/extract", 500, request_id="abc123", message="SomeError")
    text = caplog.text
    assert "route=/api/extract" in text
    assert "status=500" in text
    assert "request_id=abc123" in text
    # A sensitive marker that was never passed in must not appear.
    assert "UNIQUE-MARKER" not in text
