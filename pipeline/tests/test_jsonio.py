"""Tests for deterministic JSON I/O (task 2 scaffolding)."""

from __future__ import annotations

from pathlib import Path

from contracts.types import ProcedureInfo
from pipeline import jsonio


def test_dumps_is_sorted_and_has_trailing_newline():
    s = jsonio.dumps({"b": 1, "a": 2})
    assert s.endswith("\n")
    # sort_keys -> "a" appears before "b"
    assert s.index('"a"') < s.index('"b"')


def test_dumps_dataclass_keeps_none_not_placeholder():
    s = jsonio.dumps(ProcedureInfo(code="99213", plain_label="Office visit"))
    # Missing optional fields serialize as null, never a placeholder number/string.
    assert '"category": null' in s
    assert '"typical_max_units": null' in s


def test_write_then_read_roundtrip(tmp_path: Path):
    p = tmp_path / "out" / "data.json"
    obj = [{"code": "99213", "x": None}]
    jsonio.write_json(p, obj)
    assert jsonio.read_json(p) == obj
    # parent dir was created
    assert p.exists()


def test_write_is_deterministic(tmp_path: Path):
    obj = {"z": [3, 2, 1], "a": {"n": None, "m": 1}}
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    jsonio.write_json(a, obj)
    jsonio.write_json(b, obj)
    assert a.read_bytes() == b.read_bytes()
