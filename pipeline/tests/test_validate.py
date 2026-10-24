"""Tests for the validate.py gate. Covers U30-U34 and property P7 (fail safe)."""

from __future__ import annotations

import copy
from pathlib import Path

from pipeline import jsonio
from pipeline.validate import validate

SOURCE = "test"
YEAR = 2025


def _write_set(tmp_path: Path, prices, medicare, procedures):
    p = tmp_path / "prices.json"
    m = tmp_path / "medicare.json"
    pr = tmp_path / "procedures.json"
    jsonio.write_json(p, prices)
    jsonio.write_json(m, medicare)
    jsonio.write_json(pr, procedures)
    return p, m, pr


def _validate(p, m, pr):
    """Validate the 3-file set, isolating the optional files to non-existent tmp paths
    so these tests never read real /data/processed files."""
    base = p.parent
    return validate(
        p, m, pr,
        reference_path=base / "no_reference.json",
        quantity_limits_path=base / "no_quantity_limits.json",
        bundle_pairs_path=base / "no_bundle_pairs.json",
    )


def _price(**over):
    base = {
        "hospital_id": "h1",
        "code": "99213",
        "code_system": "CPT",
        "payer_group": "commercial",
        "min_rate": 100.0,
        "median_rate": 150.0,
        "max_rate": 200.0,
        "cash_price": None,
        "gross_charge": None,
        "data_source": SOURCE,
        "data_year": YEAR,
    }
    base.update(over)
    return base


def _procedures():
    return [{"code": "99213", "plain_label": "Office visit",
             "code_system": "CPT", "category": None, "typical_max_units": None}]


# U30 pass: a clean set -> no problems
def test_u30_clean_passes(tmp_path):
    p, m, pr = _write_set(tmp_path, [_price()], [], _procedures())
    assert _validate(p, m, pr) == []


# U31 missing provenance
def test_u31_missing_data_source(tmp_path):
    p, m, pr = _write_set(tmp_path, [_price(data_source="")], [], _procedures())
    problems = _validate(p, m, pr)
    assert any("data_source" in x for x in problems)


# U32 negative price
def test_u32_negative_price(tmp_path):
    p, m, pr = _write_set(tmp_path, [_price(min_rate=-5.0)], [], _procedures())
    problems = _validate(p, m, pr)
    assert any("negative" in x for x in problems)


# U33 min > median
def test_u33_min_gt_median(tmp_path):
    p, m, pr = _write_set(tmp_path, [_price(min_rate=160.0)], [], _procedures())
    problems = _validate(p, m, pr)
    assert any("min_rate > median_rate" in x for x in problems)


# U34 unknown code
def test_u34_unknown_code(tmp_path):
    p, m, pr = _write_set(tmp_path, [_price(code="00000")], [], _procedures())
    problems = _validate(p, m, pr)
    assert any("not in procedures.json" in x for x in problems)


# P7 fail safe: validate reports but never mutates the input files
def test_p7_does_not_mutate(tmp_path):
    prices = [_price(min_rate=-5.0, code="00000")]
    p, m, pr = _write_set(tmp_path, prices, [], _procedures())
    before = p.read_bytes()
    snapshot = copy.deepcopy(prices)

    problems = _validate(p, m, pr)
    assert problems  # it found issues

    # the file on disk is untouched, and the in-memory input is unchanged
    assert p.read_bytes() == before
    assert prices == snapshot


# medicare records are validated too
def test_medicare_checked(tmp_path):
    medicare = [{"code": "00000", "code_system": "HCPCS", "medicare_price": -1.0,
                 "ma_range_low": None, "ma_range_high": None,
                 "data_source": "", "data_year": YEAR}]
    p, m, pr = _write_set(tmp_path, [], medicare, _procedures())
    problems = _validate(p, m, pr)
    assert any("medicare" in x for x in problems)
    assert any("not in procedures.json" in x for x in problems)
    assert any("negative" in x for x in problems)
    assert any("data_source" in x for x in problems)
