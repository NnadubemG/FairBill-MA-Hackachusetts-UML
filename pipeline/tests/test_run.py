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


def test_cli_all_end_to_end(tmp_path, monkeypatch):
    """`run all` produces every processed output from tiny fixtures (wiring check)."""
    from pipeline import config, jsonio

    raw = tmp_path / "raw"
    proc = tmp_path / "processed"
    raw.mkdir()
    proc.mkdir()

    # Curated procedure list.
    (tmp_path / "procedure_list.csv").write_text(
        "code,code_system,plain_label,category,typical_max_units\n"
        "99213,CPT,Office visit,eval,1\n"
        "80053,CPT,Metabolic panel,lab,\n",
        encoding="utf-8",
    )
    # Hospitals input (binds each hospital to a raw file + parser format).
    (tmp_path / "hospitals_input.csv").write_text(
        "id,name,city,type,format_id,source_file\n"
        "mgh,MGH,Boston,academic,generic_csv,mgh.csv\n",
        encoding="utf-8",
    )
    # Raw hospital price file (long format).
    (raw / "mgh.csv").write_text(
        "code,code_system,payer,rate,rate_kind\n"
        "99213,CPT,BCBS,150.00,negotiated\n"
        "99213,CPT,,500.00,gross\n"
        "80053,CPT,,90.00,gross\n",
        encoding="utf-8",
    )
    # Raw CMS PFS, NCCI, CHIA.
    (raw / "cms_pfs.csv").write_text(
        "hcpcs,locality,payment_amount\n99213,10112,92.47\n", encoding="utf-8"
    )
    (raw / "ncci_ptp.csv").write_text(
        "code_1,code_2,modifier_indicator\n99213,80053,1\n", encoding="utf-8"
    )
    (raw / "chia_relative_price.csv").write_text(
        "hospital_id,relative_price,tier\nmgh,1.25,high\n", encoding="utf-8"
    )

    # Point config at the temp tree.
    monkeypatch.setattr(config, "PROCEDURE_LIST_CSV", tmp_path / "procedure_list.csv")
    monkeypatch.setattr(config, "HOSPITALS_INPUT_CSV", tmp_path / "hospitals_input.csv")
    monkeypatch.setattr(config, "RAW_DIR", raw)
    monkeypatch.setattr(config, "PFS_RAW", raw / "cms_pfs.csv")
    monkeypatch.setattr(config, "NCCI_RAW", raw / "ncci_ptp.csv")
    monkeypatch.setattr(config, "CHIA_RAW", raw / "chia_relative_price.csv")
    for attr, name in [
        ("PROCEDURES_JSON", "procedures.json"),
        ("HOSPITALS_JSON", "hospitals.json"),
        ("HOSPITAL_BINDINGS_JSON", "hospital_bindings.json"),
        ("PRICES_JSON", "prices.json"),
        ("MEDICARE_JSON", "medicare.json"),
        ("NCCI_PAIRS_JSON", "ncci_pairs.json"),
        ("CHIA_TIERS_JSON", "chia_tiers.json"),
        ("REFERENCE_JSON", "reference.json"),
        ("SKIPPED_LOG", "skipped.log"),
    ]:
        monkeypatch.setattr(config, attr, proc / name)

    rc = main(["all", "--data-source", "TEST", "--data-year", "2025"])
    assert rc == 0

    # Every processed output exists.
    for name in ("procedures.json", "hospitals.json", "prices.json", "medicare.json",
                 "ncci_pairs.json", "chia_tiers.json", "reference.json"):
        assert (proc / name).exists(), f"missing {name}"

    # reference.json combined medicare + gross range for 99213.
    refs = {r["code"]: r for r in jsonio.read_json(proc / "reference.json")}
    assert refs["99213"]["medicare_price"] == 92.47
    assert refs["99213"]["ma_range_low"] == 500.0  # only gross for 99213 is 500
    assert refs["99213"]["code_system"] == "CPT"
