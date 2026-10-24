"""Tests for the report (spec task 7). Covers R1 to R6 and property PE8."""

from __future__ import annotations

import re
from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from evals import config, report
from evals.cache import CachingClient
from evals.corpus import PrivatePathError, build_corpus
from evals.invariants import Violation
from evals.oracle import OracleClient
from evals.report import FAKE_BANNER, cell, pct, render, write_report
from evals.run import TASKS, run_corpus
from evals.score_flags import FLAG_TYPES

BILLS = build_corpus()


def fake_result(transform=None, bills=BILLS):
    return run_corpus(bills, OracleClient(bills, extract_transform=transform), mode="fake")


def cache_only_result():
    cache = CachingClient({t: None for t in TASKS}, {t: "real-model-name" for t in TASKS},
                          config.EVALS_DIR / ".nonexistent-cache-for-test", cache_only=True)
    return run_corpus(BILLS, cache, mode="cache-only")


def table_rows(text: str, heading: str) -> list[str]:
    """The table lines under a '## heading' section."""
    section = text.split(f"## {heading}", 1)[1].split("\n## ", 1)[0]
    return [ln for ln in section.splitlines() if ln.startswith("|")]


def columns(row: str) -> int:
    """Number of cells in a row, ignoring escaped pipes."""
    return len(re.split(r"(?<!\\)\|", row.strip())) - 2


# --- formatting helpers -------------------------------------------------------

@pytest.mark.parametrize("value,expected", [(None, "n/a"), (0.0, "0.0%"), (1.0, "100.0%"),
                                            (0.9567, "95.7%"), (0.95, "95.0%"), (0.5, "50.0%")])
def test_pct(value, expected):
    assert pct(value) == expected


def test_r6_cell_escapes_pipes_and_removes_line_breaks():
    assert cell("a|b") == "a\\|b"
    assert cell("a\nb\r\nc") == "a b c"
    assert cell("  x  ") == "x"
    assert cell(5) == "5" and cell(None) == "None"


@settings(max_examples=200)
@given(st.text(max_size=60))
def test_pe8_a_cell_never_holds_a_raw_pipe_or_line_break(text):
    out = cell(text)
    assert "\n" not in out and "\r" not in out
    assert all(out[i - 1] == "\\" for i, ch in enumerate(out) if ch == "|" and i > 0)
    assert not out.startswith("|")


# --- R1: deterministic -----------------------------------------------------------

def test_r1_same_results_give_identical_text():
    assert render(fake_result()) == render(fake_result())


def test_r1_no_timestamps_or_dates_from_the_clock():
    text = render(fake_result())
    assert not re.search(r"\b20\d\d-\d\d-\d\d[T ]\d\d:\d\d", text)
    assert "generated" not in text.lower()


# --- R2: sections ------------------------------------------------------------------

def test_r2_has_every_section_and_table():
    text = render(fake_result())
    for heading in ("Run", "Extraction accuracy", "Flags (extraction -> /core)", "Explain and letter",
                    "Thresholds (rules of thumb, set in evals/config.py)", "Failures", "Notes"):
        assert f"## {heading}" in text, heading
    ex = table_rows(text, "Extraction accuracy")
    labels = [r.split("|")[1].strip() for r in ex[2:]]
    assert labels[0] == "Overall"
    assert "Layout: plain" in labels and "Layout: messy" in labels
    assert {f"Scenario: {s}" for s in ("clean", "duplicate", "high_price", "injection", "mixed",
                                         "quantity", "unbundling", "unknown_code")} <= set(labels)
    flags = table_rows(text, "Flags (extraction -> /core)")
    assert [r.split("|")[1].strip() for r in flags[2:]] == list(FLAG_TYPES) + ["All types"]


def test_r2_run_table_names_the_models_and_the_cache_numbers():
    r = cache_only_result()
    text = render(r)
    assert "| Extract model | real-model-name |" in text
    assert f"| Bills | {len(BILLS)} |" in text
    assert "| Real model calls | 0 |" in text
    assert f"| Cache-only misses | {r.stats.cache_only_misses} |" in text
    assert "| Call budget | not reached |" in text


def test_r2_the_budget_stop_is_reported(tmp_path):
    oracle = OracleClient(BILLS)
    cache = CachingClient({t: oracle.inner(t) for t in TASKS}, {t: "m" for t in TASKS}, tmp_path / "c", max_calls=2)
    text = render(run_corpus(BILLS, cache, mode="real"))
    assert "| Call budget | reached (some calls were skipped) |" in text


def test_r2_every_failure_row_has_a_bill_id_and_a_layout():
    def damage(bill, lines):
        return [{**lines[0], "billed_amount": lines[0]["billed_amount"] + 5.0}] + lines[1:-1] \
            if bill.scenario == "mixed" else lines

    text = render(fake_result(damage))
    rows = table_rows(text, "Failures")
    assert rows[0] == "| Bill | Layout | Kind | Line |"
    body = rows[2:]
    assert body, "expected failure rows"
    for row in body:
        bill, layout, kind, line = [c.strip() for c in row.strip().strip("|").split("|")]
        assert re.fullmatch(r"[a-z_]+-\d+", bill) and layout in {"plain", "messy"} and kind and line is not None
    kinds = {r.split("|")[3].strip() for r in body}
    assert {"charge", "missing_line"} <= kinds


def test_r2_a_perfect_run_has_no_failures():
    text = render(fake_result())
    assert text.split("## Failures", 1)[1].split("## Notes", 1)[0].strip() == "None."


def test_r2_fallbacks_of_explain_and_letter_are_listed_as_failures():
    text = render(cache_only_result())
    body = table_rows(text, "Failures")
    kinds = {r.split("|")[3].strip() for r in body[2:]}
    assert {"extraction_fallback", "explain_fallback", "letter_fallback", "missing_line", "missed_flag"} <= kinds


def test_r2_failure_rows_are_capped_and_the_rest_are_counted():
    r = fake_result()
    b0 = r.bills[0]
    many = tuple(Violation(b0.bill_id, b0.style, "explain_figure", f"{i}:x") for i in range(250))
    r = replace(r, bills=(replace(b0, violations=many),) + r.bills[1:])
    text = render(r)
    rows = table_rows(text, "Failures")[2:]
    assert len(rows) == report.MAX_FAILURE_ROWS == 200
    assert "... and 50 more." in text


def test_r2_a_run_with_few_failures_shows_them_all_and_no_more_line():
    text = render(cache_only_result())
    rows = table_rows(text, "Failures")[2:]
    assert 0 < len(rows) < report.MAX_FAILURE_ROWS
    assert " more." not in text


# --- R3: thresholds ----------------------------------------------------------------

def test_r3_a_perfect_run_passes_every_threshold():
    text = render(fake_result())
    rows = table_rows(text, "Thresholds (rules of thumb, set in evals/config.py)")[2:]
    assert len(rows) == len(config.THRESHOLDS)
    assert all(r.strip().endswith("| PASS |") for r in rows)
    assert "Summary: 0 of 13 thresholds failed. Hard failure: no." in text


def test_r3_failing_thresholds_say_fail_and_the_hard_one_is_marked():
    text = render(fake_result(lambda b, lines: lines[:1]))
    rows = table_rows(text, "Thresholds (rules of thumb, set in evals/config.py)")[2:]
    assert any("| FAIL |" in r for r in rows)
    assert any(r.startswith("| Invariant violations (hard) |") for r in rows)
    m = re.search(r"Summary: (\d+) of 13 thresholds failed", text)
    assert m and int(m.group(1)) == sum("| FAIL |" in r for r in rows)


def test_r3_rules_and_values_are_printed_in_readable_form():
    text = render(fake_result())
    assert "| Line recall | 100.0% | >= 95.0% | PASS |" in text
    assert "| Hallucinated codes | 0 | == 0 | PASS |" in text
    assert "| Explain fallback rate | 0.0% | <= 25.0% | PASS |" in text


def test_r3_nothing_to_measure_shows_n_a():
    r = fake_result(bills=[b for b in BILLS if b.scenario == "clean"])
    text = render(r)
    assert "| Flag catch rate (each type) | n/a | >= 90.0% | n/a |" in text


def test_r3_a_hard_failure_is_reported_in_the_summary():
    r = fake_result()
    b0 = r.bills[0]
    bad = replace(b0, violations=(Violation(b0.bill_id, b0.style, "explain_banned_word", "1:x"),))
    r = replace(r, bills=(bad,) + r.bills[1:])
    text = render(r)
    assert "Hard failure: YES." in text
    assert f"| {b0.bill_id} | {b0.style} | HARD: explain_banned_word | 1:x |" in text
    assert "| Invariant violations (hard) | 1 | == 0 | FAIL |" in text


def test_a_core_self_check_mismatch_is_a_hard_row():
    r = fake_result()
    b0 = r.bills[0]
    flags = replace(b0.flags, oracle_matches_expected=False)
    r = replace(r, bills=(replace(b0, flags=flags),) + r.bills[1:])
    assert f"| {b0.bill_id} | {b0.style} | HARD: core_self_check |" in render(r)


# --- R4: nothing private ---------------------------------------------------------------

def test_r4_no_key_no_reply_no_bill_text(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-test-key-not-real")
    text = render(fake_result()) + render(cache_only_result())
    assert "fake-test-key-not-real" not in text and "ANTHROPIC" not in text
    for b in BILLS:
        for li in b.truth.line_items:
            for secret in (li.raw_description, li.description):
                if secret and len(secret) > 6:
                    assert secret not in text, secret
        assert b.truth.bill_metadata.hospital_name not in text
    assert '"line_items"' not in text and "paragraph" not in text


# --- R5: fake label ----------------------------------------------------------------------

def test_r5_fake_runs_are_labelled_at_the_top():
    text = render(fake_result())
    lines = text.splitlines()
    assert lines[0] == "# Eval results" and lines[2] == FAKE_BANNER
    assert "FAKE ORACLE - not a model" in text


def test_r5_real_and_cache_only_runs_have_no_fake_label():
    assert "FAKE ORACLE" not in render(cache_only_result())


# --- R6: tables stay tables -------------------------------------------------------------------

def test_r6_pipes_and_line_breaks_in_ids_cannot_break_a_table():
    r = fake_result()
    b0 = r.bills[0]
    nasty = Violation("b|1", "pl\nain", "explain_figure", "x|y\nz")
    r = replace(r, bills=(replace(b0, violations=(nasty,)),) + r.bills[1:])
    text = render(r)
    rows = table_rows(text, "Failures")
    header_cols = columns(rows[0])
    assert header_cols == 4
    assert all(columns(row) == header_cols for row in rows)
    assert "b\\|1" in text and "x\\|y z" in text


def test_every_table_row_has_as_many_cells_as_its_header():
    text = render(fake_result())
    for heading in ("Run", "Extraction accuracy", "Flags (extraction -> /core)", "Explain and letter",
                    "Thresholds (rules of thumb, set in evals/config.py)"):
        rows = table_rows(text, heading)
        assert all(columns(r) == columns(rows[0]) for r in rows), heading


# --- write_report ------------------------------------------------------------------------------

def test_write_report_writes_the_rendered_text_and_makes_the_folder(tmp_path):
    r = fake_result()
    target = write_report(r, tmp_path / "new" / "folder" / "eval-results.md")
    assert target.read_text(encoding="utf-8") == render(r)
    assert sorted(p.name for p in tmp_path.rglob("*") if p.is_file()) == ["eval-results.md"]


def test_write_report_refuses_private_paths():
    with pytest.raises(PrivatePathError):
        write_report(fake_result(), config.PRIVATE_DIR / "eval-results.md")
    assert not (config.PRIVATE_DIR / "eval-results.md").exists()


def test_write_report_overwrites_an_old_report(tmp_path):
    path = tmp_path / "r.md"
    path.write_text("old")
    write_report(fake_result(), path)
    assert path.read_text().startswith("# Eval results")
