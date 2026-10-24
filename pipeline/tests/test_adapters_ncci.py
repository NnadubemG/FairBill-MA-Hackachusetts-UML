"""Tests for the NCCI PTP adapter: raw CMS export -> clean ncci stage CSV."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from pipeline.adapters.ncci_ptp import NcciAdapterError, adapt_ncci_ptp


def _read(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_maps_column_one_two_modifier_and_strips_marker(tmp_path):
    src = tmp_path / "in.csv"
    src.write_text(
        "Column 1,Column 2,Modifier\n"
        "*99213,80053,1\n"      # leading * = pre-existing marker, must be stripped
        "45378,45385,0\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.csv"
    n = adapt_ncci_ptp(src, out)
    assert n == 2
    rows = _read(out)
    assert rows[0] == {"code_1": "99213", "code_2": "80053", "modifier_indicator": "1"}
    assert rows[1] == {"code_1": "45378", "code_2": "45385", "modifier_indicator": "0"}


def test_accepts_alternate_header_spellings(tmp_path):
    src = tmp_path / "in.csv"
    src.write_text(
        "Column One,Column Two,Modifier 0=not allowed 1=allowed 9=not applicable\n"
        "70551,74177,9\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.csv"
    assert adapt_ncci_ptp(src, out) == 1
    assert _read(out)[0]["modifier_indicator"] == "9"


def test_missing_column_raises(tmp_path):
    src = tmp_path / "in.csv"
    src.write_text("foo,bar\n1,2\n", encoding="utf-8")
    with pytest.raises(NcciAdapterError):
        adapt_ncci_ptp(src, tmp_path / "out.csv")


def test_skips_short_and_blank_rows(tmp_path):
    src = tmp_path / "in.csv"
    src.write_text(
        "Column 1,Column 2,Modifier\n"
        "99213,80053,1\n"
        "\n"                 # blank line
        ",,\n",              # empty codes -> dropped
        encoding="utf-8",
    )
    out = tmp_path / "out.csv"
    assert adapt_ncci_ptp(src, out) == 1
