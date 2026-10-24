"""Tests for the generic CSV parser + registry. Covers U17, U19, U20, P5."""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pipeline.parsers.base import Parser, RawPriceRow
from pipeline.parsers.hospital_generic_csv import GenericCsvParser
from pipeline.registry import REGISTRY, UnknownFormatError, get_parser

FIXTURES = Path(__file__).parent / "fixtures"
CSV = FIXTURES / "hospital_generic.csv"

CURATED = {"99213", "80053"}  # note: 11111 is deliberately NOT curated


def _rows(curated=CURATED):
    return list(GenericCsvParser().rows(str(CSV), curated))


# U17 happy path: curated rows mapped correctly, bad rate_kind dropped
def test_u17_happy_path_fields_mapped():
    rows = _rows()
    # 99213: negotiated(BCBS), negotiated(Aetna %), cash, gross  = 4
    # 80053: negotiated(blank rate)                              = 1
    # 11111 not curated -> 0 ; bogus rate_kind -> 0
    assert len(rows) == 5
    assert all(isinstance(r, RawPriceRow) for r in rows)

    bcbs = next(r for r in rows if r.code == "99213" and r.raw_payer == "BCBS PPO")
    assert bcbs.rate_kind == "negotiated"
    assert bcbs.raw_rate == "145.00"
    assert bcbs.code_system == "CPT"

    cash = next(r for r in rows if r.rate_kind == "cash")
    assert cash.raw_payer == ""
    assert cash.raw_rate == "95.00"


# U19 code filtering: a non-curated code never appears
def test_u19_non_curated_code_excluded():
    rows = _rows()
    assert all(r.code in CURATED for r in rows)
    assert not any(r.code == "11111" for r in rows)


# U20 mixed units / empty cells: blank rate still yielded (raw_rate empty)
def test_u20_blank_rate_cell_yielded():
    rows = _rows()
    blank = [r for r in rows if r.code == "80053"]
    assert len(blank) == 1
    assert blank[0].raw_rate == ""  # downstream treats as missing


# P5 property: every yielded row's code is in the curated set, for any curated subset
@given(st.sets(st.sampled_from(["99213", "80053", "11111", "00000"])))
def test_p5_only_curated_codes_yielded(curated):
    for r in GenericCsvParser().rows(str(CSV), curated):
        assert r.code in curated


# Registry: CSV parser is registered and satisfies the Parser protocol
def test_registry_has_csv_parser():
    parser = get_parser("generic_csv")
    assert isinstance(parser, Parser)
    assert parser.format_id == "generic_csv"
    assert "generic_csv" in REGISTRY


def test_registry_unknown_format_raises():
    with pytest.raises(UnknownFormatError):
        get_parser("does_not_exist")
