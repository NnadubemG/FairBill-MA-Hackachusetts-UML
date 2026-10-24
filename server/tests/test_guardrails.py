"""TC-7: Banned-words enforcement.

Unit-level: scrub() removes banned terms and reports the violation.
Endpoint-level: when the (mocked) model returns banned text, the returned
letter/labels contain no banned term.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import guardrails


@pytest.mark.parametrize(
    "banned",
    [
        "We guarantee you will win this lawsuit.",
        "This is fraud and you should sue.",
        "You are entitled to a refund; this is illegal.",
        "Our attorney gives legal advice.",
    ],
)
def test_scrub_removes_banned_terms(banned):
    cleaned, had = guardrails.scrub(banned)
    assert had is True
    assert not guardrails.contains_banned(cleaned), cleaned


def test_scrub_leaves_clean_text_untouched():
    text = "This charge may be worth asking the billing office about."
    cleaned, had = guardrails.scrub(text)
    assert had is False
    assert cleaned == text


def test_letter_endpoint_scrubs_model_output(monkeypatch):
    # Configure a model id and mock the Anthropic call to return banned text.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("LETTER_MODEL_ID", "claude-test")

    import app.config as config

    config._settings = None  # type: ignore[attr-defined]

    from app import anthropic_client

    def fake_complete(**kwargs):
        return (
            '{"subject": "We guarantee we will win your lawsuit",'
            ' "body": "This is fraud. You are entitled to sue your provider."}'
        )

    monkeypatch.setattr(anthropic_client, "complete", fake_complete)

    from app.main import app

    client = TestClient(app)
    r = client.post(
        "/api/letter",
        json={"type": "billing_question", "recipient": "provider"},
    )
    assert r.status_code == 200
    letter = r.json()["letter"]
    assert not guardrails.contains_banned(letter["subject"]), letter["subject"]
    assert not guardrails.contains_banned(letter["body"]), letter["body"]
