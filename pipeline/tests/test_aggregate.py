"""Tests for aggregation. Covers U13-U16 and properties P3, P4."""

from __future__ import annotations

import random

from hypothesis import given
from hypothesis import strategies as st

from pipeline.aggregate import summarize


# U13 single value
def test_u13_single_value():
    assert summarize([10.0]) == (10.0, 10.0, 10.0)


# U14 three values
def test_u14_three_values():
    assert summarize([10.0, 30.0, 20.0]) == (10.0, 20.0, 30.0)


# U15 even count median
def test_u15_even_count_median():
    assert summarize([10.0, 20.0, 30.0, 40.0]) == (10.0, 25.0, 40.0)


# U16 empty
def test_u16_empty():
    assert summarize([]) == (None, None, None)


# strategy: non-empty lists of finite, non-negative floats (real dollar values)
_values = st.lists(
    st.floats(min_value=0, max_value=1e9, allow_nan=False, allow_infinity=False),
    min_size=1,
    max_size=50,
)


# P3 property: min <= median <= max always holds
@given(_values)
def test_p3_ordering(values):
    lo, med, hi = summarize(values)
    assert lo is not None and med is not None and hi is not None
    assert lo <= med <= hi


# P4 property: result is independent of input order
@given(_values)
def test_p4_order_independence(values):
    original = summarize(values)
    shuffled = list(values)
    random.Random(0).shuffle(shuffled)
    assert summarize(shuffled) == original
