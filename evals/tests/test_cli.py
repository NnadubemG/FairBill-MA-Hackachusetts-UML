"""Tests for the command line (spec task 8). Covers K1 to K5, K7 and privacy PR1.

The real model is never used. Where a "real" run is needed, a stub builder hands back the
oracle as the model client.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys

import pytest

from synthetic import SCENARIOS, STYLES

from evals import __main__ as cli
from evals import config, run as run_module
from evals.corpus import build_corpus
from evals.invariants import Violation
from evals.oracle import OracleClient

BILLS = build_corpus()
EXPECTED_BILLS = len(SCENARIOS) * len(STYLES)   # computed from /synthetic, never hard-coded
FAKE_KEY = "fake-test-key-not-real"
MODEL_VARS = (config.ENV_EXTRACT_MODEL, config.ENV_EXPLAIN_MODEL, config.ENV_LETTER_MODEL)


def clear_env(monkeypatch):
    for name in (config.ENV_API_KEY, *MODEL_VARS):
        monkeypatch.delenv(name, raising=False)


def set_models(monkeypatch):
    monkeypatch.setenv(config.ENV_EXTRACT_MODEL, "m-extract")
    monkeypatch.setenv(config.ENV_EXPLAIN_MODEL, "m-explain")
    monkeypatch.setenv(config.ENV_LETTER_MODEL, "m-letter")


def run_cli(argv, **kwargs):
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(argv, out=out, err=err, **kwargs)
    return code, out.getvalue(), err.getvalue()


def oracle_builder(oracle=None):
    """A stand-in for make_client: returns the oracle as the model for the asked task."""
    oracle = oracle or OracleClient(BILLS)
    asked: list[str] = []

    def build(model_env_var: str):
        asked.append(model_env_var)
        task = {v: k for k, v in cli._MODEL_ENV.items()}[model_env_var]
        return oracle.inner(task)

    build.asked = asked  # type: ignore[attr-defined]
    return build


def paths(tmp_path):
    return ["--out", str(tmp_path / "r.md"), "--cache-dir", str(tmp_path / "cache")]


# --- K1: fake mode ----------------------------------------------------------------

def test_k1_fake_run_works_offline_and_scores_the_oracle_perfectly(tmp_path, monkeypatch):
    clear_env(monkeypatch)
    code, out, err = run_cli(["--fake", *paths(tmp_path)])
    assert code == config.EXIT_OK and err == ""
    report = (tmp_path / "r.md").read_text()
    assert "FAKE ORACLE - not a model" in report
    assert "| Line recall | 100.0% | >= 95.0% | PASS |" in report
    assert "Thresholds failed: 0 of 13" in out and f"Running {EXPECTED_BILLS} bills in fake mode." in out
    assert f"[1/{EXPECTED_BILLS}] " in out and f"[{EXPECTED_BILLS}/{EXPECTED_BILLS}] " in out
    assert "FAKE ORACLE run" in out
    assert not (tmp_path / "cache").exists()                 # the oracle needs no cache


def test_k1_progress_lines_name_bills_only(tmp_path, monkeypatch):
    clear_env(monkeypatch)
    _, out, _ = run_cli(["--fake", *paths(tmp_path)])
    progress = [ln for ln in out.splitlines() if ln.startswith("[")]
    assert len(progress) == EXPECTED_BILLS
    assert all(ln.endswith(": done") for ln in progress)
    for b in BILLS:
        for li in b.truth.line_items:
            assert (li.raw_description or "NOT-PRESENT") not in out


def test_k1_python_dash_m_evals_runs_as_a_program(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-m", "evals", "--fake", "--scenarios", "clean", "--styles", "plain",
         *paths(tmp_path)],
        cwd=config.REPO_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "r.md").exists() and "Traceback" not in proc.stderr


def test_default_report_paths_a_fake_run_never_uses_the_real_name():
    assert cli.default_out("fake") != cli.default_out("real")
    assert cli.default_out("real") == config.DEFAULT_REPORT_PATH
    assert cli.default_out("cache-only") == config.DEFAULT_REPORT_PATH
    assert config.EVALS_DIR in cli.default_out("fake").parents


# --- corpus options ------------------------------------------------------------------

def test_scenarios_seeds_and_styles_choose_the_bills(tmp_path, monkeypatch):
    clear_env(monkeypatch)
    code, out, _ = run_cli(["--fake", "--scenarios", "clean,mixed", "--seeds", "1,2", "--styles", "plain",
                            *paths(tmp_path)])
    assert code == 0 and "Running 4 bills" in out
    assert "[4/4] mixed-2/plain: done" in out


@pytest.mark.parametrize(
    "argv,words",
    [
        (["--fake", "--scenarios", "nope"], ("unknown scenario", "nope")),
        (["--fake", "--styles", "fancy"], ("unknown style", "fancy")),
        (["--fake", "--seeds", "a"], ("--seeds", "whole numbers")),
        (["--fake", "--seeds", "1.5"], ("--seeds", "whole numbers")),
        (["--fake", "--max-calls", "-1"], ("--max-calls",)),
        (["--fake", "--cache-only"], ("--fake", "--cache-only")),
    ],
)
def test_bad_options_give_a_clear_error_and_exit_2(argv, words, tmp_path, monkeypatch):
    clear_env(monkeypatch)
    code, out, err = run_cli([*argv, *paths(tmp_path)])
    assert code == config.EXIT_USAGE and "Traceback" not in err
    for w in words:
        assert w in err
    assert "Running" not in out and not (tmp_path / "r.md").exists()


def test_a_non_number_for_max_calls_exits_2_with_a_usage_message(tmp_path, monkeypatch, capsys):
    clear_env(monkeypatch)
    code, _, _ = run_cli(["--fake", "--max-calls", "many", *paths(tmp_path)])
    assert code == config.EXIT_USAGE
    assert "usage" in capsys.readouterr().err.lower()


# --- K2: setup problems ----------------------------------------------------------------

def test_k2_real_run_without_the_key_exits_2_naming_it(tmp_path, monkeypatch):
    clear_env(monkeypatch)
    set_models(monkeypatch)
    build = oracle_builder()
    code, out, err = run_cli(paths(tmp_path), build_client=build)
    assert code == config.EXIT_USAGE
    assert config.ENV_API_KEY in err and "Traceback" not in err
    assert build.asked == [] and not (tmp_path / "r.md").exists()
    assert "Running" not in out


def test_k2_real_run_without_model_names_lists_every_missing_variable(tmp_path, monkeypatch):
    clear_env(monkeypatch)
    monkeypatch.setenv(config.ENV_API_KEY, FAKE_KEY)
    monkeypatch.setenv(config.ENV_EXTRACT_MODEL, "m-extract")
    code, _, err = run_cli(paths(tmp_path), build_client=oracle_builder())
    assert code == config.EXIT_USAGE
    assert config.ENV_EXPLAIN_MODEL in err and config.ENV_LETTER_MODEL in err
    assert config.ENV_EXTRACT_MODEL not in err and FAKE_KEY not in err


def test_k2_a_client_that_cannot_start_gives_a_short_message(tmp_path, monkeypatch):
    clear_env(monkeypatch)
    set_models(monkeypatch)
    monkeypatch.setenv(config.ENV_API_KEY, FAKE_KEY)

    def broken(model_env_var):
        raise ImportError(f"secret detail {FAKE_KEY}")

    code, _, err = run_cli(paths(tmp_path), build_client=broken)
    assert code == config.EXIT_USAGE and "ImportError" in err
    assert "secret detail" not in err and FAKE_KEY not in err and "Traceback" not in err


# --- K3: cache-only ----------------------------------------------------------------------

def test_k3_cache_only_with_an_empty_cache_never_calls_the_model_and_still_writes_a_report(tmp_path, monkeypatch):
    clear_env(monkeypatch)
    set_models(monkeypatch)                                  # names yes, key no
    def must_not_be_called(model_env_var):
        raise AssertionError("the model client must not be built in cache-only mode")

    code, out, err = run_cli(["--cache-only", *paths(tmp_path)], build_client=must_not_be_called)
    assert code == config.EXIT_OK and err == ""
    report = (tmp_path / "r.md").read_text()
    assert "| Mode | cache-only |" in report and "| Real model calls | 0 |" in report
    assert "| Extract model | m-extract |" in report
    assert "extraction_fallback" in report
    assert "0 real calls" in out


def test_k3_cache_only_still_needs_the_model_names(tmp_path, monkeypatch):
    clear_env(monkeypatch)
    code, _, err = run_cli(["--cache-only", *paths(tmp_path)])
    assert code == config.EXIT_USAGE and config.ENV_EXTRACT_MODEL in err
    assert config.ENV_API_KEY not in err


def test_k3_strict_makes_a_failing_cache_only_run_exit_1(tmp_path, monkeypatch):
    clear_env(monkeypatch)
    set_models(monkeypatch)
    assert run_cli(["--cache-only", "--strict", *paths(tmp_path)])[0] == config.EXIT_FAILED
    assert run_cli(["--cache-only", *paths(tmp_path)])[0] == config.EXIT_OK


def test_k3_a_real_run_then_a_cache_only_replay_gives_the_same_report(tmp_path, monkeypatch):
    clear_env(monkeypatch)
    set_models(monkeypatch)
    monkeypatch.setenv(config.ENV_API_KEY, FAKE_KEY)
    first = ["--out", str(tmp_path / "first.md"), "--cache-dir", str(tmp_path / "cache")]
    second = ["--cache-only", "--out", str(tmp_path / "second.md"), "--cache-dir", str(tmp_path / "cache")]
    assert run_cli(first, build_client=oracle_builder())[0] == 0
    code, out, _ = run_cli(second)
    assert code == 0 and "0 real calls" in out
    a = (tmp_path / "first.md").read_text()
    b = (tmp_path / "second.md").read_text()
    section = lambda t: t.split("## Extraction accuracy", 1)[1]            # noqa: E731
    assert section(a) == section(b)                                         # same numbers, from disk


# --- K4: /private ---------------------------------------------------------------------------

@pytest.mark.parametrize("flag", ["--out", "--cache-dir"])
def test_k4_private_paths_are_refused(flag, tmp_path, monkeypatch):
    clear_env(monkeypatch)
    base = {"--out": str(tmp_path / "r.md"), "--cache-dir": str(tmp_path / "c")}
    base[flag] = str(config.PRIVATE_DIR / "x")
    argv = ["--fake"] + [a for k, v in base.items() for a in (k, v)]
    code, out, err = run_cli(argv)
    assert code == config.EXIT_USAGE and "private" in err.lower()
    assert "Running" not in out and not (config.PRIVATE_DIR / "x").exists()


def test_k4_private_path_with_dot_dot_is_refused(tmp_path, monkeypatch):
    clear_env(monkeypatch)
    sneaky = str(config.EVALS_DIR / ".." / "private" / "r.md")
    code, _, err = run_cli(["--fake", "--out", sneaky, "--cache-dir", str(tmp_path / "c")])
    assert code == config.EXIT_USAGE and "private" in err.lower()


# --- K5: the call budget ---------------------------------------------------------------------

def test_k5_max_calls_reaches_the_cache(tmp_path, monkeypatch):
    clear_env(monkeypatch)
    set_models(monkeypatch)
    monkeypatch.setenv(config.ENV_API_KEY, FAKE_KEY)
    code, out, _ = run_cli(["--max-calls", "3", *paths(tmp_path)], build_client=oracle_builder())
    assert code == config.EXIT_OK
    assert "3 real calls (call budget reached)" in out
    report = (tmp_path / "r.md").read_text()
    assert "| Call budget | reached (some calls were skipped) |" in report
    assert "| Real model calls | 3 |" in report


def test_k5_the_default_budget_covers_a_full_run(tmp_path, monkeypatch):
    clear_env(monkeypatch)
    set_models(monkeypatch)
    monkeypatch.setenv(config.ENV_API_KEY, FAKE_KEY)
    build = oracle_builder()
    code, out, _ = run_cli(paths(tmp_path), build_client=build)
    assert code == config.EXIT_OK and "budget reached" not in out
    assert sorted(build.asked) == sorted(cli._MODEL_ENV.values())            # one client per task
    flagged = sum(1 for b in BILLS if b.truth.expected_flags)
    expected_calls = len(BILLS) + 2 * flagged
    assert f"{expected_calls} real calls" in out and expected_calls <= config.DEFAULT_MAX_CALLS
    assert "| Extract model | m-extract |" in (tmp_path / "r.md").read_text()


# --- exit codes: hard failures and --strict -----------------------------------------------------

def test_a_hard_failure_exits_1_even_without_strict(tmp_path, monkeypatch):
    clear_env(monkeypatch)
    monkeypatch.setattr(run_module, "check_explanations",
                        lambda bill_id, style, flags: [Violation(bill_id, style, "explain_banned_word", "1:x")])
    code, _, err = run_cli(["--fake", *paths(tmp_path)])
    assert code == config.EXIT_FAILED and "HARD FAILURE" in err
    assert "HARD: explain_banned_word" in (tmp_path / "r.md").read_text()


def test_strict_exit_code_follows_the_thresholds(tmp_path, monkeypatch):
    clear_env(monkeypatch)
    set_models(monkeypatch)
    monkeypatch.setenv(config.ENV_API_KEY, FAKE_KEY)
    heavy = OracleClient(BILLS, extract_transform=lambda b, lines: lines[:1])
    args = paths(tmp_path)
    assert run_cli(args, build_client=oracle_builder(heavy))[0] == config.EXIT_OK
    assert run_cli(["--strict", *args], build_client=oracle_builder(heavy))[0] == config.EXIT_FAILED
    assert run_cli(["--strict", "--fake", *args])[0] == config.EXIT_OK


def test_the_report_cannot_be_written_into_a_file_path(tmp_path, monkeypatch):
    clear_env(monkeypatch)
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file")
    code, _, err = run_cli(["--fake", "--out", str(blocker / "r.md"), "--cache-dir", str(tmp_path / "c")])
    assert code == config.EXIT_USAGE and "could not write the report" in err and "Traceback" not in err


# --- K7: what gets written --------------------------------------------------------------------------

def test_k7_a_real_run_writes_only_the_report_and_the_cache(tmp_path, monkeypatch):
    clear_env(monkeypatch)
    set_models(monkeypatch)
    monkeypatch.setenv(config.ENV_API_KEY, FAKE_KEY)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    out_dir = tmp_path / "out"
    code, _, _ = run_cli(["--out", str(out_dir / "r.md"), "--cache-dir", str(out_dir / "cache")],
                         build_client=oracle_builder())
    assert code == 0
    assert list(work.iterdir()) == []                                        # nothing in the working folder
    assert sorted(p.name for p in out_dir.iterdir()) == ["cache", "r.md"]
    assert (out_dir / "cache" / ".gitignore").read_text() == "*\n"
    for entry in (out_dir / "cache").glob("*.json"):
        assert set(json.loads(entry.read_text())) == {"task", "model", "file_sha256", "reply"}


# --- PR1: privacy -----------------------------------------------------------------------------------------

def test_pr1_the_key_and_bill_text_never_reach_the_output_report_or_cache(tmp_path, monkeypatch):
    clear_env(monkeypatch)
    set_models(monkeypatch)
    monkeypatch.setenv(config.ENV_API_KEY, FAKE_KEY)
    code, out, err = run_cli(paths(tmp_path), build_client=oracle_builder())
    assert code == 0
    report = (tmp_path / "r.md").read_text()
    files = [p.read_text() for p in (tmp_path / "cache").iterdir() if p.is_file()]
    for text in (out, err, report, *files):
        assert FAKE_KEY not in text
    # The startup check shows only the length and the last 4 characters.
    assert f"length {len(FAKE_KEY)}, ends with ...{FAKE_KEY[-4:]}" in out
    for text in (out, err, report):
        for b in BILLS:
            assert b.truth.bill_metadata.hospital_name not in text
            for li in b.truth.line_items:
                assert (li.raw_description or "NOT-PRESENT") not in text
