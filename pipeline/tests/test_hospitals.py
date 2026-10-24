"""Tests for the hospitals stage. Covers U29."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline import jsonio
from pipeline.stages.hospitals import (
    HospitalsInputError,
    build_hospitals,
    load_hospitals,
)

FIXTURES = Path(__file__).parent / "fixtures"
INPUT = FIXTURES / "hospitals_input.csv"


# U29: hospitals.json has public fields; bindings retain format_id + source_file
def test_u29_public_fields_and_bindings():
    public, bindings = load_hospitals(INPUT)
    assert len(public) == 3

    mgh = next(r for r in public if r["id"] == "mgh")
    assert mgh == {
        "id": "mgh",
        "name": "Massachusetts General Hospital",
        "city": "Boston",
        "type": "academic",
    }
    # public record must NOT leak pipeline-internal fields
    assert "format_id" not in mgh
    assert "source_file" not in mgh

    # blank city/type -> null
    rural = next(r for r in public if r["id"] == "rural1")
    assert rural["city"] is None
    assert rural["type"] is None

    # bindings carry the parser format + file for the prices stage
    bmap = {b.hospital_id: b for b in bindings}
    assert bmap["bmc"].format_id == "generic_json"
    assert bmap["bmc"].source_file == "bmc_prices.json"


def test_build_writes_sorted_outputs(tmp_path: Path):
    out = tmp_path / "hospitals.json"
    manifest = tmp_path / "hospital_bindings.json"
    count = build_hospitals(INPUT, out, manifest)
    assert count == 3

    public = jsonio.read_json(out)
    assert [r["id"] for r in public] == ["bmc", "mgh", "rural1"]  # sorted by id

    bindings = jsonio.read_json(manifest)
    assert [b["hospital_id"] for b in bindings] == ["bmc", "mgh", "rural1"]


def test_build_is_deterministic(tmp_path: Path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    ma, mb = tmp_path / "ma.json", tmp_path / "mb.json"
    build_hospitals(INPUT, a, ma)
    build_hospitals(INPUT, b, mb)
    assert a.read_bytes() == b.read_bytes()
    assert ma.read_bytes() == mb.read_bytes()


def test_missing_column_raises(tmp_path: Path):
    bad = tmp_path / "bad.csv"
    bad.write_text("id,name,city,type\nmgh,MGH,Boston,academic\n", encoding="utf-8")
    with pytest.raises(HospitalsInputError):
        load_hospitals(bad)
