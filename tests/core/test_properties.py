"""Hypothesis property tests (PR1 to PR11 in .kiro/specs/core-checks/design.md)."""

from __future__ import annotations

import string

from hypothesis import given, settings
from hypothesis import strategies as st

from contracts.types import LineItem, PriceReference
from core import analyze
from core.constants import BANNED_WORDS
from core.reference import normalize_code

SETTINGS = settings(max_examples=100, deadline=None)

# --- strategies -------------------------------------------------------------

# A small pool so items and references often match, plus hostile values.
CODE_POOL = ["99285", "00100", "450", "0450", "061", "61", "J1100", "E11.9", "FRAUD", "Illegal7", "99285;x", ""]
codes = st.one_of(st.none(), st.sampled_from(CODE_POOL), st.text(max_size=15))
systems = st.sampled_from([None, "CPT", "HCPCS", "DRG", "REV", "ICD10", "OTHER"])

# Includes NaN, infinity, huge, tiny, zero, and negative values on purpose.
numbers = st.floats(allow_nan=True, allow_infinity=True)
amounts = st.one_of(numbers, st.floats(min_value=0, max_value=1e6), st.integers(min_value=0, max_value=10**7))
optional_amounts = st.one_of(st.none(), amounts)

dates = st.one_of(
    st.none(),
    st.sampled_from(["2026-03-01", "2026-03-02", "not a date", ""]),
)

# '@@' never appears in any template, so it marks "text from the bill".
descriptions = st.builds(lambda tail: f"@@{tail}@@", st.text(alphabet=string.ascii_letters + " ", max_size=10))

line_items = st.builds(
    LineItem,
    id=st.sampled_from(["1", "2", "3", "4", "5"]),
    description=descriptions,
    billed_amount=amounts,
    code=codes,
    code_system=systems,
    quantity=optional_amounts,
    date_of_service=dates,
)

# Reference data is trusted (not bill text), so its source is a fixed safe label.
price_references = st.builds(
    PriceReference,
    code=st.sampled_from(CODE_POOL),
    data_source=st.sampled_from(["CMS", "CHIA", "synthetic-test", ""]),
    data_year=st.integers(min_value=1999, max_value=2030),
    code_system=systems,
    medicare_price=optional_amounts,
    ma_range_low=optional_amounts,
    ma_range_high=optional_amounts,
)

item_lists = st.lists(line_items, max_size=8)
ref_lists = st.lists(price_references, max_size=6)


def text_of(flag) -> str:
    return flag.reason + "\n" + flag.basis


# --- properties -------------------------------------------------------------


@SETTINGS
@given(item_lists, ref_lists)
def test_pr1_no_banned_words(items, refs):
    for flag in analyze(items, refs):
        lowered = text_of(flag).lower()
        for word in BANNED_WORDS:
            assert word not in lowered, (word, flag)


@SETTINGS
@given(item_lists, ref_lists)
def test_pr2_numbers_carry_provenance(items, refs):
    for flag in analyze(items, refs):
        if "$" in text_of(flag):
            assert isinstance(flag.data_source, str) and flag.data_source.strip() != ""
            assert isinstance(flag.data_year, int)


@SETTINGS
@given(ref_lists)
def test_pr3_empty_bill_gives_no_flags(refs):
    assert analyze([], refs) == []


@SETTINGS
@given(item_lists, ref_lists)
def test_pr4_flags_refer_to_real_items(items, refs):
    real_ids = {item.id for item in items}
    for flag in analyze(items, refs):
        assert flag.line_item_id in real_ids


@SETTINGS
@given(st.data(), item_lists, ref_lists)
def test_pr5_order_independence(data, items, refs):
    shuffled_items = data.draw(st.permutations(items))
    shuffled_refs = data.draw(st.permutations(refs))
    assert analyze(shuffled_items, shuffled_refs) == analyze(items, refs)


@SETTINGS
@given(item_lists, ref_lists)
def test_pr6_deterministic(items, refs):
    assert analyze(items, refs) == analyze(items, refs)


@SETTINGS
@given(item_lists)
def test_pr7_no_references_means_no_price_or_coverage_flags(items):
    for flag in analyze(items, []):
        assert flag.flag_type == "duplicate_line_item"


@SETTINGS
@given(item_lists, st.lists(st.builds(
    PriceReference,
    code=st.sampled_from(CODE_POOL),
    data_source=st.just("CMS"),
    data_year=st.just(2000),
    code_system=systems,
), max_size=6))
def test_pr8_references_without_figures_give_no_price_flags(items, refs):
    for flag in analyze(items, refs):
        assert not flag.flag_type.startswith("price_")


@SETTINGS
@given(item_lists, ref_lists)
def test_pr9_bill_text_never_appears_in_output(items, refs):
    for flag in analyze(items, refs):
        assert "@@" not in text_of(flag)


@SETTINGS
@given(
    st.lists(st.builds(
        LineItem,
        id=st.text(max_size=3),
        description=st.text(max_size=5),
        billed_amount=numbers,
        code=codes,
        code_system=systems,
        quantity=st.one_of(st.none(), numbers),
        date_of_service=st.one_of(st.none(), st.text(max_size=12)),
    ), max_size=6),
    st.lists(st.builds(
        PriceReference,
        code=codes.filter(lambda c: c is not None),
        data_source=st.text(max_size=5),
        data_year=st.integers(),
        code_system=systems,
        medicare_price=st.one_of(st.none(), numbers),
        ma_range_low=st.one_of(st.none(), numbers),
        ma_range_high=st.one_of(st.none(), numbers),
    ), max_size=4),
)
def test_pr10_never_raises(items, refs):
    analyze(items, refs)


@SETTINGS
@given(st.text(max_size=20), systems)
def test_pr11_normalization_is_idempotent(code, system):
    once = normalize_code(code, system)
    if once is not None:
        assert normalize_code(once, system) == once


@SETTINGS
@given(st.text(alphabet=string.digits, min_size=1, max_size=6), st.integers(min_value=0, max_value=5),
       st.sampled_from(["REV", "DRG"]))
def test_pr11_rev_and_drg_ignore_leading_zeros(digits, extra_zeros, system):
    assert normalize_code("0" * extra_zeros + digits, system) == normalize_code(digits, system)
