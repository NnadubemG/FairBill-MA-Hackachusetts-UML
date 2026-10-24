from core import analyze
from tests.core.factories import make_item, make_ref


def test_empty_items_give_no_flags():  # TC-E1
    assert analyze([], []) == []
    assert analyze([], [make_ref(ma_range_high=1.0)]) == []


def test_output_is_sorted_by_item_id_then_type():  # TC-E2
    refs = [make_ref("99285", medicare_price=10.0, ma_range_high=20.0)]
    items = [
        make_item(id="b", code="99285", billed_amount=100.0),
        make_item(id="a", code="12345", billed_amount=5.0),
        make_item(id="c", code="99285", billed_amount=101.0),
    ]
    flags = analyze(items, refs)
    keys = [(f.line_item_id, f.flag_type) for f in flags]
    assert keys == sorted(keys)
    assert keys == [
        ("a", "no_reference_found"),
        ("b", "price_above_reference"),
        ("b", "price_outside_ma_range"),
        ("c", "price_above_reference"),
        ("c", "price_outside_ma_range"),
    ]


def test_input_order_does_not_change_output():  # TC-E3
    refs = [make_ref("99285", medicare_price=10.0), make_ref("450", "REV", ma_range_high=5.0)]
    items = [
        make_item(id="1", code="99285", billed_amount=100.0),
        make_item(id="2", code="0450", code_system="REV", billed_amount=50.0),
        make_item(id="3", code="77777", billed_amount=1.0),
        make_item(id="4", code="77777", billed_amount=1.0),
    ]
    assert analyze(items, refs) == analyze(list(reversed(items)), list(reversed(refs)))


def test_all_four_flag_types_can_appear_together():
    refs = [make_ref("99285", medicare_price=10.0, ma_range_high=20.0)]
    items = [
        make_item(id="1", code="99285", billed_amount=100.0),
        make_item(id="2", code="55555", billed_amount=10.0),
        make_item(id="3", code="66666", billed_amount=10.0),
        make_item(id="4", code="66666", billed_amount=10.0),
    ]
    found = {f.flag_type for f in analyze(items, refs)}
    assert found == {
        "price_above_reference",
        "price_outside_ma_range",
        "no_reference_found",
        "duplicate_line_item",
    }


def test_reference_data_is_not_modified():
    refs = [make_ref("99285", medicare_price=10.0)]
    items = [make_item(billed_amount=100.0)]
    analyze(items, refs)
    assert refs == [make_ref("99285", medicare_price=10.0)]
    assert items == [make_item(billed_amount=100.0)]
