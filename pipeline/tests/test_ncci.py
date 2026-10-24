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


# Output conforms to contracts/bundle-pair.schema.json (loadable as BundlePair).
def test_output_matches_bundle_pair_contract(tmp_path):
    from contracts.types import BundlePair

    out = tmp_path / "bundle_pairs.json"
    build_ncci_pairs(NCCI, CURATED, SOURCE, YEAR, out_path=out)
    for rec in jsonio.read_json(out):
        bp = BundlePair(**rec)  # exact field match -> raises if shape drifts
        assert bp.modifier_indicator in {"0", "1", "9"}
        assert bp.data_source and bp.data_year is not None


# validate.py flags bad bundle pairs (unknown code, bad indicator, duplicate)
def test_validate_catches_bad_bundle_pairs(tmp_path):
    jsonio.write_json(tmp_path / "procedures.json", [
        {"code": "99213", "code_system": "CPT", "plain_label": "x",
         "category": None, "typical_max_units": None},
        {"code": "80053", "code_system": "CPT", "plain_label": "y",
         "category": None, "typical_max_units": None},
    ])
    jsonio.write_json(tmp_path / "prices.json", [])
    jsonio.write_json(tmp_path / "medicare.json", [])
    jsonio.write_json(tmp_path / "bundle_pairs.json", [
        {"code_1": "99213", "code_2": "00000", "modifier_indicator": "0",
         "data_source": "s", "data_year": 2025},  # unknown code_2
        {"code_1": "99213", "code_2": "80053", "modifier_indicator": "7",
         "data_source": "s", "data_year": 2025},  # bad indicator
    ])
    from pipeline.validate import validate

    problems = validate(
        prices_path=tmp_path / "prices.json",
        medicare_path=tmp_path / "medicare.json",
        procedures_path=tmp_path / "procedures.json",
        reference_path=tmp_path / "missing.json",
        quantity_limits_path=tmp_path / "missing2.json",
        bundle_pairs_path=tmp_path / "bundle_pairs.json",
    )
    assert any("not in procedures.json" in p for p in problems)
    assert any("modifier_indicator must be" in p for p in problems)
