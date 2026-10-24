"""Tests for the curated procedure list loader and the procedures stage.

Covers design test cases U1-U5. Fixtures are tiny synthetic CSVs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline import jsonio
from pipeline.procedure_list import (
    ProcedureListError,
    curated_codes,
    load_procedures,
)
from pipeline.stages.procedures import build_procedures

FIXTURES = Path(__file__).parent / "fixtures"


# U1 happy path
def test_u1_happy_path_optional_fields_become_none():
    procs = load_procedures(FIXTURES / "procedures_ok.csv")
    assert len(procs) == 2
    by_code = {p.code: p for p in procs}

    p1 = by_code["99213"]
    assert p1.plain_label == "Office visit established patient"
    assert p1.code_system == "CPT"
    assert p1.category == "evaluation"
    assert p1.typical_max_units == 1.0

    p2 = by_code["80053"]
    # empty category / typical_max_units -> None, never a placeholder
    assert p2.category is None
    assert p2.typical_max_units is None

    assert curated_codes(procs) == {"99213", "80053"}


# U2 missing column
def test_u2_missing_column_raises():
    with pytest.raises(ProcedureListError):
        load_procedures(FIXTURES / "procedures_missing_col.csv")


# U3 empty code
def test_u3_empty_code_raises():
    with pytest.raises(ProcedureListError):
        load_procedures(FIXTURES / "procedures_empty_code.csv")


# U4 duplicate code
def test_u4_duplicate_code_raises():
    with pytest.raises(ProcedureListError):
        load_procedures(FIXTURES / "procedures_dup_code.csv")


# U5 empty file (header only)
def test_u5_header_only_is_empty():
    procs = load_procedures(FIXTURES / "procedures_header_only.csv")
    assert procs == []
    assert curated_codes(procs) == set()


# Stage: writes a deterministic, code-sorted procedures.json
def test_stage_writes_sorted_procedures(tmp_path: Path):
    out = tmp_path / "procedures.json"
    count = build_procedures(FIXTURES / "procedures_ok.csv", out)
    assert count == 2

    data = jsonio.read_json(out)
    assert [r["code"] for r in data] == ["80053", "99213"]  # sorted by code
    # null preserved for missing optional fields
    md = {r["code"]: r for r in data}["80053"]
    assert md["category"] is None
    assert md["typical_max_units"] is None


def test_stage_output_is_deterministic(tmp_path: Path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    build_procedures(FIXTURES / "procedures_ok.csv", a)
    build_procedures(FIXTURES / "procedures_ok.csv", b)
    assert a.read_bytes() == b.read_bytes()
