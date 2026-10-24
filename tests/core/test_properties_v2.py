"""Hypothesis properties for the quantity and unbundling checks (PQ1 to PQ7)."""

from __future__ import annotations

import dataclasses
import math
import string

from hypothesis import Phase, given, settings
from hypothesis import strategies as st

from contracts.types import BundlePair, LineItem, PriceReference, QuantityLimit
from core import analyze
from core.constants import BANNED_WORDS

SETTINGS = settings(max_examples=100, deadline=None)
NEW_TYPES = {"quantity_implausible", "possible_unbundling"}

POOL = ["99285", "93000", "93005", "93001", "0120", "120", "00100", "J1100", "FRAUD", "99285;x", ""]
codes = st.one_of(st.none(), st.sampled_from(POOL), st.text(max_size=12))
systems = st.sampled_from([None, "CPT", "HCPCS", "DRG", "REV", "OTHER"])
numbers = st.floats(allow_nan=True, allow_infinity=True)
quantities = st.one_of(st.none(), numbers, st.integers(min_value=-2, max_value=60), st.floats(0, 60))
sources = st.sampled_from(["CMS", "synthetic-test", "", "   "])  # includes unusable ones on purpose
dates = st.sampled_from([None, "2026-03-01", "2026-03-02", "not a date"])
descriptions = st.builds(lambda t: f"@@{t}@@", st.text(alphabet=string.ascii_letters + " ", max_size=8))

# Two families of data, mixed together. The "wild" one is hostile (NaN, blank sources, odd
# codes) but rarely lines up well enough to trigger a flag. The "focused" one usually
# matches, so the checks really fire. Without it the properties would pass vacuously.
FOCUSED = [("99285", "CPT"), ("93000", "CPT"), ("93005", "CPT"), ("0120", "REV")]
focused_code = st.sampled_from(FOCUSED)

wild_items = st.builds(
    LineItem,
    id=st.just("x"),
    description=descriptions,
    billed_amount=st.one_of(numbers, st.floats(0, 5000)),
    code=codes,
    code_system=systems,
    quantity=quantities,
    date_of_service=dates,
)
focused_items = focused_code.flatmap(
    lambda cs: st.builds(
        LineItem,
        id=st.just("x"),
        description=descriptions,
        billed_amount=st.floats(1, 500),
        code=st.just(cs[0]),
        code_system=st.sampled_from([cs[1], cs[1], None]),
        quantity=st.one_of(st.integers(1, 6), st.floats(0.5, 6)),
        date_of_service=st.sampled_from([None, "2026-03-01"]),
    )
)
# Unique ids, so a flag can be traced back to exactly one input item.
item_lists = st.lists(st.one_of(wild_items, focused_items), max_size=8).map(
    lambda items: [dataclasses.replace(item, id=str(i)) for i, item in enumerate(items)]
)

wild_limits = st.builds(
    QuantityLimit,
    code=st.sampled_from(POOL),
    code_system=systems,
    max_units=st.one_of(numbers, st.integers(-1, 40), st.floats(0, 40)),
    data_source=sources,
    data_year=st.one_of(st.integers(1999, 2030), st.none()),
)
focused_limits = focused_code.flatmap(
    lambda cs: st.builds(
        QuantityLimit,
        code=st.just(cs[0]),
        code_system=st.sampled_from([cs[1], cs[1], None]),
        max_units=st.integers(1, 4),
        data_source=st.just("CMS"),
        data_year=st.integers(1999, 2030),
    )
)
limits = st.one_of(wild_limits, focused_limits)

wild_pairs = st.builds(
    BundlePair,
    code_1=st.sampled_from(POOL),
    code_2=st.sampled_from(POOL),
    modifier_indicator=st.sampled_from(["0", "1", "9", "7", ""]),
    data_source=sources,
    data_year=st.one_of(st.integers(1999, 2030), st.none()),
)
focused_pairs = st.builds(
    BundlePair,
    code_1=st.sampled_from(["99285", "93000"]),
    code_2=st.sampled_from(["93005", "93000", "0120"]),
    modifier_indicator=st.sampled_from(["0", "1", "9"]),
    data_source=st.just("CMS"),
    data_year=st.integers(1999, 2030),
)
pairs = st.one_of(wild_pairs, focused_pairs)
limit_lists = st.lists(limits, max_size=6)
pair_lists = st.lists(pairs, max_size=6)
refs_lists = st.lists(
    st.builds(
        PriceReference,
        code=st.sampled_from(POOL),
        data_source=st.sampled_from(["CMS", "synthetic-test"]),
        data_year=st.integers(1999, 2030),
        code_system=systems,
        medicare_price=st.one_of(st.none(), st.floats(0, 100)),
        ma_range_high=st.one_of(st.none(), st.floats(0, 200)),
    ),
    max_size=4,
)


def text_of(flag) -> str:
    return flag.reason + "\n" + flag.basis


def usable_source(record) -> bool:
    return isinstance(record.data_source, str) and record.data_source.strip() != "" and isinstance(record.data_year, int)


@SETTINGS
@given(item_lists, refs_lists, limit_lists, pair_lists)
def test_pq1_new_data_only_adds_new_flag_types(items, refs, qlimits, bpairs):
    before = analyze(items, refs)
    after = analyze(items, refs, quantity_limits=qlimits, bundle_pairs=bpairs)
    assert all(f.flag_type not in NEW_TYPES for f in before)
    assert [f for f in after if f.flag_type not in NEW_TYPES] == before
    assert analyze(items, refs, quantity_limits=(), bundle_pairs=()) == before


@SETTINGS
@given(item_lists, refs_lists, limit_lists, pair_lists)
def test_pq2_no_banned_words(items, refs, qlimits, bpairs):
    for flag in analyze(items, refs, quantity_limits=qlimits, bundle_pairs=bpairs):
        lowered = text_of(flag).lower()
        assert not any(word in lowered for word in BANNED_WORDS), flag


@SETTINGS
@given(item_lists, refs_lists, limit_lists, pair_lists)
def test_pq3_bill_text_never_appears(items, refs, qlimits, bpairs):
    for flag in analyze(items, refs, quantity_limits=qlimits, bundle_pairs=bpairs):
        assert "@@" not in text_of(flag)


@SETTINGS
@given(st.data(), item_lists, refs_lists, limit_lists, pair_lists)
def test_pq4_order_independence(data, items, refs, qlimits, bpairs):
    expected = analyze(items, refs, quantity_limits=qlimits, bundle_pairs=bpairs)
    shuffled = analyze(
        data.draw(st.permutations(items)),
        data.draw(st.permutations(refs)),
        quantity_limits=data.draw(st.permutations(qlimits)),
        bundle_pairs=data.draw(st.permutations(bpairs)),
    )
    assert shuffled == expected


@SETTINGS
@given(
    st.lists(
        st.builds(
            LineItem,
            id=st.text(max_size=3),
            description=st.text(max_size=5),
            billed_amount=numbers,
            code=codes,
            code_system=systems,
            quantity=st.one_of(st.none(), numbers),
            date_of_service=st.one_of(st.none(), st.text(max_size=12)),
        ),
        max_size=6,
    ),
    st.lists(
        st.builds(
            QuantityLimit,
            code=st.text(max_size=8),
            code_system=systems,
            max_units=numbers,
            data_source=st.text(max_size=4),
            data_year=st.one_of(st.integers(), st.none()),
        ),
        max_size=4,
    ),
    st.lists(
        st.builds(
            BundlePair,
            code_1=st.text(max_size=8),
            code_2=st.text(max_size=8),
            modifier_indicator=st.text(max_size=2),
            data_source=st.text(max_size=4),
            data_year=st.integers(),
        ),
        max_size=4,
    ),
)
def test_pq5_never_raises(items, qlimits, bpairs):
    analyze(items, [], quantity_limits=qlimits, bundle_pairs=bpairs)


@SETTINGS
@given(item_lists, limit_lists)
def test_pq6_quantity_flags_have_a_real_limit_below_the_quantity(items, qlimits):
    by_id = {item.id: item for item in items}
    for flag in analyze(items, [], quantity_limits=qlimits):
        if flag.flag_type != "quantity_implausible":
            continue
        quantity = by_id[flag.line_item_id].quantity
        assert quantity is not None and math.isfinite(quantity) and quantity > 0
        assert isinstance(flag.data_source, str) and flag.data_source.strip() and isinstance(flag.data_year, int)
        assert any(
            usable_source(limit)
            and isinstance(limit.max_units, (int, float))
            and math.isfinite(limit.max_units)
            and 0 < limit.max_units < quantity
            for limit in qlimits
        )


@SETTINGS
@given(item_lists, pair_lists)
def test_pq7_unbundling_flags_point_at_a_code_2_line(items, bpairs):
    by_id = {item.id: item for item in items}
    usable = [p for p in bpairs if usable_source(p) and p.modifier_indicator in ("0", "1")]
    code_2s = {p.code_2.strip().upper() for p in usable}
    code_1s = {p.code_1.strip().upper() for p in usable}
    for flag in analyze(items, [], bundle_pairs=bpairs):
        if flag.flag_type != "possible_unbundling":
            continue
        item = by_id[flag.line_item_id]
        assert item.code is not None and item.code.strip().upper() in code_2s
        assert item.code_system in (None, "CPT", "HCPCS")
        # the matching primary code really is on the bill
        assert any(o.code is not None and o.code.strip().upper() in code_1s for o in items if o is not item)


# --- guards against vacuous properties ---------------------------------------


def test_generators_really_trigger_quantity_flags():
    from hypothesis import find

    find(
        st.tuples(item_lists, limit_lists),
        lambda t: any(f.flag_type == "quantity_implausible" for f in analyze(t[0], [], quantity_limits=t[1])),
        settings=settings(max_examples=2000, database=None, phases=[Phase.generate]),
    )


def test_generators_really_trigger_unbundling_flags():
    from hypothesis import find

    find(
        st.tuples(item_lists, pair_lists),
        lambda t: any(f.flag_type == "possible_unbundling" for f in analyze(t[0], [], bundle_pairs=t[1])),
        settings=settings(max_examples=2000, database=None, phases=[Phase.generate]),
    )
