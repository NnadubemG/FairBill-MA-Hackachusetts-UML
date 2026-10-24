"""Tests for code + confidence rules (spec task 6).

Covers T2 (no codes -> null/low/confirm), T3 (unknown code -> confirm),
T4 (procedures.json missing -> skip check + warn, no error), and property P2
(null code implies needs_confirmation and low confidence).
"""

from __future__ import annotations

import json

from hypothesis import given
from hypothesis import strategies as st

from backend.extract._contracts import LineItem
from backend.extract.codes import (
    CODE_CHECK_UNAVAILABLE,
    apply_code_and_confidence,
    load_known_codes,
)


def _line(id_, code=None, system=None, amount=100.0):
    return LineItem(id=id_, description="x", billed_amount=amount, code=code, code_system=system)


# --- T2: no codes ----------------------------------------------------------

def test_t2_no_codes_become_low_and_confirm():
    lines = [_line("1"), _line("2")]
    out, conf, warnings = apply_code_and_confidence(
        lines, {"1": "high", "2": "high"}, known_codes={"99213"}
    )
    for c in conf:
        assert c.confidence == "low"
        assert c.needs_confirmation is True
    assert all(li.code is None for li in out)


# --- T3: unknown code ------------------------------------------------------

def test_t3_unknown_code_kept_but_needs_confirmation():
    lines = [_line("1", code="00000", system="CPT")]
    out, conf, _ = apply_code_and_confidence(
        lines, {"1": "high"}, known_codes={"99213"}
    )
    assert out[0].code == "00000"          # kept, not cleared
    assert conf[0].needs_confirmation is True


def test_known_code_high_confidence_no_confirm():
    lines = [_line("1", code="99213", system="CPT")]
    out, conf, _ = apply_code_and_confidence(
        lines, {"1": "high"}, known_codes={"99213"}
    )
    assert out[0].code == "99213"
    assert conf[0].needs_confirmation is False
    assert conf[0].confidence == "high"


def test_low_confidence_coded_line_has_code_cleared():
    # Model unsure of the code -> we do not trust it; clear to null.
    lines = [_line("1", code="99213", system="CPT")]
    out, conf, _ = apply_code_and_confidence(
        lines, {"1": "low"}, known_codes={"99213"}
    )
    assert out[0].code is None
    assert out[0].code_system is None
    assert conf[0].confidence == "low"
    assert conf[0].needs_confirmation is True


def test_medium_confidence_below_threshold_confirms():
    lines = [_line("1", code="99213", system="CPT")]
    _, conf, _ = apply_code_and_confidence(
        lines, {"1": "medium"}, known_codes={"99213"}
    )
    assert conf[0].confidence == "medium"
    assert conf[0].needs_confirmation is True  # below default "high" threshold


def test_missing_model_confidence_defaults_low():
    lines = [_line("1", code="99213", system="CPT")]
    out, conf, _ = apply_code_and_confidence(lines, {}, known_codes={"99213"})
    # No confidence given -> treated as low -> code cleared.
    assert out[0].code is None
    assert conf[0].needs_confirmation is True


# --- T4: procedures.json missing -------------------------------------------

def test_t4_known_codes_none_skips_check_and_warns():
    lines = [_line("1", code="00000", system="CPT")]
    out, conf, warnings = apply_code_and_confidence(
        lines, {"1": "high"}, known_codes=None
    )
    assert out[0].code == "00000"
    # Check skipped: a high-confidence code is not forced to confirm by membership.
    assert conf[0].needs_confirmation is False
    assert CODE_CHECK_UNAVAILABLE in warnings


def test_load_known_codes_missing_file_returns_none(tmp_path):
    missing = tmp_path / "nope.json"
    assert load_known_codes(missing) is None


def test_load_known_codes_reads_codes(tmp_path):
    p = tmp_path / "procedures.json"
    p.write_text(json.dumps([
        {"code": "99213", "plain_label": "Office visit"},
        {"code": "80053", "plain_label": "Metabolic panel"},
    ]))
    codes = load_known_codes(p)
    assert codes == {"99213", "80053"}


def test_load_known_codes_empty_file_is_empty_set_not_none(tmp_path):
    p = tmp_path / "procedures.json"
    p.write_text("[]")
    assert load_known_codes(p) == set()  # present-but-empty differs from absent


def test_load_known_codes_malformed_returns_none(tmp_path):
    p = tmp_path / "procedures.json"
    p.write_text("{not json")
    assert load_known_codes(p) is None


# --- Property P2 -----------------------------------------------------------

_conf_values = st.sampled_from(["high", "medium", "low"])
_codes = st.one_of(st.none(), st.sampled_from(["99213", "00000", "80053"]))


@given(
    st.lists(
        st.tuples(st.text(min_size=1, max_size=4), _codes, _conf_values),
        min_size=0,
        max_size=8,
        unique_by=lambda t: t[0],
    ),
    st.one_of(st.none(), st.just({"99213", "80053"})),
)
def test_p2_null_code_implies_confirm_and_low(rows, known):
    lines = [_line(id_, code=code) for id_, code, _ in rows]
    model_conf = {id_: conf for id_, _, conf in rows}
    out_lines, confidences, _ = apply_code_and_confidence(
        lines, model_conf, known_codes=known
    )
    by_id = {c.line_item_id: c for c in confidences}
    line_by_id = {li.id: li for li in out_lines}
    for lid, c in by_id.items():
        if line_by_id[lid].code is None:
            assert c.needs_confirmation is True
            assert c.confidence == "low"
    # One confidence entry per line, ids preserved.
    assert len(confidences) == len(lines)
