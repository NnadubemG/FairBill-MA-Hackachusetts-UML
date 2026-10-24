"""Tests for fallback templates (spec task 3).

Covers E17 (fallback per type), E18 (banned word in reason), E22 (real core templates),
and properties P4 (pure) and P6 (adds no figure).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from core import language as core_language

from backend.explain import checks, config, templates

from .factories import make_flag

ALL_TYPES = [
    "price_above_reference",
    "price_outside_ma_range",
    "duplicate_line_item",
    "quantity_implausible",
    "possible_unbundling",
    "no_reference_found",
]


# --- E17: one question per type -------------------------------------------

@pytest.mark.parametrize("flag_type", ALL_TYPES)
def test_e17_each_type_gets_its_fixed_question(flag_type):
    flag = make_flag(flag_type=flag_type)
    text = templates.fallback(flag)
    assert text.endswith(templates.QUESTIONS[flag_type])
    assert text.startswith(flag.reason)
    assert not checks.has_banned_word(text)


def test_e17_all_six_types_have_a_question():
    assert set(templates.QUESTIONS) == set(ALL_TYPES)


def test_e17_unknown_type_gets_generic_question():
    flag = make_flag(flag_type="something_new")
    assert templates.fallback(flag).endswith(templates.GENERIC_QUESTION)


def test_questions_have_no_digits():
    # So a question can never add a figure.
    for q in [*templates.QUESTIONS.values(), templates.GENERIC_QUESTION]:
        assert not any(ch.isdigit() for ch in q)
        assert q.endswith("?") and q.count("?") == 1


# --- E18: banned word in reason --------------------------------------------

@pytest.mark.parametrize("bad", ["This is FRAUD.", "It looks overcharged.", "You   Are   Owed money."])
def test_e18_banned_reason_is_not_copied(bad):
    flag = make_flag(reason=bad)
    text = templates.fallback(flag)
    assert not checks.has_banned_word(text)
    assert text.startswith(templates.GENERIC_LEAD)


def test_empty_reason_uses_generic_lead():
    text = templates.fallback(make_flag(reason="   "))
    assert text.startswith(templates.GENERIC_LEAD)


def test_reason_without_final_period_gets_one():
    text = templates.fallback(make_flag(reason="This may be worth asking about"))
    assert text.startswith("This may be worth asking about. ")


def test_reason_whitespace_is_collapsed():
    text = templates.fallback(make_flag(reason="Line one.\n  Line   two."))
    assert "\n" not in text and "  " not in text


# --- E22: the real core templates -----------------------------------------

def _core_cases():
    d = Decimal
    above = core_language.above_reference_text("99213", d("1234.50"), d("823.00"), "CMS PFS", 2026)
    outside = core_language.outside_ma_range_text("99213", d("1234.50"), d("100.00"), d("900.00"), "MA hospital files", 2026)
    dup_dated = core_language.duplicate_text(2, True)
    dup_undated = core_language.duplicate_text(3, False)
    none_ref = core_language.no_reference_text("99213")
    return [
        ("price_above_reference", *above, "CMS PFS", 2026),
        ("price_outside_ma_range", *outside, "MA hospital files", 2026),
        ("duplicate_line_item", *dup_dated, None, None),
        ("duplicate_line_item", *dup_undated, None, None),
        ("no_reference_found", *none_ref, None, None),
    ]


@pytest.mark.parametrize("flag_type,reason,basis,src,year", _core_cases())
def test_e22_core_templates_make_good_fallbacks(flag_type, reason, basis, src, year):
    flag = make_flag(flag_type=flag_type, reason=reason, basis=basis, data_source=src, data_year=year)
    text = templates.fallback(flag)
    assert checks.sentence_shape_ok(text), text
    assert not checks.has_banned_word(text)
    allowed = checks.figures(reason + " " + basis)
    assert checks.figures(text) <= allowed
    # A fallback built from a real core reason is itself acceptable.
    assert checks.accept(text, flag)


# --- Properties ------------------------------------------------------------

_flag_strategy = st.builds(
    make_flag,
    flag_type=st.one_of(st.sampled_from(ALL_TYPES), st.text(max_size=12)),
    reason=st.text(max_size=150),
    basis=st.text(max_size=100),
    data_year=st.one_of(st.none(), st.integers(min_value=1990, max_value=2100)),
)


@settings(max_examples=300)
@given(_flag_strategy)
def test_p4_fallback_is_pure(flag):
    assert templates.fallback(flag) == templates.fallback(flag)


@settings(max_examples=300)
@given(_flag_strategy)
def test_p6_fallback_adds_no_figure_and_no_banned_word(flag):
    text = templates.fallback(flag)
    assert not checks.has_banned_word(text)
    allowed = checks.figures(f"{flag.reason} {flag.basis}")
    # The fallback only copies the reason (or uses a figure-free sentence).
    assert checks.figures(text) <= checks.figures(flag.reason or "") | allowed
    assert checks.figures(text) <= allowed


def test_p4_position_does_not_matter():
    flags = [make_flag(line_item_id=str(i), flag_type=t) for i, t in enumerate(ALL_TYPES)]
    forward = [templates.fallback(f) for f in flags]
    backward = [templates.fallback(f) for f in reversed(flags)][::-1]
    assert forward == backward


def test_config_banned_words_used():
    assert config.BANNED_WORDS  # sanity: the guard has a list to check against
