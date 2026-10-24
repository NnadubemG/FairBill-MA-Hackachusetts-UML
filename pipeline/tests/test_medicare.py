"""Tests for the medicare stage. Covers U25, U26."""

from __future__ import annotations

from pathlib import Path

from pipeline import jsonio
from pipeline.stages.medicare import build_medicare

FIXTURES = Path(__file__).parent / "fixtures"
PFS = FIXTURES / "pfs_sample.csv"
CURATED = {"99213", "80053", "70553"}  # 11111 not curated; 70553 only in non-MA locality
SOURCE = "CMS Physician Fee Schedule (test)"
YEAR = 2025
MA = "10112"


# U25: filtered to MA locality + curated codes; PriceReference with provenance
def test_u25_ma_locality_curated_codes(tmp_path):
    out = tmp_path / "medicare.json"
    count = build_medicare(PFS, CURATED, SOURCE, YEAR, locality=MA, out_path=out)
    assert count == 2  # 99213 (MA) + 80053 (MA); 11111 not curated; 70553 not in MA

    data = jsonio.read_json(out)
    by = {r["code"]: r for r in data}

    assert by["99213"]["medicare_price"] == 92.47  # the MA row, not the 99999 row
    assert by["99213"]["code_system"] == "HCPCS"
    assert by["99213"]["data_source"] == SOURCE
    assert by["99213"]["data_year"] == YEAR

    assert by["80053"]["medicare_price"] == 14.33
    # non-curated code never appears
    assert "11111" not in by


# U26: a curated code with no MA-locality row -> no record (no guess)
def test_u26_missing_ma_locality_no_record(tmp_path):
    out = tmp_path / "medicare.json"
    build_medicare(PFS, CURATED, SOURCE, YEAR, locality=MA, out_path=out)
    data = jsonio.read_json(out)
    codes = {r["code"] for r in data}
    # 70553 exists only for locality 99999 -> must NOT be emitted
    assert "70553" not in codes


def test_output_sorted_and_deterministic(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    build_medicare(PFS, CURATED, SOURCE, YEAR, locality=MA, out_path=a)
    build_medicare(PFS, CURATED, SOURCE, YEAR, locality=MA, out_path=b)
    assert a.read_bytes() == b.read_bytes()
    data = jsonio.read_json(a)
    assert [r["code"] for r in data] == sorted(r["code"] for r in data)
