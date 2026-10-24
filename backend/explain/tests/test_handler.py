"""Tests for the explain handler (spec task 5).

Covers E1, E2 (in a batch), E11, E13, E14, E15, E16, and properties P2 and P5.
Everything runs offline with FakeLLMClient.
"""

from __future__ import annotations

import json
from dataclasses import fields

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.explain import checks, config, prompts
from backend.explain.handler import WARN_MODEL_UNAVAILABLE, explain
from backend.explain.templates import fallback
from backend.extract.llm_client import FakeLLMClient

from .factories import GOOD_TEXT, make_flag

ALL_TYPES = [
    "price_above_reference",
    "price_outside_ma_range",
    "duplicate_line_item",
    "quantity_implausible",
    "possible_unbundling",
    "no_reference_found",
]


def reply(texts: dict[int, str]) -> str:
    """A model reply with ``{"f<i>": text}`` entries."""
    return json.dumps(
        {"explanations": [{"key": f"f{i}", "text": t} for i, t in texts.items()]}
    )


def same_except_explanation(a, b) -> bool:
    return all(
        getattr(a, f.name) == getattr(b, f.name) for f in fields(a) if f.name != "explanation"
    )


# --- E1: each flag type ---------------------------------------------------

@pytest.mark.parametrize("flag_type", ALL_TYPES)
def test_e1_good_model_text_is_used_for_each_type(flag_type):
    flag = make_flag(flag_type=flag_type)
    client = FakeLLMClient(default=reply({0: GOOD_TEXT}))
    result = explain([flag], client=client)
    assert result.flags[0].explanation == GOOD_TEXT
    assert result.fallback_count == 0
    assert result.warnings == []


def test_whitespace_around_model_text_is_trimmed():
    client = FakeLLMClient(default=reply({0: "  \n" + GOOD_TEXT + "  "}))
    assert explain([make_flag()], client=client).flags[0].explanation == GOOD_TEXT


# --- E2 in a batch: only the bad flag falls back ---------------------------

def test_e2_bad_text_falls_back_but_neighbours_keep_model_text():
    flags = [make_flag(line_item_id=str(i)) for i in range(3)]
    bad = "This looks like fraud to me. It is a lot. Can you explain it?"
    client = FakeLLMClient(default=reply({0: GOOD_TEXT, 1: bad, 2: GOOD_TEXT}))
    result = explain(flags, client=client)
    assert result.flags[0].explanation == GOOD_TEXT
    assert result.flags[1].explanation == fallback(flags[1])
    assert result.flags[2].explanation == GOOD_TEXT
    assert result.fallback_count == 1
    assert result.warnings == []          # the call itself worked


def test_new_figure_falls_back():
    flag = make_flag()
    client = FakeLLMClient(default=reply({0: GOOD_TEXT.replace("$823.00", "$900.00")}))
    result = explain([flag], client=client)
    assert result.flags[0].explanation == fallback(flag)
    assert result.fallback_count == 1


# --- E11: missing key ------------------------------------------------------

def test_e11_missing_key_only_that_flag_falls_back():
    flags = [make_flag(line_item_id=str(i)) for i in range(3)]
    client = FakeLLMClient(default=reply({0: GOOD_TEXT, 2: GOOD_TEXT}))
    result = explain(flags, client=client)
    assert [f.explanation == GOOD_TEXT for f in result.flags] == [True, False, True]
    assert result.flags[1].explanation == fallback(flags[1])
    assert result.fallback_count == 1


# --- E13 / E14 / E15: how many calls --------------------------------------

def test_e13_empty_list_makes_no_call():
    client = FakeLLMClient(default="{}")
    result = explain([], client=client)
    assert result.flags == [] and result.fallback_count == 0 and result.warnings == []
    assert client.calls == 0


def test_e14_five_flags_one_call():
    flags = [make_flag(line_item_id=str(i)) for i in range(5)]
    client = FakeLLMClient(default=reply({i: GOOD_TEXT for i in range(5)}))
    result = explain(flags, client=client)
    assert client.calls == 1
    assert client.requests[0]["max_tokens"] == prompts.compute_max_tokens(5)
    payload = json.loads(client.requests[0]["content"][0]["text"])
    assert len(payload["flags"]) == 5
    assert result.fallback_count == 0


def test_e15_over_the_cap_still_one_call_and_extra_flags_fall_back():
    cap = config.MAX_FLAGS_PER_CALL
    flags = [make_flag(line_item_id=str(i)) for i in range(cap + 3)]
    client = FakeLLMClient(default=reply({i: GOOD_TEXT for i in range(cap + 3)}))
    result = explain(flags, client=client)
    assert client.calls == 1
    assert len(json.loads(client.requests[0]["content"][0]["text"])["flags"]) == cap
    assert len(result.flags) == cap + 3
    assert result.fallback_count == 3
    for i in range(cap, cap + 3):
        assert result.flags[i].explanation == fallback(flags[i])
    # The model replied for keys beyond the cap; they are ignored.
    assert all(f.explanation == GOOD_TEXT for f in result.flags[:cap])


def test_no_retry_on_bad_reply():
    client = FakeLLMClient(default="not json")
    explain([make_flag()], client=client)
    assert client.calls == 1


# --- E16: other fields unchanged ------------------------------------------

def test_e16_only_explanation_changes_and_order_is_kept():
    flags = [
        make_flag(line_item_id="b", flag_type="duplicate_line_item", severity="low"),
        make_flag(line_item_id="a", flag_type="no_reference_found", severity="info",
                  data_source=None, data_year=None),
        make_flag(line_item_id="c"),
    ]
    client = FakeLLMClient(default=reply({0: GOOD_TEXT}))
    result = explain(flags, client=client)
    assert len(result.flags) == 3
    for before, after in zip(flags, result.flags):
        assert same_except_explanation(before, after)
        assert isinstance(after.explanation, str) and after.explanation.strip()


def test_existing_explanation_is_replaced():
    flag = make_flag(explanation="old text")
    client = FakeLLMClient(default=reply({0: GOOD_TEXT}))
    assert explain([flag], client=client).flags[0].explanation == GOOD_TEXT


def test_input_flags_are_not_modified():
    flag = make_flag()
    explain([flag], client=FakeLLMClient(default=reply({0: GOOD_TEXT})))
    assert flag.explanation is None


def test_unusable_reply_sets_warning_and_all_fallback():
    flags = [make_flag(line_item_id=str(i)) for i in range(2)]
    result = explain(flags, client=FakeLLMClient(default="garbage"))
    assert result.warnings == [WARN_MODEL_UNAVAILABLE]
    assert result.fallback_count == 2
    assert [f.explanation for f in result.flags] == [fallback(f) for f in flags]


# --- Properties ------------------------------------------------------------

_reason = st.one_of(
    st.text(max_size=120),
    st.sampled_from([
        "This may be worth asking about. It is about 1.5 times the reference.",
        "This is fraud. It is OVERCHARGED.",
        "",
    ]),
)
_flags = st.lists(
    st.builds(
        make_flag,
        line_item_id=st.text(min_size=1, max_size=4),
        flag_type=st.one_of(st.sampled_from(ALL_TYPES), st.text(max_size=8)),
        reason=_reason,
        basis=st.text(max_size=80),
        data_year=st.one_of(st.none(), st.integers(min_value=1990, max_value=2100)),
    ),
    max_size=8,
)
_model_text = st.one_of(
    st.text(max_size=150),
    st.just(GOOD_TEXT),
    st.just("This is fraud, plain and simple. Can you explain it?"),
)
_reply = st.one_of(
    st.text(max_size=200),
    st.dictionaries(st.integers(min_value=0, max_value=10), _model_text, max_size=10).map(reply),
)


@settings(max_examples=200)
@given(_flags, _reply)
def test_p2_p5_result_shape_and_safety(flags, raw_reply):
    client = FakeLLMClient(default=raw_reply)
    result = explain(flags, client=client)

    assert len(result.flags) == len(flags)
    assert client.calls == (1 if flags else 0)
    assert 0 <= result.fallback_count <= len(flags)
    for before, after in zip(flags, result.flags):
        assert same_except_explanation(before, after)
        assert isinstance(after.explanation, str) and after.explanation.strip()
        assert not checks.has_banned_word(after.explanation)
