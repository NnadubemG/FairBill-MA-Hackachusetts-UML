"""Tests for the failure fallback and privacy (spec task 6).

Covers E9 (model call raises), E10 (invalid or wrong-shape reply), property P3 (never
raises), and privacy PR1 (no flag text, model text or secrets in logs or output, no
files written).
"""

from __future__ import annotations

import json
import logging

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.explain.handler import WARN_MODEL_UNAVAILABLE, explain
from backend.explain.models import ExplainResult
from backend.explain.templates import fallback
from backend.extract.llm_client import FakeLLMClient, LLMError

from .factories import GOOD_TEXT, make_flag


def flags_n(n=3):
    return [make_flag(line_item_id=str(i)) for i in range(n)]


def assert_all_fallback(result: ExplainResult, flags):
    assert isinstance(result, ExplainResult)
    assert [f.explanation for f in result.flags] == [fallback(f) for f in flags]
    assert result.fallback_count == len(flags)
    assert result.warnings == [WARN_MODEL_UNAVAILABLE]


# --- E9: the model call raises --------------------------------------------

@pytest.mark.parametrize(
    "error",
    [LLMError("model API down"), RuntimeError("boom"), TimeoutError(), ValueError("x"), OSError("net")],
)
def test_e9_model_error_gives_fallback_for_every_flag(error):
    flags = flags_n(3)
    result = explain(flags, client=FakeLLMClient(raise_on_invoke=error))
    assert_all_fallback(result, flags)


def test_e9_nothing_scripted_gives_fallback():
    flags = flags_n(2)
    assert_all_fallback(explain(flags, client=FakeLLMClient()), flags)


def test_e9_failure_does_not_retry():
    client = FakeLLMClient(raise_on_invoke=RuntimeError("boom"))
    explain(flags_n(2), client=client)
    assert client.calls == 1


# --- E10: invalid JSON or wrong shape -------------------------------------

@pytest.mark.parametrize(
    "bad_reply",
    [
        "",
        "not json at all",
        "{",
        "[]",
        "null",
        "42",
        '{"explanations": "nope"}',
        '{"explanations": null}',
        '{"explanations": []}',
        '{"other": [{"key": "f0", "text": "x"}]}',
        '{"explanations": [{"key": "f0"}]}',
        '{"explanations": [{"text": "x"}]}',
        None,
    ],
)
def test_e10_unusable_reply_gives_fallback_for_every_flag(bad_reply):
    flags = flags_n(2)
    assert_all_fallback(explain(flags, client=_ReplyClient(bad_reply)), flags)


class _ReplyClient:
    """A client that returns whatever it is given (even a non-string)."""

    def __init__(self, value):
        self._value = value

    def invoke(self, *, system, content, repair_hint=None, max_tokens=None):
        return self._value


# --- P3: never raises ------------------------------------------------------

@settings(max_examples=100)
@given(st.text(max_size=30))
def test_p3_failing_client_never_raises(msg):
    flags = flags_n(2)
    result = explain(flags, client=FakeLLMClient(raise_on_invoke=RuntimeError(msg or "boom")))
    assert_all_fallback(result, flags)


@settings(max_examples=100)
@given(st.one_of(st.text(max_size=200), st.binary(max_size=40), st.none(), st.integers(), st.floats()))
def test_p3_garbage_reply_never_raises(value):
    flags = flags_n(2)
    result = explain(flags, client=_ReplyClient(value))
    assert isinstance(result, ExplainResult)
    assert len(result.flags) == 2
    assert all(isinstance(f.explanation, str) and f.explanation for f in result.flags)


# --- PR1: privacy ----------------------------------------------------------

SECRET_REASON = "Patient JANE DOE account 55512345 may be worth asking about. It is a note."
SECRET_BASIS = "Basis mentions JANE DOE 55512345 and $999.99. Source: Test, 2026."


def test_pr1_no_flag_or_model_text_in_logs_or_output(caplog, capsys):
    flag = make_flag(reason=SECRET_REASON, basis=SECRET_BASIS)
    model_text = (
        "JANE DOE may be worth asking about. It is a note for account 55512345. "
        "Can you explain it?"
    )
    reply = json.dumps({"explanations": [{"key": "f0", "text": model_text}]})
    with caplog.at_level(logging.DEBUG):
        explain([flag], client=FakeLLMClient(default=reply))
        explain([flag], client=FakeLLMClient(raise_on_invoke=RuntimeError("JANE DOE 55512345")))
    out = capsys.readouterr()
    for sink in (caplog.text, out.out, out.err):
        assert "JANE DOE" not in sink
        assert "55512345" not in sink
        assert "999.99" not in sink


def test_pr1_warning_has_no_flag_text():
    flag = make_flag(reason=SECRET_REASON, basis=SECRET_BASIS)
    result = explain([flag], client=FakeLLMClient(raise_on_invoke=RuntimeError("JANE DOE")))
    for w in result.warnings:
        assert "JANE DOE" not in w and "55512345" not in w


def test_pr1_no_files_written(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    explain(flags_n(3), client=FakeLLMClient(default=json.dumps(
        {"explanations": [{"key": "f0", "text": GOOD_TEXT}]})))
    explain(flags_n(3), client=FakeLLMClient(raise_on_invoke=RuntimeError("boom")))
    assert list(tmp_path.iterdir()) == []
