"""Tests for the run.py CLI caching. Covers U35."""

from __future__ import annotations

import os
import time
from pathlib import Path

from pipeline.run import is_up_to_date, main


def _touch(path: Path, mtime: float):
    path.write_text("x", encoding="utf-8")
    os.utime(path, (mtime, mtime))


# U35: output newer than inputs -> up to date (cached); input newer -> stale
def test_u35_cache_up_to_date(tmp_path):
    inp = tmp_path / "in.csv"
    out = tmp_path / "out.json"
    _touch(inp, 1000.0)
    _touch(out, 2000.0)  # output newer than input
    assert is_up_to_date(out, [inp]) is True


def test_u35_cache_stale_when_input_newer(tmp_path):
    inp = tmp_path / "in.csv"
    out = tmp_path / "out.json"
    _touch(out, 1000.0)
    _touch(inp, 2000.0)  # input newer than output
    assert is_up_to_date(out, [inp]) is False


def test_u35_missing_output_not_up_to_date(tmp_path):
    inp = tmp_path / "in.csv"
    _touch(inp, 1000.0)
    assert is_up_to_date(tmp_path / "missing.json", [inp]) is False


def test_u35_missing_input_ignored(tmp_path):
    out = tmp_path / "out.json"
    _touch(out, 1000.0)
    # a non-existent input can't make the output stale
    assert is_up_to_date(out, [tmp_path / "nope.csv"]) is True


# CLI: 'procedures' runs and respects --force via the real stage, using a built file.
def test_cli_procedures_and_cache(tmp_path, monkeypatch):
    from pipeline import config
    from pipeline.stages import procedures as proc_stage

    # Point the stage's default inputs/outputs at temp files.
    src = tmp_path / "procedure_list.csv"
    src.write_text(
        "code,code_system,plain_label,category,typical_max_units\n"
        "99213,CPT,Office visit,eval,1\n",
        encoding="utf-8",
    )
    out = tmp_path / "procedures.json"
    monkeypatch.setattr(config, "PROCEDURE_LIST_CSV", src)
    monkeypatch.setattr(config, "PROCEDURES_JSON", out)
    # run.py reads config at call time inside _run_stage, so patching config works.

    rc = main(["procedures"])
    assert rc == 0
    assert out.exists()

    # Second run without --force: output newer than input -> cached (file not rewritten).
    before = out.stat().st_mtime
    time.sleep(0.01)
    rc = main(["procedures"])
    assert rc == 0
    assert out.stat().st_mtime == before  # unchanged -> was cached
