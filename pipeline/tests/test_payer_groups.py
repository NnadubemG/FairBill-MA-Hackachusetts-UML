"""Tests for payer grouping. Covers U6, U7, and property test P1."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from contracts.types import PayerGroup
from pipeline.payer_groups import classify

VALID_GROUPS = {
    "commercial",
    "medicare_advantage",
    "medicaid_managed",
    "cash",
    "gross",
}


# U6 table test
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("BCBS PPO", "commercial"),
        ("Aetna Medicare Advantage", "medicare_advantage"),
        ("MassHealth Medicaid MCO", "medicaid_managed"),
        ("Discounted Cash Price", "cash"),
        ("Gross Charge", "gross"),
        ("Self-Pay", "cash"),
        ("Chargemaster", "gross"),
    ],
)
def test_u6_known_labels(raw, expected):
    assert classify(raw) == expected


# U7 case-insensitive
@pytest.mark.parametrize("raw", ["gross charge", "GROSS CHARGE", "Gross Charge"])
def test_u7_case_insensitive(raw):
    assert classify(raw) == "gross"


# P1 property: total function, always returns one of the five, never raises
@given(st.text())
def test_p1_classify_is_total(raw):
    result = classify(raw)
    assert result in VALID_GROUPS


# P1 companion: empty / whitespace -> default commercial, still valid
@pytest.mark.parametrize("raw", ["", "   ", "\t\n"])
def test_p1_empty_defaults_commercial(raw):
    assert classify(raw) == "commercial"
