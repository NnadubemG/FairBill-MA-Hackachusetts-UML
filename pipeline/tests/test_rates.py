"""Tests for rate parsing and the skip log. Covers U8-U12 and property P2."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pipeline import skiplog
from pipeline.rates import Dollar, Missing, Skip, parse_rate


# U8 dollar formats
@pytest.mark.parametrize(
    "cell,expected",
    [
        ("$1,234.50", 1234.5),
        ("1234.5", 1234.5),
        ("$500", 500.0),
        ("0", 0.0),
        ("1,000,000", 1000000.0),
    ],
)
def test_u8_dollar_formats(cell, expected):
    result = parse_rate(cell)
    assert isinstance(result, Dollar)
    assert result.value == expected


# U9 percentage skipped
@pytest.mark.parametrize("cell", ["110% of Medicare", "95%", "50 %"])
def test_u9_percentage_skipped(cell):
    result = parse_rate(cell)
    assert isinstance(result, Skip)
    assert "percent" in result.reason.lower()


# U10 algorithm skipped
@pytest.mark.parametrize("cell", ["per diem", "case rate", "see addendum", "varies"])
def test_u10_algorithm_skipped(cell):
    result = parse_rate(cell)
    assert isinstance(result, Skip)


# U11 missing
@pytest.mark.parametrize("cell", ["", "   ", "N/A", "na", "None", "-", None])
def test_u11_missing(cell):
    assert isinstance(parse_rate(cell), Missing)


# U12 negative
@pytest.mark.parametrize("cell", ["-5", "-$5", "- 100"])
def test_u12_negative_skipped(cell):
    result = parse_rate(cell)
    assert isinstance(result, Skip)
    assert result.reason == "negative"


# P2 property: never invents a Dollar from a % input, and any Dollar is finite >= 0
@given(st.text())
def test_p2_never_invents_from_percentage(cell):
    result = parse_rate(cell)
    if "%" in cell:
        assert not isinstance(result, Dollar)
    if isinstance(result, Dollar):
        assert result.value >= 0
        assert result.value == result.value  # not NaN
        assert result.value not in (float("inf"), float("-inf"))


# P2 companion: a Dollar result, re-stringified, must contain no percent sign
@given(st.text())
def test_p2_dollar_has_no_percent_origin(cell):
    result = parse_rate(cell)
    if isinstance(result, Dollar):
        assert "%" not in cell


# skiplog: never writes a dollar figure, one line per skip
def test_skiplog_contains_no_dollar_value(tmp_path: Path):
    log = tmp_path / "skipped.log"
    skiplog.log_skip("h1", "99213", "Aetna 110% of Medicare", "percentage-based rate", log)
    skiplog.log_skip("h1", "80053", "BCBS case rate", "algorithm-based rate", log)
    content = log.read_text(encoding="utf-8")

    # two lines, each starting with SKIP
    lines = [ln for ln in content.splitlines() if ln]
    assert len(lines) == 2
    assert all(ln.startswith("SKIP\t") for ln in lines)
    # no bare dollar-amount tokens were written
    assert not re.search(r"\$\s*\d", content)


def test_skiplog_untrusted_fields_stay_one_line(tmp_path: Path):
    log = tmp_path / "skipped.log"
    # untrusted payer label with embedded newline/tab must not break line format
    skiplog.log_skip("h1", "99213", "evil\npayer\tlabel", "unrecognized", log)
    content = log.read_text(encoding="utf-8")
    lines = [ln for ln in content.splitlines() if ln]
    assert len(lines) == 1
