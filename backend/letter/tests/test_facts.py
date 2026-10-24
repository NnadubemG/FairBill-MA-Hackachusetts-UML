"""Tests for letter facts (spec task 3).

Covers the build part of L10 (unknown ids) and L11 (cap), and L12 (unsafe code, amount).
"""

from __future__ import annotations

import math
import re

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.explain.checks import figures, has_banned_word
from backend.letter import config
from backend.letter.facts import (
    WARN_TOO_MANY,
    WARN_UNKNOWN_LINE,
    build_items,
    facts_text,
    format_amount,
    format_date,
    safe_code,
)

from .factories import BASIS, REASON, make_flag, make_line


# --- safe_code -------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [("99213", "99213"), (" 99213 ", "99213"), ("j1234", "J1234"), ("0450", "0450"),
     ("12.5-A", "12.5-A"), ("A" * 12, "A" * 12)],
)
def test_safe_code_accepts_normal_codes(raw, expected):
    assert safe_code(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "   ", None, 99213, "has space", "A" * 13, "FRAUD", "99fraud1", "illegal1",
     "a/b", "9921;3", "<b>", "9921\n3", "코드"],
)
def test_l12_unsafe_codes_are_dropped(raw):
    assert safe_code(raw) is None


# --- format_amount ---------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [(1234.5, "$1,234.50"), (0, "$0.00"), (-0.0, "$0.00"), (5, "$5.00"), (0.005, "$0.01"),
     (2.675, "$2.68"),
     (1000000, "$1,000,000.00"), (19.999, "$20.00")],
)
def test_format_amount_ok(raw, expected):
    assert format_amount(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [float("nan"), float("inf"), float("-inf"), -1, -0.01, None, True, False, "12.50", [], 1e15],
)
def test_l12_unsafe_amounts_are_dropped(raw):
    assert format_amount(raw) is None


# --- format_date -----------------------------------------------------------

@pytest.mark.parametrize("raw", ["2026-03-04", " 2026-03-04 ", "2024-02-29"])
def test_format_date_ok(raw):
    assert format_date(raw) == raw.strip()


@pytest.mark.parametrize(
    "raw", ["2026-02-30", "2026-13-01", "03/04/2026", "20260304", "2026-3-4", "", None, 20260304, "soon"]
)
def test_format_date_bad(raw):
    assert format_date(raw) is None


# --- build_items -----------------------------------------------------------

def test_build_items_matches_flags_to_lines_in_input_order():
    lines = [make_line("a", code="99213"), make_line("b", code="85025", amount=42, date_of_service=None)]
    flags = [make_flag("b"), make_flag("a")]
    items, warnings = build_items(flags, lines)
    assert [i.line_item_id for i in items] == ["b", "a"]
    assert [i.key for i in items] == ["f0", "f1"]
    assert items[0].code == "85025" and items[0].amount == "$42.00" and items[0].date is None
    assert items[1].code == "99213" and items[1].amount == "$1,234.50" and items[1].date == "2026-03-04"
    assert items[0].data_year == 2026
    assert warnings == []


def test_l10_unknown_line_id_is_skipped_with_warning():
    items, warnings = build_items([make_flag("1"), make_flag("missing")], [make_line("1")])
    assert [i.line_item_id for i in items] == ["1"]
    assert warnings == [WARN_UNKNOWN_LINE]


def test_l10_no_usable_flag_gives_no_items():
    items, warnings = build_items([make_flag("x")], [make_line("1")])
    assert items == [] and warnings == [WARN_UNKNOWN_LINE]
    assert build_items([], [make_line("1")]) == ([], [])
    assert build_items([make_flag("1")], []) == ([], [WARN_UNKNOWN_LINE])


def test_l11_cap_keeps_first_ten_and_warns():
    lines = [make_line(str(i)) for i in range(14)]
    flags = [make_flag(str(i)) for i in range(14)]
    items, warnings = build_items(flags, lines)
    assert len(items) == config.MAX_FLAGS == 10
    assert [i.line_item_id for i in items] == [str(i) for i in range(10)]
    assert warnings == [WARN_TOO_MANY]


def test_unknown_flags_do_not_count_toward_the_cap():
    lines = [make_line(str(i)) for i in range(10)]
    flags = [make_flag("nope")] * 5 + [make_flag(str(i)) for i in range(10)]
    items, warnings = build_items(flags, lines)
    assert len(items) == 10
    assert warnings == [WARN_UNKNOWN_LINE]


def test_both_warnings_can_appear():
    lines = [make_line(str(i)) for i in range(11)]
    flags = [make_flag("nope")] + [make_flag(str(i)) for i in range(11)]
    _, warnings = build_items(flags, lines)
    assert warnings == [WARN_UNKNOWN_LINE, WARN_TOO_MANY]


def test_first_line_wins_when_ids_repeat():
    lines = [make_line("1", code="99213"), make_line("1", code="85025")]
    items, _ = build_items([make_flag("1")], lines)
    assert items[0].code == "99213"


def test_l12_unsafe_code_and_amount_still_make_an_entry():
    lines = [make_line("1", code="FRAUD", amount=float("nan"), date_of_service="garbage")]
    items, warnings = build_items([make_flag("1")], lines)
    assert len(items) == 1 and warnings == []
    assert items[0].code is None and items[0].amount is None and items[0].date is None


def test_line_description_is_never_used():
    lines = [make_line("1", description="SECRET DESCRIPTION text")]
    items, _ = build_items([make_flag("1")], lines)
    assert "SECRET" not in repr(items) and "SECRET" not in facts_text(items)


def test_flag_text_with_banned_word_is_dropped():
    flag = make_flag("1", reason="This is a fraud case.", basis="Basis is fine. Source: X, 2026.")
    items, _ = build_items([flag], [make_line("1")])
    assert items[0].reason == "" and items[0].basis == "Basis is fine. Source: X, 2026."
    flag2 = make_flag("1", basis="It looks OVERCHARGED.")
    items2, _ = build_items([flag2], [make_line("1")])
    assert items2[0].basis == ""


def test_flag_text_whitespace_is_collapsed_and_cut():
    flag = make_flag("1", reason="line one\n\nline   two", basis="x" * 2000)
    items, _ = build_items([flag], [make_line("1")])
    assert items[0].reason == "line one line two"
    assert len(items[0].basis) == 500


def test_non_int_year_is_ignored():
    flag = make_flag("1", data_year=True)  # bool is not a year
    items, _ = build_items([flag], [make_line("1")])
    assert items[0].data_year is None


# --- facts_text ------------------------------------------------------------

def test_facts_text_has_all_the_fact_fields():
    items, _ = build_items([make_flag("1")], [make_line("1")])
    text = facts_text(items)
    for part in (REASON, BASIS, "99213", "$1,234.50", "2026-03-04", "2026"):
        assert part in text
    assert {figures("$1,234.50").pop(), figures("99213").pop()} <= figures(text)


def test_facts_text_empty_for_no_items():
    assert facts_text([]) == ""


# --- Properties ------------------------------------------------------------

_code = st.one_of(st.none(), st.text(max_size=16), st.sampled_from(["99213", "FRAUD", "85025", "x y"]))
_amount = st.one_of(
    st.floats(allow_nan=True, allow_infinity=True, width=32),
    st.integers(min_value=-5, max_value=10**6),
)


@settings(max_examples=200)
@given(
    st.lists(
        st.tuples(st.text(min_size=1, max_size=3), _code, _amount, st.text(max_size=12)),
        max_size=14,
    ),
    st.lists(st.text(min_size=1, max_size=3), max_size=16),
)
def test_items_only_hold_safe_facts(line_specs, flag_ids):
    lines = [make_line(i, code=c, amount=a, date_of_service=d) for i, c, a, d in line_specs]
    flags = [make_flag(i) for i in flag_ids]
    items, _ = build_items(flags, lines)

    known = {li.id for li in lines}
    assert len(items) <= config.MAX_FLAGS
    for item in items:
        assert item.line_item_id in known
        if item.code is not None:
            assert re.fullmatch(r"[A-Za-z0-9.\-]{1,12}", item.code)
            assert not has_banned_word(item.code)
        if item.amount is not None:
            assert re.fullmatch(r"\$\d{1,3}(,\d{3})*\.\d{2}", item.amount)
        if item.date is not None:
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", item.date)
    assert math.isfinite(len(items))
