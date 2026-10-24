"""Tests for the runner (spec task 6). Covers X1, X2, X4, X5 and K6 (noisy oracle end to end).

Everything runs offline: the oracle is the model, with or without the disk cache around it.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from evals import config, run as run_module
from evals.cache import CachingClient
from evals.corpus import build_corpus
from evals.oracle import OracleClient
from evals.run import (
    TASKS,
    any_threshold_failed,
    evaluate_thresholds,
    has_hard_failure,
    run_bill,
    run_corpus,
)

BILLS = build_corpus()


def fake_run(bills=BILLS, oracle=None, progress=None):
    oracle = oracle or OracleClient(bills)
    return run_corpus(bills, oracle, mode="fake", progress=progress)


# --- X1: everything works ---------------------------------------------------

def test_x1_oracle_run_is_perfect_everywhere():
    r = fake_run()
    assert r.mode == "fake" and r.models == {t: config.FAKE_MODEL_LABEL for t in TASKS}
    assert len(r.bills) == 16
    e, f = r.extraction, r.flags
    assert (e.line_recall, e.line_precision, e.code_exact, e.charge_exact) == (1.0, 1.0, 1.0, 1.0)
    assert e.units_exact == 1.0 and e.date_exact == 1.0 and e.hallucinated_codes == 0
    assert e.injection_extra_lines == 0 and e.fallback_bills == 0 and e.bills == 16
    assert f.overall_catch_rate == 1.0 and f.min_catch_rate == 1.0 and f.total_false_positives == 0
    assert f.fp_rate_clean == 0.0 and f.core_self_check_mismatches == 0 and f.core_errors == 0
    assert r.explain_total > 0 and r.explain_fallback_rate == 0.0
    assert r.letters > 0 and r.letter_fallback_rate == 0.0
    assert r.violations == ()
    assert not has_hard_failure(r) and not any_threshold_failed(r)
    assert all(t.passed is True for t in evaluate_thresholds(r))


def test_x1_the_run_is_deterministic():
    assert fake_run() == fake_run()


def test_every_bill_has_every_stage_result():
    for b in fake_run().bills:
        assert b.extraction is not None and b.flags is not None
        assert b.key == f"{b.bill_id}/{b.style}"


# --- X2 / X4: letters --------------------------------------------------------

def test_x2_x4_a_letter_is_made_only_for_bills_that_have_flags():
    r = fake_run()
    by_scenario = {}
    for b in r.bills:
        by_scenario.setdefault(b.scenario, set()).add((b.explain_flags > 0, b.letter_ran))
    assert by_scenario["clean"] == {(False, False)}
    assert by_scenario["injection"] == {(False, False)}
    assert by_scenario["mixed"] == {(True, True)}
    assert r.letters == sum(1 for b in r.bills if b.explain_flags > 0)
    assert all(not b.letter_fallback for b in r.bills if b.letter_ran)


# --- X5: the model fails ----------------------------------------------------

def test_x5_when_every_call_misses_the_cache_everything_falls_back_and_nothing_crashes(tmp_path):
    cache = CachingClient({t: None for t in TASKS}, {t: "m" for t in TASKS}, tmp_path / "c", cache_only=True)
    r = run_corpus(BILLS, cache, mode="cache-only")
    assert r.extraction.fallback_bills == 16 and r.extraction.line_recall == 0.0
    assert r.explain_fallback_rate == 1.0 and r.letter_fallback_rate == 1.0
    assert r.violations == ()                               # fallbacks are still safe
    assert r.stats.real_calls == 0 and r.stats.cache_only_misses > 0 and r.stats.hits == 0
    assert any_threshold_failed(r) and not has_hard_failure(r)
    assert r.flags.total_caught == 0 and r.flags.total_planted > 0
    assert r.flags.fp_rate_clean == 0.0                     # no lines, so no false positives


def test_the_call_budget_stops_real_calls_and_the_run_still_finishes(tmp_path):
    oracle = OracleClient(BILLS)
    cache = CachingClient({t: oracle.inner(t) for t in TASKS}, {t: "fake" for t in TASKS},
                          tmp_path / "c", max_calls=5)
    r = run_corpus(BILLS, cache, mode="real")
    assert r.stats.budget_hit and r.stats.real_calls == 5
    assert len(r.bills) == 16 and r.violations == ()
    assert 0 < r.extraction.line_recall < 1.0               # 5 bills were read, the rest fell back


# --- the cached path: run once, replay from disk -------------------------------

def test_a_second_run_is_answered_from_the_cache_and_gives_the_same_results(tmp_path):
    oracle = OracleClient(BILLS)
    first_cache = CachingClient({t: oracle.inner(t) for t in TASKS}, {t: "fake" for t in TASKS}, tmp_path / "c")
    first = run_corpus(BILLS, first_cache, mode="real")
    assert first.stats.hits == 0 and first.stats.misses == first.stats.real_calls > 16
    assert first.extraction.line_recall == 1.0

    replay_cache = CachingClient({t: None for t in TASKS}, {t: "fake" for t in TASKS}, tmp_path / "c", cache_only=True)
    second = run_corpus(BILLS, replay_cache, mode="cache-only")
    assert second.stats.real_calls == 0 and second.stats.misses == 0
    assert second.stats.hits == first.stats.misses
    assert second.metric_values() == first.metric_values()
    assert [b.extraction.counts for b in second.bills] == [b.extraction.counts for b in first.bills]


def test_a_different_model_name_does_not_reuse_the_cache(tmp_path):
    oracle = OracleClient(BILLS[:2])
    inners = {t: oracle.inner(t) for t in TASKS}
    run_corpus(BILLS[:2], CachingClient(inners, {t: "model-a" for t in TASKS}, tmp_path / "c"), mode="real")
    other = CachingClient(inners, {t: "model-b" for t in TASKS}, tmp_path / "c")
    r = run_corpus(BILLS[:2], other, mode="real")
    assert r.stats.hits == 0 and r.stats.real_calls > 0


# --- K6: a noisy oracle end to end ---------------------------------------------

def test_k6_a_noisy_extraction_lowers_the_scores_and_names_the_bad_bills():
    def damage(bill, lines):
        if bill.scenario != "mixed":
            return lines
        lines = [dict(x) for x in lines]
        lines[0]["billed_amount"] = lines[0]["billed_amount"] + 1.0     # wrong charge
        lines[-1]["code"] = "99999"                                     # a changed code
        return lines[:-1] + [dict(lines[-1]), {**lines[-1], "id": "extra-1", "code": None,
                                                 "billed_amount": 1.0, "quantity": None}]

    r = fake_run(oracle=OracleClient(BILLS, extract_transform=damage))
    # One wrong field still matches (so recall stays 1.0); it lowers that field's rate. The
    # extra line lowers precision.
    assert r.extraction.line_recall == 1.0 and r.extraction.line_precision < 1.0
    assert r.extraction.charge_exact < 1.0 and r.extraction.code_exact < 1.0
    bad = {b.key for b in r.bills if b.extraction.failures}
    assert bad == {b.key for b in r.bills if b.scenario == "mixed"}
    perfect = [b for b in r.bills if b.scenario != "mixed"]
    assert all(b.extraction.counts.line_recall == 1.0 for b in perfect)
    kinds = {f.kind for b in r.bills for f in (b.extraction.failures if b.extraction else ())}
    assert {"charge", "extra_line"} <= kinds
    mixed = [b for b in r.bills if b.scenario == "mixed"]
    assert all(b.flags.counts.total_caught < b.flags.counts.total_planted or b.flags.counts.total_false_positives
               for b in mixed)


def test_k6_light_noise_stays_inside_the_thresholds_and_heavy_noise_does_not():
    # Two wrong lines out of ~100 is 98%: still inside the rules of thumb.
    light = fake_run(oracle=OracleClient(BILLS, extract_transform=lambda b, lines: (
        [{**lines[0], "billed_amount": lines[0]["billed_amount"] + 1.0}] + lines[1:]
        if b.key == "mixed-1/plain" else lines)))
    assert light.extraction.charge_exact < 1.0 and not any_threshold_failed(light)

    # Keeping only the first line of every bill is far outside them.
    heavy = fake_run(oracle=OracleClient(BILLS, extract_transform=lambda b, lines: lines[:1]))
    assert heavy.extraction.line_recall < 0.5
    failed = {t.threshold.metric for t in evaluate_thresholds(heavy) if t.passed is False}
    assert {"line_recall", "flag_catch_rate"} <= failed
    assert any_threshold_failed(heavy) and not has_hard_failure(heavy)


def test_k6_a_dropped_duplicate_copy_is_a_missed_duplicate_flag():
    def drop_a_copy(bill, lines):
        if bill.scenario != "duplicate":
            return lines
        dup_ids = sorted({e.line_item_id for e in bill.truth.expected_flags if e.flag_type == "duplicate_line_item"})
        return [x for x in lines if x["id"] != dup_ids[0]]

    r = fake_run(oracle=OracleClient(BILLS, extract_transform=drop_a_copy))
    for b in r.bills:
        if b.scenario == "duplicate":
            assert b.flags.counts.planted == {"duplicate_line_item": 2}
            assert b.flags.counts.total_caught == 0          # both copies lose the flag
        else:
            assert b.flags.counts.total_caught == b.flags.counts.total_planted
    assert r.flags.catch_rate("duplicate_line_item") == 0.5   # 4 of 8: the mixed bills keep theirs
    assert r.flags.min_catch_rate == 0.5


# --- crashes become hard failures, not exceptions --------------------------------

class _Exploding:
    stats = run_module.CacheStats()

    def scoped(self, task, file_sha256):
        raise RuntimeError("factory broke")

    def model_for(self, task):
        return "x"


def test_a_crash_in_a_stage_is_a_hard_failure_and_the_run_continues():
    r = run_corpus(BILLS[:3], _Exploding(), mode="real")
    assert len(r.bills) == 3
    stages = {v.ref for v in r.violations if v.kind == "stage_error"}
    assert "extract" in stages
    assert has_hard_failure(r)


def test_a_violation_makes_the_hard_threshold_fail(monkeypatch):
    from evals.invariants import Violation

    monkeypatch.setattr(run_module, "check_explanations",
                        lambda bill_id, style, flags: [Violation(bill_id, style, "explain_banned_word", "1:x")])
    r = fake_run()
    assert len(r.violations) > 0 and r.metric_values()["invariant_violations"] == len(r.violations)
    hard = [t for t in evaluate_thresholds(r) if t.threshold.hard]
    assert hard and all(t.passed is False for t in hard)
    assert has_hard_failure(r)


# --- grouping and totals -----------------------------------------------------------

def test_extraction_by_layout_and_scenario_adds_up_to_the_total():
    r = fake_run()
    from evals.score_extract import total

    for attr in ("style", "scenario"):
        groups = r.extraction_by(attr)
        assert list(groups) == sorted(groups)
        assert total(groups.values()) == r.extraction
    assert set(r.extraction_by("style")) == {"plain", "messy"}


def test_metric_values_cover_every_threshold():
    r = fake_run()
    assert set(r.metric_values()) == {t.metric for t in config.THRESHOLDS}


def test_thresholds_with_nothing_to_measure_are_n_a_not_failures():
    r = fake_run([b for b in BILLS if b.scenario == "clean"])
    by_metric = {t.threshold.metric: t for t in evaluate_thresholds(r)}
    assert by_metric["flag_catch_rate"].passed is None and by_metric["flag_catch_rate"].value is None
    assert by_metric["explain_fallback_rate"].passed is None
    assert by_metric["letter_fallback_rate"].passed is None
    assert not any_threshold_failed(r)


# --- progress and privacy ---------------------------------------------------------------

def test_progress_lines_name_bills_and_counts_only():
    lines: list[str] = []
    fake_run(BILLS[:3], progress=lines.append)
    assert lines == [f"[{i}/3] {b.key}: done" for i, b in enumerate(BILLS[:3], start=1)]


def test_run_bill_never_raises_for_any_single_bill():
    for b in BILLS:
        assert run_bill(b, OracleClient(BILLS)).violations == ()


def test_the_result_holds_no_bill_text():
    r = fake_run(BILLS[:4])
    text = repr(r)
    for b in BILLS[:4]:
        for li in b.truth.line_items:
            assert (li.raw_description or "NOT-PRESENT") not in text
    assert all(not b.extraction.alignment.pairs for b in r.bills)     # the matching is not kept
    assert replace(r.stats).hits == r.stats.hits
