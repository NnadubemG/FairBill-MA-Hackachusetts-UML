"""Tests for flag scoring (spec task 4). Covers F1 to F7 and property PE5 (flag part)."""

from __future__ import annotations

from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from contracts.types import ExpectedFlag
from synthetic import SCENARIOS, STYLES

from evals import score_flags as sf
from evals.align import match
from evals.corpus import Bill, build_corpus
from evals.score_extract import score_bill

from .factories import line, renamed, result

BILLS = {b.key: b for b in build_corpus()}


def bill(scenario: str, style: str = "plain") -> Bill:
    return BILLS[f"{scenario}-1/{style}"]


def run(b: Bill, extracted):
    """Match the extracted lines and score the flags."""
    alignment = match(b.truth.line_items, extracted)
    return sf.score_flags(b, alignment, extracted)


def perfect(b: Bill):
    return renamed(list(b.truth.line_items))


# --- F1: the oracle run (the /core self-check) ------------------------------

@pytest.mark.parametrize("key", sorted(BILLS))
def test_f1_core_on_truth_lines_equals_expected_flags(key):
    b = BILLS[key]
    got = {(f.line_item_id, f.flag_type) for f in sf.run_core(b.truth.line_items, b.truth)}
    assert got == {(e.line_item_id, e.flag_type) for e in b.truth.expected_flags}
    assert run(b, perfect(b)).oracle_matches_expected


@pytest.mark.parametrize("key", sorted(BILLS))
def test_perfect_extraction_catches_every_planted_flag_with_no_false_positive(key):
    b = BILLS[key]
    s = run(b, perfect(b))
    assert s.counts.total_caught == s.counts.total_planted == len(b.truth.expected_flags)
    assert s.counts.total_false_positives == 0 and s.missed == () and s.false_positive_pairs == ()
    assert s.counts.core_self_check_mismatches == 0 and s.counts.core_errors == 0


def test_every_flag_type_is_planted_somewhere_in_the_default_corpus():
    total = sf.total(run(b, perfect(b)).counts for b in BILLS.values())
    assert set(sf.FLAG_TYPES) <= set(total.planted)
    assert total.overall_catch_rate == 1.0 and total.min_catch_rate == 1.0


# --- F2: dropping a duplicate copy ------------------------------------------

def test_f2_a_dropped_duplicate_copy_loses_the_duplicate_flags():
    b = bill("duplicate")
    dup_ids = sorted({e.line_item_id for e in b.truth.expected_flags if e.flag_type == "duplicate_line_item"})
    assert len(dup_ids) == 2
    extracted = [li for li in b.truth.line_items if li.id != dup_ids[0]]
    s = run(b, renamed(extracted))
    assert s.counts.caught.get("duplicate_line_item", 0) == 0
    assert s.counts.planted["duplicate_line_item"] == 2
    assert s.counts.catch_rate("duplicate_line_item") == 0.0
    assert set(s.missed) == {(i, "duplicate_line_item") for i in dup_ids}


# --- F3 / F7: false positives ------------------------------------------------

def test_f3_an_extra_extracted_line_that_gets_flagged_is_a_false_positive():
    b = bill("clean")
    extra = line("extra-1", "Q9999", 77.0, 1, None)                # a code with no reference price
    s = run(b, perfect(b) + [extra])
    assert (None, "no_reference_found") in s.false_positive_pairs
    assert s.counts.total_false_positives >= 1
    assert s.counts.clean_bills_with_fp == 1 and s.counts.fp_rate_clean == 1.0


def test_f7_a_flag_on_an_unmatched_line_has_no_truth_id():
    b = bill("clean")
    s = run(b, perfect(b) + [line("extra-1", "Q9999", 77.0)])
    assert all(p[0] is None for p in s.false_positive_pairs)


def test_a_wrong_flag_type_on_a_matched_line_is_a_false_positive_with_its_truth_id():
    b = bill("clean")
    li = b.truth.line_items[0]
    extracted = perfect(b)
    extracted[0] = replace(extracted[0], billed_amount=li.billed_amount * 20)   # now far above the range
    s = run(b, extracted)
    assert s.false_positive_pairs and all(p[0] == li.id for p in s.false_positive_pairs)
    assert s.counts.clean_bills_with_fp == 1


# --- F4: clean bill --------------------------------------------------------

def test_f4_clean_bill_perfect_extraction_has_no_flags():
    b = bill("clean")
    s = run(b, perfect(b))
    assert s.counts.total_false_positives == 0 and s.counts.total_planted == 0
    assert (s.counts.clean_bills, s.counts.fp_rate_clean) == (1, 0.0)
    assert (s.counts.no_issue_bills, s.counts.fp_rate_no_issue) == (1, 0.0)


def test_injection_is_a_no_issue_bill_but_not_a_clean_bill():
    b = bill("injection")
    s = run(b, perfect(b))
    assert (s.counts.clean_bills, s.counts.no_issue_bills) == (0, 1)
    assert s.counts.fp_rate_clean is None and s.counts.fp_rate_no_issue == 0.0


def test_a_bill_with_planted_flags_is_not_a_no_issue_bill():
    s = run(bill("mixed"), perfect(bill("mixed")))
    assert s.counts.no_issue_bills == 0 and s.counts.fp_rate_no_issue is None


# --- F5: ids differ -------------------------------------------------------

def test_f5_flags_map_back_through_the_matching_when_ids_differ():
    b = bill("mixed")
    extracted = renamed(list(b.truth.line_items), prefix="model-")
    assert not {li.id for li in extracted} & {li.id for li in b.truth.line_items}
    s = run(b, extracted)
    assert s.counts.total_caught == s.counts.total_planted > 0
    assert s.missed == () and s.false_positive_pairs == ()


def test_extracted_lines_in_another_order_give_the_same_flag_score():
    b = bill("mixed")
    extracted = perfect(b)
    s1, s2 = run(b, extracted), run(b, list(reversed(extracted)))
    assert s1.counts == s2.counts and s1.missed == s2.missed


# --- F6: n/a ---------------------------------------------------------------

def test_f6_types_with_no_planted_flags_are_n_a():
    c = run(bill("clean"), perfect(bill("clean"))).counts
    assert all(c.catch_rate(t) is None for t in sf.FLAG_TYPES)
    assert c.overall_catch_rate is None and c.min_catch_rate is None
    assert sf.FlagCounts().fp_rate_clean is None


def test_min_catch_rate_is_the_worst_type_that_has_planted_flags():
    c = sf.FlagCounts(planted={"a": 4, "b": 2, "c": 0}, caught={"a": 4, "b": 1})
    assert c.min_catch_rate == 0.5 and c.catch_rate("a") == 1.0 and c.catch_rate("c") is None


# --- additive counts --------------------------------------------------------

def test_counts_add_across_bills_and_dicts_merge():
    a = sf.FlagCounts(bills=1, planted={"x": 2}, caught={"x": 1}, clean_bills=1)
    b = sf.FlagCounts(bills=1, planted={"x": 1, "y": 3}, caught={"y": 3}, false_positives={"y": 1})
    c = a + b
    assert (c.bills, c.planted, c.caught, c.false_positives) == (2, {"x": 3, "y": 3}, {"x": 1, "y": 3}, {"y": 1})
    assert sf.total([]) == sf.FlagCounts()
    assert c.catch_rate("x") == pytest.approx(1 / 3)                 # micro-average: 1 of 3


# --- self-check and /core errors --------------------------------------------

def test_a_wrong_expected_flag_shows_up_as_a_core_self_check_mismatch():
    b = bill("clean")
    wrong = replace(b.truth, expected_flags=[ExpectedFlag(line_item_id="1", flag_type="duplicate_line_item")])
    bad = replace(b, truth=wrong)
    s = run(bad, perfect(bad))
    assert s.oracle_matches_expected is False and s.counts.core_self_check_mismatches == 1


def test_a_core_crash_is_counted_and_does_not_stop_the_run(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("core crashed")

    monkeypatch.setattr(sf, "core_analyze", boom)
    b = bill("mixed")
    s = run(b, perfect(b))
    assert s.counts.core_errors == 2                       # pipeline run and oracle run
    assert s.counts.total_caught == 0 and s.counts.total_planted > 0


def test_the_score_holds_ids_and_types_only():
    b = bill("mixed")
    s = run(b, perfect(b)[1:])
    for pair in s.missed + s.false_positive_pairs:
        assert pair[1] in sf.FLAG_TYPES and (pair[0] is None or isinstance(pair[0], str))


# --- PE5 (flag part): a perfect extraction scores 1 for any synthetic bill ---

@settings(max_examples=60, deadline=None)
@given(st.sampled_from(SCENARIOS), st.integers(min_value=1, max_value=40), st.sampled_from(STYLES))
def test_pe5_a_perfect_extraction_scores_one_for_any_synthetic_bill(scenario, seed, style):
    b = build_corpus(scenarios=[scenario], seeds=[seed], styles=[style])[0]
    extracted = perfect(b)
    ex = score_bill(b.bill_id, b.style, b.scenario, b.truth.line_items, result(extracted))
    assert ex.counts.line_recall == 1.0 and ex.counts.line_precision == 1.0
    assert ex.counts.code_exact == 1.0 and ex.counts.charge_exact == 1.0 and ex.failures == ()

    fl = sf.score_flags(b, ex.alignment, extracted)
    assert fl.oracle_matches_expected, (scenario, seed)
    assert fl.counts.total_caught == fl.counts.total_planted
    assert fl.counts.total_false_positives == 0
