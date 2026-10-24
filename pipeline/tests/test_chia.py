"""Tests for the CHIA stage. Covers U28."""

from __future__ import annotations

from pathlib import Path

from pipeline import jsonio
from pipeline.stages.chia import build_chia_tiers

FIXTURES = Path(__file__).parent / "fixtures"
CHIA = FIXTURES / "chia_sample.csv"
SOURCE = "CHIA relative price (test)"
YEAR = 2025


# U28: tier per hospital where available; hospital without data -> no record
def test_u28_tier_where_available(tmp_path):
    out = tmp_path / "chia_tiers.json"
    count = build_chia_tiers(CHIA, SOURCE, YEAR, out_path=out)
    data = jsonio.read_json(out)
    by = {r["hospital_id"]: r for r in data}

    # mgh: both relative_price and tier present
    assert by["mgh"]["relative_price"] == 1.25
    assert by["mgh"]["tier"] == "high"
    assert by["mgh"]["data_source"] == SOURCE
    assert by["mgh"]["data_year"] == YEAR

    # bmc: tier only, relative_price null
    assert by["bmc"]["relative_price"] is None
    assert by["bmc"]["tier"] == "mid"

    # rural1: relative_price only, tier null
    assert by["rural1"]["relative_price"] == 0.85
    assert by["rural1"]["tier"] is None

    # nodata: neither -> no record (absence, not placeholder)
    assert "nodata" not in by
    assert count == len(by) == 3


def test_output_sorted_and_deterministic(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    build_chia_tiers(CHIA, SOURCE, YEAR, out_path=a)
    build_chia_tiers(CHIA, SOURCE, YEAR, out_path=b)
    assert a.read_bytes() == b.read_bytes()
    data = jsonio.read_json(a)
    assert [r["hospital_id"] for r in data] == sorted(r["hospital_id"] for r in data)
