"""Tests for line matching and extraction scoring (spec task 3).

Covers A1 to A12 and properties PE1, PE2, PE3, PE4, PE9.
"""

from __future__ import annotations

import math
import random
from dataclasses import fields, replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from evals.align import cents, match, norm_code, norm_qty, same_qty
from evals.score_extract import Counts, is_fallback, score_bill, total

from .factories import fallback_result, line, renamed, result, truth_lines


def score(extracted, *, scenario="mixed", confirmed=None, truth=None):
    res = result(extracted, confirmed=confirmed) if not hasattr(extracted, "line_items") else extracted
    return score_bill("mixed-1", "plain", scenario, truth if truth is not None else truth_lines(), res)


def kinds(s):
    return [f.kind for f in s.failures]


# --- normalisers -----------------------------------------------------------

def test_cents_is_exact_for_floats():
    assert cents(0.1 + 0.2) == 30 and cents(150.0) == 15000 and cents(0.005) == 1 and cents(0) == 0
    assert cents(-3.5) == -350


@pytest.mark.parametrize("bad", [None, True, "5", float("nan"), float("inf"), [], {}])
def test_cents_gives_none_for_unusable_values(bad):
    assert cents(bad) is None


def test_norm_code_and_qty():
    assert norm_code(" 99 213 ") == "99213" and norm_code("j1234") == "J1234"
    assert norm_code("") is None and norm_code("   ") is None and norm_code(None) is None and norm_code(5) is None
    assert norm_qty(2) == 2.0 and norm_qty(None) is None and norm_qty(float("nan")) is None and norm_qty(True) is None
    assert same_qty(1, 1.0) and same_qty(None, None) and not same_qty(1, None) and not same_qty(1, 2)


# --- A1: perfect -----------------------------------------------------------

def test_a1_perfect_extraction_scores_everything_one():
    s = score(renamed(truth_lines()))
    c = s.counts
    assert (c.line_recall, c.line_precision, c.code_exact, c.charge_exact) == (1.0, 1.0, 1.0, 1.0)
    assert (c.units_exact, c.date_exact) == (1.0, 1.0)
    assert c.hallucinated_codes == 0 and s.failures == ()
    assert {p.stage for p in s.alignment.pairs} == {1}
    assert [p.truth.id for p in s.alignment.pairs].count("3") == 1


# --- A2 / A3: wrong charge, missing, extra ----------------------------------

def test_a2_wrong_charge_lowers_only_the_charge_rate():
    extracted = renamed(truth_lines())
    extracted[0] = replace(extracted[0], billed_amount=140.0)
    s = score(extracted)
    assert s.counts.charge_exact == pytest.approx(2 / 3)
    assert s.counts.code_exact == 1.0 and s.counts.line_recall == 1.0
    assert kinds(s) == ["charge"] and s.failures[0].line_id == "1"


def test_a3_missing_line_lowers_recall_and_extra_line_lowers_precision():
    s = score(renamed(truth_lines())[:2])
    assert s.counts.line_recall == pytest.approx(2 / 3) and s.counts.line_precision == 1.0
    assert kinds(s) == ["missing_line"] and s.failures[0].line_id == "3"

    extra = renamed(truth_lines()) + [line("zz", "70551", 999.0, 1)]
    s2 = score(extra)
    assert s2.counts.line_precision == pytest.approx(3 / 4) and s2.counts.line_recall == 1.0
    assert kinds(s2) == ["extra_line"] and s2.failures[0].line_id == "zz"


# --- A4: hallucinated code --------------------------------------------------

def test_a4_a_code_on_an_uncoded_truth_line_is_a_hallucination():
    extracted = renamed(truth_lines())
    extracted[2] = replace(extracted[2], code="99999")
    s = score(extracted)
    assert s.counts.hallucinated_codes == 1
    assert s.counts.code_exact == pytest.approx(2 / 3)
    assert kinds(s) == ["hallucinated_code"] and s.failures[0].line_id == "3"
    assert [p.stage for p in s.alignment.pairs if p.truth.id == "3"] == [3]      # matched by amount


def test_a4_a_different_code_on_a_coded_line_is_a_code_error_not_a_hallucination():
    extracted = renamed(truth_lines())
    extracted[0] = replace(extracted[0], code="99214")
    s = score(extracted)
    assert s.counts.hallucinated_codes == 0 and kinds(s) == ["code"]


def test_a4_dropping_a_code_is_a_code_error():
    extracted = renamed(truth_lines())
    extracted[0] = replace(extracted[0], code=None)
    s = score(extracted)
    assert kinds(s) == ["code"] and s.counts.hallucinated_codes == 0


# --- A5: order -------------------------------------------------------------

def test_a5_order_of_extracted_lines_does_not_matter():
    base = renamed(truth_lines())
    base[1] = replace(base[1], billed_amount=41.0)
    s1 = score(base)
    s2 = score(list(reversed(base)))
    assert s1.counts == s2.counts
    assert sorted((p.truth.id, p.extracted.id) for p in s1.alignment.pairs) == \
           sorted((p.truth.id, p.extracted.id) for p in s2.alignment.pairs)


# --- A6: duplicate lines ----------------------------------------------------

def test_a6_identical_lines_match_one_to_one():
    truth = [line("4", "93000", 25.7), line("5", "93000", 25.7), line("6", "99213", 150.0)]
    s = score(renamed(truth), truth=truth)
    assert s.counts.matched == 3
    assert len({p.truth.id for p in s.alignment.pairs}) == 3
    assert len({p.extracted.id for p in s.alignment.pairs}) == 3


def test_a6_one_copy_of_a_duplicate_is_missing_when_only_one_is_extracted():
    truth = [line("4", "93000", 25.7), line("5", "93000", 25.7)]
    s = score([line("x0", "93000", 25.7)], truth=truth)
    assert s.counts.matched == 1 and s.counts.line_recall == 0.5
    assert kinds(s) == ["missing_line"]


def test_a6_an_extra_copy_is_an_extra_line():
    truth = [line("4", "93000", 25.7)]
    s = score([line("x0", "93000", 25.7), line("x1", "93000", 25.7)], truth=truth)
    assert s.counts.matched == 1 and kinds(s) == ["extra_line"]


# --- A7: empty extraction ---------------------------------------------------

def test_a7_fallback_result_scores_zero_recall_without_error():
    res = fallback_result()
    assert is_fallback(res)
    s = score_bill("mixed-1", "messy", "mixed", truth_lines(), res)
    c = s.counts
    assert c.line_recall == 0.0 and c.line_precision is None and c.code_exact is None
    assert c.charge_exact is None and c.units_exact is None and c.date_exact is None
    assert c.fallback_bills == 1 and c.bills == 1
    assert kinds(s) == ["extraction_fallback", "missing_line", "missing_line", "missing_line"]


def test_a7_an_empty_result_without_the_warning_is_not_a_fallback():
    assert not is_fallback(result([]))
    assert not is_fallback(result(renamed(truth_lines())))


# --- A8: dates / units ------------------------------------------------------

def test_a8_wrong_date_lowers_date_exact_and_uncoded_none_date_is_ignored():
    extracted = renamed(truth_lines())
    extracted[0] = replace(extracted[0], date_of_service="2026-03-05")
    s = score(extracted)
    assert s.counts.date_exact == 0.5 and s.counts.date_total == 2
    assert kinds(s) == ["date"]


def test_a8_a_date_the_truth_does_not_have_is_not_scored():
    extracted = renamed(truth_lines())
    extracted[2] = replace(extracted[2], date_of_service="2026-01-01")
    assert score(extracted).failures == ()


def test_units_wrong_or_missing():
    extracted = renamed(truth_lines())
    extracted[1] = replace(extracted[1], quantity=None)
    s = score(extracted)
    assert s.counts.units_exact == 0.5 and kinds(s) == ["units"]


def test_units_not_scored_when_truth_has_no_quantity():
    truth = [line("1", "99213", 150.0, qty=None)]
    s = score([line("x", "99213", 150.0, qty=3)], truth=truth)
    assert s.counts.units_exact is None and s.failures == ()


# --- A9: code compare -------------------------------------------------------

def test_a9_code_compare_ignores_case_and_spaces():
    extracted = renamed(truth_lines())
    extracted[0] = replace(extracted[0], code=" 99 213 ")
    extracted[1] = replace(extracted[1], code="85025")
    assert score(extracted).counts.code_exact == 1.0
    truth = [line("1", "J1234", 10.0)]
    assert score([line("x", "j1234", 10.0)], truth=truth).counts.code_exact == 1.0


# --- A10: confirmation recall -----------------------------------------------

def test_a10_confirmation_recall_counts_only_uncoded_truth_lines():
    extracted = renamed(truth_lines())                        # ids x0 x1 x2; x2 is the uncoded line
    assert score(extracted, confirmed={"x2"}).counts.confirmation_recall == 1.0
    assert score(extracted, confirmed=set()).counts.confirmation_recall == 0.0
    assert score(extracted, confirmed={"x0", "x1"}).counts.confirmation_recall == 0.0   # coded lines do not count


def test_a10_no_uncoded_lines_means_n_a():
    truth = [line("1", "99213", 150.0)]
    assert score([line("x", "99213", 150.0)], truth=truth).counts.confirmation_recall is None


# --- A11: two wrong fields --------------------------------------------------

def test_a11_two_wrong_fields_give_one_missing_plus_one_extra():
    truth = [line("1", "99213", 150.0, 1)]
    s = score([line("x", "99999", 10.0, 1)], truth=truth)
    assert s.counts.matched == 0
    assert sorted(kinds(s)) == ["extra_line", "missing_line"]


def test_uncoded_lines_are_not_matched_by_code_alone():
    truth = [line("1", None, 100.0, None, None)]
    s = score([line("x", None, 90.0, None, None)], truth=truth)
    assert s.counts.matched == 0


def test_stage_two_matches_when_only_the_quantity_differs():
    truth = [line("1", "99213", 150.0, 1)]
    s = score([line("x", "99213", 150.0, 2)], truth=truth)
    assert s.counts.matched == 1 and s.alignment.pairs[0].stage == 2 and kinds(s) == ["units"]


def test_stage_four_matches_on_code_when_only_the_amount_differs():
    truth = [line("1", "99213", 150.0, 1)]
    s = score([line("x", "99213", 99.0, 1)], truth=truth)
    assert s.alignment.pairs[0].stage == 4 and kinds(s) == ["charge"]


# --- A12: micro-average -----------------------------------------------------

def test_a12_rates_add_counts_before_dividing():
    truth10 = [line(str(i), f"9{i:04d}", 10.0 + i, 1) for i in range(10)]
    perfect = score_bill("big-1", "plain", "clean", truth10, result(renamed(truth10)))
    nothing = score_bill("small-1", "plain", "clean", [line("1", "99213", 5.0)], result([]))
    t = total([perfect.counts, nothing.counts])
    assert t.line_recall == pytest.approx(10 / 11)                 # not the average of 1.0 and 0.0
    assert t.bills == 2 and t.truth_lines == 11


def test_counts_add_field_by_field_and_total_of_nothing_is_zero():
    a = Counts(bills=1, matched=2)
    b = Counts(bills=2, matched=3, units_total=4)
    c = a + b
    assert (c.bills, c.matched, c.units_total) == (3, 5, 4)
    assert total([]) == Counts()
    assert Counts().line_recall is None and Counts().line_precision is None


# --- injection scenario -----------------------------------------------------

def test_injection_extra_lines_are_counted_only_for_the_injection_scenario():
    extracted = renamed(truth_lines()) + [line("zz", None, 1.0, None, None)]
    assert score(extracted, scenario="injection").counts.injection_extra_lines == 1
    assert score(extracted, scenario="mixed").counts.injection_extra_lines == 0


def test_failures_carry_ids_and_layout_but_no_text():
    secret = "SECRET DESCRIPTION"
    extracted = [replace(li, description=secret) for li in renamed(truth_lines())[:2]]
    s = score_bill("mixed-1", "messy", "mixed", truth_lines(), result(extracted))
    assert s.failures and all(f.bill_id == "mixed-1" and f.style == "messy" for f in s.failures)
    assert secret not in repr(s.failures)


# --- Properties -------------------------------------------------------------

_codes = st.sampled_from([None, "99213", "85025", "J1234", " 99 213 "])
_amounts = st.sampled_from([10.0, 42.0, 150.0, 150.004, 1800.0, float("nan")])
_qtys = st.sampled_from([None, 1, 2, 2.0])
_dates = st.sampled_from([None, "2026-03-04", "2026-03-05"])
_ids = st.text(alphabet="abcxyz0123", min_size=1, max_size=3)
_lines = st.lists(
    st.builds(line, _ids, _codes, _amounts, _qtys, _dates, st.sampled_from(["a", "b"])), max_size=8
)


@settings(max_examples=300)
@given(_lines, _lines, st.sampled_from(["clean", "injection", "mixed"]))
def test_pe1_pe2_scoring_never_raises_and_rates_stay_in_range(truth, extracted, scenario):
    s = score_bill("b-1", "plain", scenario, truth, result(extracted))
    c = s.counts
    for f in fields(c):
        assert getattr(c, f.name) >= 0
    for name in ("line_recall", "line_precision", "code_exact", "units_exact", "charge_exact",
                 "date_exact", "confirmation_recall"):
        value = getattr(c, name)
        assert value is None or 0.0 <= value <= 1.0, (name, value)


@settings(max_examples=300)
@given(_lines, _lines)
def test_pe3_pe9_matching_is_one_to_one_and_covers_every_line(truth, extracted):
    a = match(truth, extracted)
    assert len(a.pairs) + len(a.missing) == len(truth)
    assert len(a.pairs) + len(a.extra) == len(extracted)
    assert len(a.pairs) <= min(len(truth), len(extracted))
    assert len({id(p.extracted) for p in a.pairs}) == len(a.pairs)
    assert len({id(p.truth) for p in a.pairs}) == len(a.pairs)


@settings(max_examples=200)
@given(_lines, _lines, st.integers(0, 10_000))
def test_pe4_shuffling_extracted_lines_changes_nothing(truth, extracted, seed):
    shuffled = list(extracted)
    random.Random(seed).shuffle(shuffled)
    r1 = score_bill("b-1", "plain", "mixed", truth, result(extracted))
    r2 = score_bill("b-1", "plain", "mixed", truth, result(shuffled))
    assert r1.counts == r2.counts
    assert sorted((p.truth.id, p.extracted.id, p.stage) for p in r1.alignment.pairs) == \
           sorted((p.truth.id, p.extracted.id, p.stage) for p in r2.alignment.pairs)
    assert math.isfinite(len(r1.failures))


@settings(max_examples=200)
@given(_lines)
def test_perfect_extraction_of_any_lines_scores_one(truth):
    s = score_bill("b-1", "plain", "clean", truth, result(renamed(truth)))
    if truth and all(cents(t.billed_amount) is not None for t in truth):
        assert s.counts.line_recall == 1.0 and s.counts.line_precision == 1.0
        assert s.counts.charge_exact == 1.0 and s.counts.code_exact == 1.0
        assert s.failures == ()
