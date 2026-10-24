"""Tests for the quantity_limits stage + its validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline import jsonio
from pipeline.stages.quantity_limits import build_quantity_limits
from pipeline.validate import validate

SOURCE = "test-source"
YEAR = 2025


def _proc(code, units, cs="CPT"):
    return {"code": code, "code_system": cs, "plain_label": code,
            "category": None, "typical_max_units": units}


def _write_procs(tmp_path, procs):
    p = tmp_path / "procedures.json"
    jsonio.write_json(p, procs)
    return p


# QL1: one QuantityLimit per procedure with typical_max_units; null units -> no record
def test_ql1_emits_from_units(tmp_path):
    procs = _write_procs(tmp_path, [_proc("99213", 1), _proc("J1100", 8), _proc("80053", None)])
    out = tmp_path / "quantity_limits.json"
    n = build_quantity_limits(SOURCE, YEAR, procs, out)
    assert n == 2  # 80053 has null units -> skipped

    data = {r["code"]: r for r in jsonio.read_json(out)}
    assert data["99213"]["max_units"] == 1
    assert data["99213"]["code_system"] == "CPT"
    assert data["99213"]["data_source"] == SOURCE
    assert data["99213"]["data_year"] == YEAR
    assert "80053" not in data


# QL2: non-positive units dropped (never emit an invalid limit)
def test_ql2_non_positive_dropped(tmp_path):
    procs = _write_procs(tmp_path, [_proc("99213", 0), _proc("80053", -3), _proc("71046", 2)])
    out = tmp_path / "quantity_limits.json"
    n = build_quantity_limits(SOURCE, YEAR, procs, out)
    assert n == 1
    assert [r["code"] for r in jsonio.read_json(out)] == ["71046"]


# QL3: empty/whitespace data_source rejected (honest provenance required)
def test_ql3_requires_data_source(tmp_path):
    procs = _write_procs(tmp_path, [_proc("99213", 1)])
    with pytest.raises(ValueError):
        build_quantity_limits("  ", YEAR, procs, tmp_path / "q.json")


# QL4: deterministic + sorted
def test_ql4_sorted_deterministic(tmp_path):
    procs = _write_procs(tmp_path, [_proc("99213", 1), _proc("11111", 2)])
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    build_quantity_limits(SOURCE, YEAR, procs, a)
    build_quantity_limits(SOURCE, YEAR, procs, b)
    assert a.read_bytes() == b.read_bytes()
    assert [r["code"] for r in jsonio.read_json(a)] == ["11111", "99213"]


# QL5: validate.py flags a non-positive max_units and unknown code
def test_ql5_validate_catches_bad(tmp_path):
    jsonio.write_json(tmp_path / "procedures.json", [_proc("99213", 1)])
    jsonio.write_json(tmp_path / "prices.json", [])
    jsonio.write_json(tmp_path / "medicare.json", [])
    jsonio.write_json(tmp_path / "quantity_limits.json", [
        {"code": "99213", "code_system": "CPT", "max_units": 0,
         "data_source": "s", "data_year": 2025},  # non-positive
        {"code": "00000", "code_system": "CPT", "max_units": 1,
         "data_source": "s", "data_year": 2025},  # unknown code
    ])
    problems = validate(
        prices_path=tmp_path / "prices.json",
        medicare_path=tmp_path / "medicare.json",
        procedures_path=tmp_path / "procedures.json",
        reference_path=tmp_path / "missing.json",
        quantity_limits_path=tmp_path / "quantity_limits.json",
        bundle_pairs_path=tmp_path / "missing2.json",
    )
    assert any("max_units must be > 0" in p for p in problems)
    assert any("not in procedures.json" in p for p in problems)
