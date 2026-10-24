import pytest

from contracts.types import QuantityLimit
from core import analyze, constants
from core.checks.quantity import check_quantity
from core.reference import ReferenceIndex
from tests.core.factories import make_item, make_limit, make_ref


def run(item, *limits):
    return check_quantity([item], ReferenceIndex(list(limits)))


def test_quantity_above_limit_flags():  # TQ1
    flags = run(make_item(quantity=3), make_limit(max_units=2))
    assert len(flags) == 1
    flag = flags[0]
    assert flag.flag_type == "quantity_implausible"
    assert flag.severity == "low"
    assert (flag.data_source, flag.data_year) == ("synthetic-test", 2000)
    assert "quantity of 3 " in flag.reason and "may be worth asking about" in flag.reason
    assert "maximum of 2 units" in flag.reason
    assert "Typical maximum for code 99285: 2 units" in flag.basis
    assert "synthetic-test, 2000" in flag.basis
    assert "$" not in flag.reason + flag.basis


def test_quantity_equal_to_limit_is_not_flagged():  # TQ2
    assert run(make_item(quantity=2), make_limit(max_units=2)) == []


def test_no_limit_or_ambiguous_limits_give_no_flag():  # TQ3
    assert run(make_item(quantity=99, code="12345"), make_limit()) == []
    assert run(make_item(quantity=99), make_limit(max_units=1), make_limit(max_units=2)) == []
    assert run(make_item(quantity=99, code="bad;code"), make_limit()) == []
    assert run(make_item(quantity=99, code=None, code_system=None), make_limit()) == []


@pytest.mark.parametrize("quantity", [None, 0, -1, float("nan"), float("inf"), float("-inf")])
def test_bad_quantity_gives_no_flag(quantity):  # TQ4
    assert run(make_item(quantity=quantity), make_limit(max_units=2)) == []


@pytest.mark.parametrize("max_units", [0, -1, float("nan"), float("inf")])
def test_bad_limit_gives_no_flag(max_units):  # TQ5
    assert run(make_item(quantity=5), make_limit(max_units=max_units)) == []


def test_limit_without_provenance_is_not_used():  # TQ6
    blank = QuantityLimit(code="99285", code_system="CPT", max_units=1, data_source="  ", data_year=2000)
    no_year = QuantityLimit(code="99285", code_system="CPT", max_units=1, data_source="x", data_year=None)
    assert run(make_item(quantity=5), blank) == []
    assert run(make_item(quantity=5), no_year) == []


def test_code_normalization_matches_price_references():  # TQ7
    assert len(run(make_item(code="0120", code_system="REV", quantity=4), make_limit("120", "REV", 3))) == 1
    assert run(make_item(code="00100", code_system="CPT", quantity=4), make_limit("100", "CPT", 3)) == []
    assert len(run(make_item(code="00100", code_system="CPT", quantity=4), make_limit("00100", "CPT", 3))) == 1


def test_fractional_quantities_and_number_formatting():  # TQ8
    flag = run(make_item(quantity=2.5), make_limit(max_units=2))[0]
    assert "quantity of 2.5 " in flag.reason
    whole = run(make_item(quantity=3.0), make_limit(max_units=2.0))[0]
    assert "quantity of 3 " in whole.reason and "3.0" not in whole.reason
    assert run(make_item(quantity=2.01), make_limit(max_units=2))  # just above
    assert run(make_item(quantity=1.99), make_limit(max_units=2)) == []


def test_newest_limit_year_wins():  # TQ9
    old = make_limit(max_units=1, data_year=2000)
    new = make_limit(max_units=10, data_year=2001)
    assert run(make_item(quantity=5), old, new) == []
    assert len(run(make_item(quantity=5), new, old)) == 0
    assert len(run(make_item(quantity=11), old, new)) == 1


def test_huge_quantity_does_not_crash_or_print_digits():
    flag = run(make_item(quantity=1e300), make_limit(max_units=2))[0]
    assert "a very large number" in flag.reason
    assert len(flag.reason) < 300


def test_no_limits_equals_v1_behavior():  # TE1
    refs = [make_ref(medicare_price=10.0, ma_range_high=20.0)]
    items = [make_item(id="1", billed_amount=100.0, quantity=50), make_item(id="2", code="77777")]
    assert analyze(items, refs) == analyze(items, refs, quantity_limits=())


def test_new_arguments_are_keyword_only():  # TE2
    with pytest.raises(TypeError):
        analyze([], [], ())  # type: ignore[misc]


def test_engine_adds_quantity_flags_when_limits_are_supplied():
    items = [make_item(id="1", quantity=5), make_item(id="2", code="77777", quantity=5)]
    flags = analyze(items, [], quantity_limits=[make_limit(max_units=2)])
    assert [(f.line_item_id, f.flag_type) for f in flags] == [("1", "quantity_implausible")]


def test_quantity_flag_text_has_no_banned_words_or_description():
    item = make_item(quantity=5, description="say fraud @@")
    flag = run(item, make_limit(max_units=2))[0]
    text = (flag.reason + flag.basis).lower()
    assert not any(word in text for word in constants.BANNED_WORDS) and "@@" not in text
