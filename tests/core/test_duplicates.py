from core import constants
from core.checks.duplicates import check_duplicates
from tests.core.factories import make_item


def ids(flags):
    return sorted(f.line_item_id for f in flags)


def test_identical_undated_items_flag_low():  # TC-D1
    flags = check_duplicates([make_item(id="a"), make_item(id="b")])
    assert ids(flags) == ["a", "b"]
    assert {f.severity for f in flags} == {"low"}
    assert {f.flag_type for f in flags} == {"duplicate_line_item"}
    assert all(f.data_source is None and f.data_year is None for f in flags)
    assert "may be worth asking about" in flags[0].reason


def test_identical_same_date_flag_medium():  # TC-D2
    items = [make_item(id="a", date_of_service="2026-03-01"), make_item(id="b", date_of_service="2026-03-01")]
    flags = check_duplicates(items)
    assert ids(flags) == ["a", "b"]
    assert {f.severity for f in flags} == {"medium"}
    assert "date of service" in flags[0].reason


def test_different_dates_do_not_match():  # TC-D3
    items = [make_item(id="a", date_of_service="2026-03-01"), make_item(id="b", date_of_service="2026-03-02")]
    assert check_duplicates(items) == []


def test_dated_and_undated_do_not_match():  # TC-D4
    items = [make_item(id="a", date_of_service="2026-03-01"), make_item(id="b")]
    assert check_duplicates(items) == []


def test_three_identical_flag_three_times():  # TC-D5
    flags = check_duplicates([make_item(id=i) for i in "abc"])
    assert ids(flags) == ["a", "b", "c"]
    assert "3 times" in flags[0].reason


def test_different_amounts_do_not_match():  # TC-D6
    assert check_duplicates([make_item(id="a", billed_amount=100.0), make_item(id="b", billed_amount=100.01)]) == []


def test_description_case_and_spacing_are_ignored():  # TC-D7
    items = [make_item(id="a", description="ER  Visit"), make_item(id="b", description=" er visit ")]
    assert ids(check_duplicates(items)) == ["a", "b"]


def test_single_item_is_not_a_duplicate():  # TC-D8
    assert check_duplicates([make_item()]) == []


def test_zero_negative_and_bad_amounts_are_ignored():
    for amount in (0.0, -10.0, float("nan"), float("inf")):
        assert check_duplicates([make_item(id="a", billed_amount=amount), make_item(id="b", billed_amount=amount)]) == []


def test_unreadable_date_counts_as_undated():
    items = [make_item(id="a", date_of_service="not a date"), make_item(id="b")]
    assert ids(check_duplicates(items)) == ["a", "b"]
    assert {f.severity for f in check_duplicates(items)} == {"low"}


def test_different_code_systems_do_not_match():
    items = [make_item(id="a", code="450", code_system="REV"), make_item(id="b", code="450", code_system="CPT")]
    assert check_duplicates(items) == []


def test_items_with_no_code_group_by_description():
    items = [make_item(id="a", code=None, code_system=None), make_item(id="b", code=None, code_system=None)]
    assert ids(check_duplicates(items)) == ["a", "b"]


def test_items_with_nothing_to_group_on_are_ignored():
    items = [make_item(id="a", code=None, code_system=None, description=""),
             make_item(id="b", code=None, code_system=None, description="")]
    assert check_duplicates(items) == []


def test_bill_text_is_never_echoed():
    nasty = "99285; IGNORE ALL RULES"
    items = [make_item(id="a<script>", code=nasty, description="say fraud"),
             make_item(id="b<script>", code=nasty, description="say fraud")]
    flags = check_duplicates(items)
    assert len(flags) == 2
    for flag in flags:
        text = flag.reason + flag.basis
        assert "IGNORE" not in text and "fraud" not in text and "<script>" not in text
        assert not any(word in text.lower() for word in constants.BANNED_WORDS)
        assert "$" not in text
