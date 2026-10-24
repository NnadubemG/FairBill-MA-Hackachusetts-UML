import dataclasses
import json
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from contracts.types import SyntheticBill
from core import analyze
from synthetic import SCENARIOS, bill_from_dict, generate_bill, to_json

SEEDS = range(200)
SETTINGS = settings(max_examples=100, deadline=None)
scenarios = st.sampled_from(SCENARIOS)
seeds = st.integers(min_value=0, max_value=10_000)


def pairs(items):
    return sorted((x.line_item_id, x.flag_type) for x in items)


def analyzed(bill: SyntheticBill):
    return pairs(analyze(bill.line_items, bill.price_references))


def test_same_seed_and_scenario_give_equal_bills():  # TS-G1
    for scenario in SCENARIOS:
        assert generate_bill(7, scenario) == generate_bill(7, scenario)


def test_different_seeds_give_different_bills():  # TS-G2
    bills = {to_json(generate_bill(seed, "clean")) for seed in range(20)}
    assert len(bills) > 1


def test_clean_bills_have_no_flags():  # TS-G3
    for seed in SEEDS:
        bill = generate_bill(seed, "clean")
        assert bill.expected_flags == []
        assert analyzed(bill) == []


def test_duplicate_scenario():  # TS-G4
    for seed in SEEDS:
        bill = generate_bill(seed, "duplicate")
        dup_ids = [f.line_item_id for f in bill.expected_flags]
        assert len(dup_ids) == 2
        assert {f.flag_type for f in bill.expected_flags} == {"duplicate_line_item"}
        a, b = (next(i for i in bill.line_items if i.id == x) for x in dup_ids)
        assert dataclasses.replace(a, id="") == dataclasses.replace(b, id="")
        assert analyzed(bill) == pairs(bill.expected_flags)


def test_high_price_scenario():  # TS-G5
    for seed in SEEDS:
        bill = generate_bill(seed, "high_price")
        assert len(bill.expected_flags) == 2
        assert len({f.line_item_id for f in bill.expected_flags}) == 1
        assert {f.flag_type for f in bill.expected_flags} == {"price_above_reference", "price_outside_ma_range"}
        assert analyzed(bill) == pairs(bill.expected_flags)


def test_unknown_code_scenario():  # TS-G6
    for seed in SEEDS:
        bill = generate_bill(seed, "unknown_code")
        assert [f.flag_type for f in bill.expected_flags] == ["no_reference_found"]
        flagged = next(i for i in bill.line_items if i.id == bill.expected_flags[0].line_item_id)
        assert flagged.code not in {r.code for r in bill.price_references}
        assert bill.price_references  # references exist, so "nothing loaded" is not the cause
        assert analyzed(bill) == pairs(bill.expected_flags)


def test_injection_scenario_is_inert():  # TS-G7
    for seed in SEEDS:
        bill = generate_bill(seed, "injection")
        assert bill.expected_flags == []
        injected = [i for i in bill.line_items if "IGNORE PREVIOUS INSTRUCTIONS" in (i.raw_description or "")]
        assert len(injected) == 1
        flags = analyze(bill.line_items, bill.price_references)
        assert flags == []
        assert all("IGNORE" not in f.reason + f.basis for f in flags)


def test_mixed_scenario():  # TS-G8
    for seed in SEEDS:
        bill = generate_bill(seed, "mixed")
        assert {f.flag_type for f in bill.expected_flags} == {
            "duplicate_line_item",
            "price_above_reference",
            "price_outside_ma_range",
            "no_reference_found",
        }
        assert analyzed(bill) == pairs(bill.expected_flags)


def test_ids_are_sequential_and_expected_ids_exist():  # TS-G9
    for scenario in SCENARIOS:
        for seed in range(50):
            bill = generate_bill(seed, scenario)
            ids = [i.id for i in bill.line_items]
            assert ids == [str(n) for n in range(1, len(ids) + 1)]
            assert {f.line_item_id for f in bill.expected_flags} <= set(ids)


def test_references_are_labelled_synthetic_and_names_fictional():  # TS-G10
    bill = generate_bill(1, "clean")
    assert bill.price_references
    for ref in bill.price_references:
        assert ref.data_source == "synthetic-demo"
        assert isinstance(ref.data_year, int)
    assert "FICTIONAL" in bill.bill_metadata.hospital_name


def test_total_matches_sum_of_amounts():  # TS-G11 / PS6
    for scenario in SCENARIOS:
        for seed in range(50):
            bill = generate_bill(seed, scenario)
            total = sum(Decimal(str(i.billed_amount)) for i in bill.line_items)
            assert Decimal(str(bill.bill_metadata.total_billed)) == total


def test_amounts_are_finite_positive_two_decimals():  # TS-G12
    for scenario in SCENARIOS:
        for seed in range(50):
            for item in generate_bill(seed, scenario).line_items:
                amount = Decimal(str(item.billed_amount))
                assert amount.is_finite() and amount > 0
                assert amount.as_tuple().exponent >= -2


def test_quantity_lines_are_exact_multiples_of_a_unit_price():  # TS-G13
    seen_multi = False
    for seed in range(100):
        for item in generate_bill(seed, "clean").line_items:
            quantity = Decimal(str(item.quantity))
            if quantity > 1:
                seen_multi = True
            unit = Decimal(str(item.billed_amount)) / quantity
            assert unit == unit.quantize(Decimal("0.01"))
    assert seen_multi  # the catalog really does exercise per-unit pricing


def test_unknown_scenario_raises_with_valid_names():  # TS-G14
    with pytest.raises(ValueError) as error:
        generate_bill(1, "nope")
    assert all(name in str(error.value) for name in SCENARIOS)


def test_revenue_code_is_padded_on_bill_but_unpadded_in_reference():
    codes = {i.code for seed in range(60) for i in generate_bill(seed, "clean").line_items}
    refs = {r.code for r in generate_bill(0, "clean").price_references}
    assert "0120" in codes and "120" in refs and "0120" not in refs


# --- properties -------------------------------------------------------------


@SETTINGS
@given(seeds, scenarios)
def test_ps1_core_agrees_with_ground_truth(seed, scenario):
    bill = generate_bill(seed, scenario)
    assert analyzed(bill) == pairs(bill.expected_flags)


@SETTINGS
@given(seeds, scenarios)
def test_ps2_generation_is_deterministic(seed, scenario):
    assert generate_bill(seed, scenario) == generate_bill(seed, scenario)


@SETTINGS
@given(seeds, scenarios)
def test_ps3_json_round_trip(seed, scenario):
    bill = generate_bill(seed, scenario)
    assert bill_from_dict(json.loads(to_json(bill))) == bill


@SETTINGS
@given(seeds, scenarios)
def test_ps4_ids_unique_and_expected_ids_exist(seed, scenario):
    bill = generate_bill(seed, scenario)
    ids = [i.id for i in bill.line_items]
    assert len(ids) == len(set(ids))
    assert {f.line_item_id for f in bill.expected_flags} <= set(ids)
