import subprocess
import sys
from pathlib import Path

import pytest

from synthetic import SCENARIOS
from synthetic.__main__ import SAMPLE_SPECS, SAMPLES_DIR, main

ROOT = Path(__file__).resolve().parents[2]


def names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def test_cli_writes_exactly_three_files(tmp_path):  # TS-C1
    out = tmp_path / "out"
    assert main(["--seed", "7", "--scenario", "mixed", "--style", "messy", "--out", str(out)]) == 0
    assert names(out) == ["bill-mixed-7.json", "bill-mixed-7.pdf", "bill-mixed-7.txt"]
    assert names(tmp_path) == ["out"]  # nothing written next to it


def test_cli_creates_nested_output_folders(tmp_path):
    out = tmp_path / "a" / "b"
    assert main(["--scenario", "clean", "--out", str(out)]) == 0
    assert (out / "bill-clean-1.json").exists()


def test_cli_rejects_an_output_path_that_is_a_file(tmp_path, capsys):  # TS-C3
    target = tmp_path / "file.txt"
    target.write_text("keep me")
    assert main(["--scenario", "clean", "--out", str(target)]) == 2
    assert target.read_text() == "keep me"
    assert names(tmp_path) == ["file.txt"]
    assert "not a folder" in capsys.readouterr().err


def test_cli_requires_out_unless_samples(capsys):
    assert main(["--scenario", "clean"]) == 2
    assert "--out" in capsys.readouterr().err


def test_cli_rejects_unknown_scenario_and_style(tmp_path):
    with pytest.raises(SystemExit) as bad_scenario:
        main(["--scenario", "nope", "--out", str(tmp_path)])
    with pytest.raises(SystemExit) as bad_style:
        main(["--style", "fancy", "--out", str(tmp_path)])
    assert bad_scenario.value.code == 2 and bad_style.value.code == 2
    assert names(tmp_path) == []


def test_committed_samples_are_current(tmp_path):  # TS-C2
    assert main(["--samples", "--out", str(tmp_path)]) == 0
    assert SAMPLES_DIR.is_dir(), "run: python -m synthetic --samples"
    assert names(SAMPLES_DIR) == names(tmp_path)  # no missing or stale files
    for fresh in tmp_path.iterdir():
        assert (SAMPLES_DIR / fresh.name).read_bytes() == fresh.read_bytes(), (
            f"{fresh.name} is out of date: run python -m synthetic --samples"
        )


def test_there_is_a_sample_for_every_scenario():
    assert {scenario for scenario, _, _ in SAMPLE_SPECS} == set(SCENARIOS)
    assert len(names(SAMPLES_DIR)) == 3 * len(SCENARIOS)


def test_module_entry_point_runs(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "synthetic", "--scenario", "duplicate", "--out", str(tmp_path)],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert names(tmp_path) == ["bill-duplicate-1.json", "bill-duplicate-1.pdf", "bill-duplicate-1.txt"]
