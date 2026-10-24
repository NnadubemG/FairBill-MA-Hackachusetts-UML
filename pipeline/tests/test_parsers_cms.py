"""Tests for the CMS Hospital Price Transparency JSON parser (format_id=cms_json).

Covers the real CMS v2.x machine-readable shape: a top-level object whose
``standard_charge_information`` array holds items with ``code_information`` and
``standard_charges`` (gross/discounted_cash/payers_information). The parser must stream,
filter to curated CPT/HCPCS codes, keep dollar negotiated rates, pass %/algorithm rates
through verbatim (so the prices stage skips them), and ignore non-curated code systems.
"""

from __future__ import annotations

import json
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from pipeline.parsers.base import Parser, RawPriceRow
from pipeline.parsers.cms_hospital_json import CmsHospitalJsonParser
from pipeline.registry import get_parser

# A compact file that mirrors the real Lahey structure.
SAMPLE = {
    "hospital_name": "Test Hospital",
    "last_updated_on": "2026-04-01",
    "version": "2.0.0",
    "standard_charge_information": [
        {
            "description": "Office visit",
            "code_information": [{"code": "99213", "type": "CPT"}],
            "standard_charges": [
                {
                    "gross_charge": 300.0,
                    "discounted_cash": 180.0,
                    "payers_information": [
                        {"payer_name": "BCBS", "plan_name": "PPO",
                         "methodology": "fee schedule", "standard_charge_dollar": 145.0},
                        {"payer_name": "Aetna", "plan_name": "HMO",
                         "standard_charge_percentage": 45},        # -> "45%" (skipped later)
                        {"payer_name": "Cigna", "plan_name": "Open",
                         "standard_charge_algorithm": "see addendum"},  # -> "algorithm"
                    ],
                }
            ],
        },
        {
            "description": "A drug by NDC - must be ignored",
            "code_information": [{"code": "99213", "type": "NDC"}],  # non-curated system
            "standard_charges": [{"gross_charge": 9.99}],
        },
        {
            "description": "Not in curated list",
            "code_information": [{"code": "11111", "type": "CPT"}],
            "standard_charges": [{"gross_charge": 50.0}],
        },
        {
            "description": "Basic panel",
            "code_information": [{"code": "80053", "type": "HCPCS"}],
            "standard_charges": [
                {"payers_information": [
                    {"payer_name": "Tufts", "standard_charge_dollar": 22.5},
                ]}
            ],
        },
    ],
}

CURATED = {"99213", "80053"}


def _write(tmp_path: Path) -> str:
    p = tmp_path / "cms.json"
    p.write_text(json.dumps(SAMPLE), encoding="utf-8")
    return str(p)


def _rows(tmp_path, curated=CURATED):
    return list(CmsHospitalJsonParser().rows(_write(tmp_path), curated))


def test_registry_has_cms_parser():
    parser = get_parser("cms_json")
    assert isinstance(parser, Parser)
    assert parser.format_id == "cms_json"


def test_gross_cash_and_dollar_negotiated_mapped(tmp_path):
    rows = _rows(tmp_path)
    by = lambda code, kind, payer="": [
        r for r in rows if r.code == code and r.rate_kind == kind and (not payer or payer in r.raw_payer)
    ]
    # 99213: gross + cash + 3 payer rows (dollar, %, algorithm) = 5
    assert len(by("99213", "gross")) == 1
    assert by("99213", "gross")[0].raw_rate == "300.0"
    assert by("99213", "cash")[0].raw_rate == "180.0"
    bcbs = by("99213", "negotiated", "BCBS")[0]
    assert bcbs.raw_rate == "145.0"
    assert bcbs.code_system == "CPT"


def test_percentage_and_algorithm_passed_through_not_dropped(tmp_path):
    rows = _rows(tmp_path)
    negs = [r for r in rows if r.code == "99213" and r.rate_kind == "negotiated"]
    raws = {r.raw_rate for r in negs}
    assert "145.0" in raws
    assert "45%" in raws            # percentage preserved so prices stage can skip it
    assert "algorithm" in raws      # algorithm marker preserved


def test_non_curated_code_and_system_excluded(tmp_path):
    rows = _rows(tmp_path)
    assert all(r.code in CURATED for r in rows)
    assert not any(r.code == "11111" for r in rows)   # curated filter
    # The NDC-typed 99213 must not add a gross row of 9.99.
    assert not any(r.raw_rate == "9.99" for r in rows)


def test_hcpcs_dollar_row(tmp_path):
    rows = _rows(tmp_path)
    tufts = [r for r in rows if r.code == "80053" and r.rate_kind == "negotiated"]
    assert len(tufts) == 1
    assert tufts[0].raw_rate == "22.5"
    assert tufts[0].code_system == "HCPCS"


def test_empty_curated_yields_nothing(tmp_path):
    assert _rows(tmp_path, set()) == []


def test_streams_across_tiny_chunks(tmp_path, monkeypatch):
    import pipeline.parsers.cms_hospital_json as mod

    monkeypatch.setattr(mod, "_READ_CHUNK", 5)  # force many refills mid-object
    rows = list(mod.CmsHospitalJsonParser().rows(_write(tmp_path), CURATED))
    assert {r.code for r in rows} == CURATED
    assert any(r.rate_kind == "negotiated" and r.raw_rate == "145.0" for r in rows)


@given(st.sets(st.sampled_from(["99213", "80053", "11111", "00000"])))
def test_only_curated_codes_yielded(curated):
    # Hypothesis-driven: can't use the function-scoped tmp_path fixture here, so write
    # the sample to a temp file inside the test.
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
        json.dump(SAMPLE, fh)
        path = fh.name
    try:
        for r in CmsHospitalJsonParser().rows(path, curated):
            assert r.code in curated
            assert isinstance(r, RawPriceRow)
    finally:
        Path(path).unlink(missing_ok=True)
