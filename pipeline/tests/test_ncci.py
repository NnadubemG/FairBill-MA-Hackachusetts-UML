"""Tests for the NCCI stage. Covers U27."""

from __future__ import annotations

from pathlib import Path

from pipeline import jsonio
from pipeline.stages.ncci import build_ncci_pairs

FIXTURES = Path(__file__).parent / "fixtures"
NCCI = FIXTURES / "ncci_sample.csv"
CURATED = {"99213", "80053", "70553"}
SOURCE = "NCCI PTP edits (test)"
YEAR = 2025


# U27: pair kept only when both codes curated; modifier indicator retained
def test_u27_both_codes_curated_kept(tmp_path):
    out = tmp_path / "ncci_pairs.json"
    count = build_ncci_pairs(NCCI, CURATED, SOURCE, YEAR, out_path=out)
    data = jsonio.read_json(out)
    pairs = {(r["code_1"], r["code_2"]): r for r in data}

    # 99213/80053 both curated -> kept, indicator retained
    assert ("99213", "80053") in pairs
    assert pairs[("99213", "80053")]["modifier_indicator"] == "1"
    assert pairs[("99213", "80053")]["data_source"] == SOURCE
    assert pairs[("99213", "80053")]["data_year"] == YEAR

    # 70553/80053 both curated -> kept
    assert ("70553", "80053") in pairs

    # any pair touching non-curated 11111 -> dropped
    assert not any("11111" in (a, b) for (a, b) in pairs)
    assert count == len(pairs)


def test_output_sorted_and_deterministic(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    build_ncci_pairs(NCCI, CURATED, SOURCE, YEAR, out_path=a)
    build_ncci_pairs(NCCI, CURATED, SOURCE, YEAR, out_path=b)
    assert a.read_bytes() == b.read_bytes()
    data = jsonio.read_json(a)
    keys = [(r["code_1"], r["code_2"]) for r in data]
    assert keys == sorted(keys)
