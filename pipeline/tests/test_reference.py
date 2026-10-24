"""Tests for the reference stage + validate extension. RF1-RF10."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline import jsonio
from pipeline.stages.reference import ReferenceError, build_reference, write_reference
from pipeline.validate import validate


def _proc(code, cs="CPT"):
    return {"code": code, "code_system": cs, "plain_label": code,
            "category": None, "typical_max_units": None}


def _med(code, price, year=2025, cs="HCPCS", src="CMS PFS"):
    return {"code": code, "code_system": cs, "medicare_price": price,
            "ma_range_low": None, "ma_range_high": None,
            "data_source": src, "data_year": year}


def _gross(code, charge, hospital, year=2025, cs="CPT", src="MGH MRF"):
    return {"hospital_id": hospital, "code": code, "code_system": cs,
            "payer_group": "gross", "min_rate": None, "median_rate": None,
            "max_rate": None, "cash_price": None, "gross_charge": charge,
            "data_source": src, "data_year": year}


# RF1 combine
def test_rf1_combine():
    refs = build_reference(
        [_proc("99213")],
        [_med("99213", 92.47)],
        [_gross("99213", 400.0, "a"), _gross("99213", 600.0, "b")],
    )
    assert len(refs) == 1
    r = refs[0]
    assert r.code == "99213"
    assert r.medicare_price == 92.47
    assert r.ma_range_low == 400.0
    assert r.ma_range_high == 600.0
    assert r.code_system == "CPT"  # from procedures.json
    assert r.data_source and r.data_year


# RF2 medicare only
def test_rf2_medicare_only():
    refs = build_reference([_proc("99213")], [_med("99213", 92.47)], [])
    assert refs[0].medicare_price == 92.47
    assert refs[0].ma_range_low is None
    assert refs[0].ma_range_high is None


# RF3 range only
def test_rf3_range_only():
    refs = build_reference([_proc("80053")], [], [_gross("80053", 420.0, "b")])
    assert refs[0].medicare_price is None
    assert refs[0].ma_range_low == 420.0
    assert refs[0].ma_range_high == 420.0


# RF4 neither -> no record
def test_rf4_neither():
    refs = build_reference([_proc("99213"), _proc("11111")], [_med("99213", 50.0)], [])
    codes = {r.code for r in refs}
    assert "99213" in codes
    assert "11111" not in codes  # no data -> no record


# RF5 differing years -> older year + note
def test_rf5_differing_years():
    refs = build_reference(
        [_proc("99213")],
        [_med("99213", 92.47, year=2025)],
        [_gross("99213", 400.0, "a", year=2024)],
    )
    r = refs[0]
    assert r.data_year == 2024
    assert "older year shown" in r.data_source


# RF6 code_system never null (from procedures even if medicare/gross differ)
def test_rf6_code_system_from_procedures():
    refs = build_reference(
        [_proc("70553", cs="CPT")],
        [_med("70553", 200.0, cs="HCPCS")],
        [],
    )
    assert refs[0].code_system == "CPT"


# RF6b code_system missing everywhere -> raise
def test_rf6b_missing_code_system_raises():
    proc = {"code": "99213", "code_system": None, "plain_label": "x",
            "category": None, "typical_max_units": None}
    med = {"code": "99213", "code_system": None, "medicare_price": 50.0,
           "ma_range_low": None, "ma_range_high": None,
           "data_source": "CMS", "data_year": 2025}
    with pytest.raises(ReferenceError):
        build_reference([proc], [med], [])


# RF10 determinism + sorted
def test_rf10_determinism_and_sorted(tmp_path):
    procs = [_proc("99213"), _proc("80053")]
    med = [_med("99213", 92.47)]
    prices = [_gross("80053", 420.0, "b")]
    jsonio.write_json(tmp_path / "procedures.json", procs)
    jsonio.write_json(tmp_path / "medicare.json", med)
    jsonio.write_json(tmp_path / "prices.json", prices)

    a = tmp_path / "ref_a.json"
    b = tmp_path / "ref_b.json"
    n1 = write_reference(tmp_path / "procedures.json", tmp_path / "medicare.json",
                         tmp_path / "prices.json", a)
    n2 = write_reference(tmp_path / "procedures.json", tmp_path / "medicare.json",
                         tmp_path / "prices.json", b)
    assert n1 == n2 == 2
    assert a.read_bytes() == b.read_bytes()
    data = jsonio.read_json(a)
    assert [r["code"] for r in data] == ["80053", "99213"]  # sorted


# ---- validate.py extension ----

def _write_validate_set(tmp_path: Path, reference):
    jsonio.write_json(tmp_path / "procedures.json", [_proc("99213")])
    jsonio.write_json(tmp_path / "prices.json", [])
    jsonio.write_json(tmp_path / "medicare.json", [])
    jsonio.write_json(tmp_path / "reference.json", reference)
    # quantity_limits/bundle_pairs point at files that do not exist, so validate() skips them
    # instead of reading the real /data/processed copies.
    return (tmp_path / "prices.json", tmp_path / "medicare.json",
            tmp_path / "procedures.json", tmp_path / "reference.json",
            tmp_path / "quantity_limits.json", tmp_path / "bundle_pairs.json")


def _ref_rec(**over):
    base = {"code": "99213", "code_system": "CPT", "medicare_price": 92.47,
            "ma_range_low": 400.0, "ma_range_high": 600.0,
            "data_source": "CMS PFS; MA gross charges", "data_year": 2025}
    base.update(over)
    return base


def test_reference_clean_passes(tmp_path):
    paths = _write_validate_set(tmp_path, [_ref_rec()])
    assert validate(*paths) == []


# RF7 duplicate (code, code_system)
def test_rf7_duplicate_key_fails(tmp_path):
    paths = _write_validate_set(tmp_path, [_ref_rec(), _ref_rec()])
    problems = validate(*paths)
    assert any("duplicate (code, code_system)" in p for p in problems)


# RF8 range order
def test_rf8_range_order_fails(tmp_path):
    paths = _write_validate_set(tmp_path, [_ref_rec(ma_range_low=600.0, ma_range_high=400.0)])
    problems = validate(*paths)
    assert any("ma_range_low > ma_range_high" in p for p in problems)


# RF9 negative value
def test_rf9_negative_fails(tmp_path):
    paths = _write_validate_set(tmp_path, [_ref_rec(medicare_price=-1.0)])
    problems = validate(*paths)
    assert any("negative" in p for p in problems)


# missing code_system
def test_reference_missing_code_system_fails(tmp_path):
    paths = _write_validate_set(tmp_path, [_ref_rec(code_system=None)])
    problems = validate(*paths)
    assert any("missing code_system" in p for p in problems)
