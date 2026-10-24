"""Tests for fenced-JSON parsing in extract (model replies wrapped in code fences)."""

from __future__ import annotations

import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.extract.handler import extract
from backend.extract.jsonutil import parse_model_json, strip_fence
from backend.extract.llm_client import FakeLLMClient
from backend.extract.validate import validate_lines

FENCE = "`" * 3
LINE = {"id": "1", "description": "Office visit", "billed_amount": 150,
        "code": "99213", "code_system": "CPT"}
ENVELOPE = {
    "line_items": [LINE],
    "metadata": {"hospital_name": "Riverside General", "statement_date": "03/04/2026",
                 "total": "$150.00"},
    "confidence_hints": {"1": "high"},
}
RAW = json.dumps(ENVELOPE)


def fenced(text: str, tag: str = "json") -> str:
    return f"{FENCE}{tag}\n{text}\n{FENCE}"


# --- parse_model_json ------------------------------------------------------

@pytest.mark.parametrize(
    "reply",
    [
        RAW,                                           # plain
        fenced(RAW),                                   # ```json
        fenced(RAW, tag=""),                           # ``` with no tag
        fenced(RAW, tag="JSON"),                       # upper-case tag
        f"{FENCE}json\r\n{RAW}\r\n{FENCE}",            # Windows line ends
        f"  \n{fenced(RAW)}\n  ",                      # spaces around
        f"Here is the JSON:\n{fenced(RAW)}",           # sentence before
        f"{fenced(RAW)}\nHope that helps.",            # sentence after
        f"{FENCE}json\n{RAW}",                         # fence never closed
    ],
)
def test_fenced_and_plain_replies_parse_the_same(reply):
    assert parse_model_json(reply) == ENVELOPE


def test_plain_json_with_backticks_inside_a_string_is_untouched():
    text = json.dumps({"line_items": [{**LINE, "description": f"note {FENCE}x{FENCE} here"}]})
    assert parse_model_json(text)["line_items"][0]["description"] == f"note {FENCE}x{FENCE} here"


def test_bad_json_still_raises_the_same_errors():
    with pytest.raises(json.JSONDecodeError):
        parse_model_json("not json")
    with pytest.raises(json.JSONDecodeError):
        parse_model_json(fenced("not json"))
    with pytest.raises(json.JSONDecodeError):
        parse_model_json("")
    with pytest.raises(TypeError):
        parse_model_json(None)


def test_strip_fence_leaves_other_values_alone():
    assert strip_fence("no fence") == "no fence"
    assert strip_fence(None) is None
    assert strip_fence(5) == 5


@settings(max_examples=100)
@given(
    st.dictionaries(
        st.one_of(st.text(max_size=5), st.just(FENCE)),
        st.one_of(st.none(), st.integers(), st.text(max_size=8), st.just(FENCE)),
        max_size=4,
    )
)
def test_property_fence_does_not_change_the_parsed_value(obj):
    text = json.dumps(obj)
    assert parse_model_json(fenced(text)) == parse_model_json(text) == obj


# --- through validate_lines and the handler --------------------------------

def test_validate_lines_accepts_a_fenced_reply():
    out = validate_lines(fenced(RAW))
    assert out.parse_error is None
    assert [li.id for li in out.line_items] == ["1"]


def test_validate_lines_still_reports_bad_json_in_a_fence():
    out = validate_lines(fenced("{not json"))
    assert out.parse_error is not None and out.line_items == []


def test_handler_uses_fenced_reply_without_a_retry(tmp_path):
    procs = tmp_path / "procedures.json"
    procs.write_text(json.dumps([{"code": "99213", "plain_label": "x"}]))
    client = FakeLLMClient(default=fenced(RAW))
    result = extract(b"\x89PNG fake", "image/png", client=client, procedures_path=procs)
    assert client.calls == 1                               # no repair retry needed
    assert len(result.line_items) == 1
    assert result.metadata.hospital_name == "Riverside General"
    assert result.metadata.statement_date == "2026-03-04"
    assert result.metadata.total == 150.0
    assert [c.confidence for c in result.line_confidence] == ["high"]
    assert result.warnings == []


# --- JSON that itself contains backticks ----------------------------------

def test_fenced_json_that_contains_three_backticks_inside_a_string():
    # Found by a Hypothesis run: the first closing fence was inside the JSON string.
    for obj in ({FENCE: None}, {"note": f"use {FENCE}code{FENCE} here"}, {"a": [FENCE, FENCE]}):
        text = json.dumps(obj)
        assert parse_model_json(fenced(text)) == obj
        assert parse_model_json(f"Here you go:\n{fenced(text)}\nDone.") == obj


def test_two_fenced_blocks_use_the_first_one_that_parses():
    first = json.dumps({"a": 1})
    second = json.dumps({"b": 2})
    reply = f"{fenced(first)}\nand also\n{fenced(second)}"
    assert parse_model_json(reply) == {"a": 1}


def test_unparseable_fenced_reply_still_raises_json_error():
    with pytest.raises(json.JSONDecodeError):
        parse_model_json(f"{FENCE}json\n{{not json}}\n{FENCE}\n{FENCE}json\nalso not\n{FENCE}")
