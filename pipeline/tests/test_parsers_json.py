"""Tests for the generic JSON parser. Covers U18 (+ code filtering, registry)."""

from __future__ import annotations

from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from pipeline.parsers.base import Parser, RawPriceRow
from pipeline.parsers.hospital_generic_json import GenericJsonParser
from pipeline.registry import get_parser

FIXTURES = Path(__file__).parent / "fixtures"
JSON = FIXTURES / "hospital_generic.json"

CURATED = {"99213", "80053"}  # 11111 deliberately not curated


def _rows(curated=CURATED):
    return list(GenericJsonParser().rows(str(JSON), curated))


# U18 happy path: same semantics as the CSV parser, JSON array form
def test_u18_happy_path_fields_mapped():
    rows = _rows()
    # 99213: negotiated, negotiated(%), cash, gross = 4 ; 80053: 1 ; others dropped
    assert len(rows) == 5
    assert all(isinstance(r, RawPriceRow) for r in rows)

    bcbs = next(r for r in rows if r.code == "99213" and r.raw_payer == "BCBS PPO")
    assert bcbs.rate_kind == "negotiated"
    assert bcbs.raw_rate == "145.00"
    assert bcbs.code_system == "CPT"

    # null rate -> empty string (downstream treats as missing)
    blank = next(r for r in rows if r.code == "80053")
    assert blank.raw_rate == ""


def test_u18_non_curated_excluded():
    assert all(r.code in CURATED for r in _rows())
    assert not any(r.code == "11111" for r in _rows())


@given(st.sets(st.sampled_from(["99213", "80053", "11111", "00000"])))
def test_json_only_curated_codes_yielded(curated):
    for r in GenericJsonParser().rows(str(JSON), curated):
        assert r.code in curated


def test_registry_has_json_parser():
    parser = get_parser("generic_json")
    assert isinstance(parser, Parser)
    assert parser.format_id == "generic_json"


def test_u18_streams_across_chunk_boundaries(monkeypatch):
    """Force tiny reads so records straddle chunk boundaries -> exercises refill."""
    import pipeline.parsers.hospital_generic_json as mod

    monkeypatch.setattr(mod, "_READ_CHUNK", 7)  # smaller than any single record
    rows = list(mod.GenericJsonParser().rows(str(JSON), CURATED))
    # Same result as a normal read: 5 curated rows with valid rate_kind.
    assert len(rows) == 5
    assert {r.code for r in rows} == CURATED
