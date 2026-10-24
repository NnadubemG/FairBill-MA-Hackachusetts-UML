"""Tests for post-processing normalization + merge (spec task 5).

Covers T10 (money/date normalization, including date_of_service) and T11
(continuation-row merge). Pure functions, offline.
"""

from __future__ import annotations

import pytest

from backend.extract._contracts import LineItem
from backend.extract.postprocess import (
    merge_continuations,
    normalize_and_merge,
    normalize_date,
    normalize_line,
    normalize_money,
)


# --- T10a: money -----------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("$1,234.50", 1234.5),
        ("1234.50", 1234.5),
        ("$0.00", 0.0),
        ("  $ 42 ", 42.0),
        (1234.5, 1234.5),
        (42, 42.0),
        ("(123.45)", -123.45),   # parenthesised negative
        ("123.45-", -123.45),    # trailing-minus accounting style
        ("-50", -50.0),
        ("$1,000,000", 1_000_000.0),
    ],
)
def test_normalize_money_valid(raw, expected):
    assert normalize_money(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "N/A", "n/a", "abc", "$", "-", None, True, False])
def test_normalize_money_unparseable_returns_none(raw):
    assert normalize_money(raw) is None


# --- T10b: dates (incl. date_of_service) -----------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026-03-04", "2026-03-04"),
        ("2026-3-4", "2026-03-04"),
        ("03/04/2026", "2026-03-04"),   # US month-first
        ("3/4/2026", "2026-03-04"),
        ("2026/03/04", "2026-03-04"),   # year-first
        ("03-04-2026", "2026-03-04"),
        ("Mar 4, 2026", "2026-03-04"),
        ("March 4, 2026", "2026-03-04"),
        ("4 Mar 2026", "2026-03-04"),
    ],
)
def test_normalize_date_valid(raw, expected):
    assert normalize_date(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "  ", "not a date", "03/04/26", "13/40/2026", "2026-13-01", None, 20260304],
)
def test_normalize_date_unparseable_returns_none(raw):
    assert normalize_date(raw) is None


def test_normalize_line_sets_iso_date_and_float_amount():
    line = LineItem(
        id="1",
        description="X-ray",
        billed_amount="$1,200.00",  # type: ignore[arg-type]  (model may emit string)
        date_of_service="03/04/2026",
    )
    out = normalize_line(line)
    assert out.billed_amount == 1200.0
    assert out.date_of_service == "2026-03-04"


def test_normalize_line_unparseable_date_becomes_none():
    line = LineItem(id="1", description="X-ray", billed_amount=10.0, date_of_service="garbage")
    out = normalize_line(line)
    assert out.date_of_service is None


# --- T11: continuation-row merge -------------------------------------------

def test_merge_continuation_into_previous():
    lines = [
        LineItem(id="1", description="MRI brain without", billed_amount=2500.0, code="70551"),
        LineItem(id="2", description="contrast material", billed_amount=0.0),
        LineItem(id="3", description="Lab panel", billed_amount=80.0, code="80053"),
    ]
    merged = merge_continuations(lines)
    assert len(merged) == 2
    assert merged[0].description == "MRI brain without contrast material"
    assert merged[0].code == "70551"          # real line's fields preserved
    assert merged[0].billed_amount == 2500.0
    assert merged[1].description == "Lab panel"


def test_leading_continuation_is_kept_not_dropped():
    lines = [
        LineItem(id="1", description="orphan fragment", billed_amount=0.0),
        LineItem(id="2", description="Real line", billed_amount=100.0, code="99213"),
    ]
    merged = merge_continuations(lines)
    assert len(merged) == 2  # nothing dropped
    assert merged[0].description == "orphan fragment"


def test_line_with_code_is_not_a_continuation():
    lines = [
        LineItem(id="1", description="Visit", billed_amount=100.0, code="99213"),
        LineItem(id="2", description="Addon", billed_amount=0.0, code="99354"),  # has code
    ]
    merged = merge_continuations(lines)
    assert len(merged) == 2  # the coded zero-charge line stays separate


def test_normalize_and_merge_runs_normalization_first():
    lines = [
        LineItem(id="1", description="CT abdomen", billed_amount="$1,000.00",  # type: ignore[arg-type]
                 code="74177", date_of_service="03/04/2026"),
        LineItem(id="2", description="with contrast", billed_amount="$0.00"),  # type: ignore[arg-type]
    ]
    out = normalize_and_merge(lines)
    assert len(out) == 1
    assert out[0].description == "CT abdomen with contrast"
    assert out[0].billed_amount == 1000.0
    assert out[0].date_of_service == "2026-03-04"


def test_empty_input():
    assert merge_continuations([]) == []
    assert normalize_and_merge([]) == []
