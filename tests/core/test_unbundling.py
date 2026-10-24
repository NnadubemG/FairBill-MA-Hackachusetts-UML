import pytest

from contracts.types import BundlePair
from core import analyze, constants
from core.checks.unbundling import check_unbundling
from tests.core.factories import make_item, make_pair


def primary(**kw):
    return make_item(id="p", code="93000", **kw)


def secondary(**kw):
    return make_item(id="s", code="93005", **kw)


def ids(flags):
    return sorted(f.line_item_id for f in flags)


def test_both_codes_present_flags_the_code_2_line_only():  # TU1
    flags = check_unbundling([primary(), secondary()], [make_pair()])
    assert ids(flags) == ["s"]
    flag = flags[0]
    assert flag.flag_type == "possible_unbundling"
    assert (flag.data_source, flag.data_year) == ("synthetic-test", 2000)
    assert "93005" in flag.reason and "93000" in flag.reason
    assert "may be worth asking about" in flag.reason
    assert "93000" in flag.basis and "93005" in flag.basis and "synthetic-test, 2000" in flag.basis
    assert "$" not in flag.reason + flag.basis


def test_dates_must_agree():  # TU2
    pair = [make_pair()]
    same = check_unbundling([primary(date_of_service="2026-03-01"), secondary(date_of_service="2026-03-01")], pair)
    differ = check_unbundling([primary(date_of_service="2026-03-01"), secondary(date_of_service="2026-03-02")], pair)
    mixed1 = check_unbundling([primary(date_of_service="2026-03-01"), secondary()], pair)
    mixed2 = check_unbundling([primary(), secondary(date_of_service="2026-03-01")], pair)
    assert ids(same) == ["s"]
    assert differ == [] and mixed1 == [] and mixed2 == []


def test_one_code_alone_is_not_flagged():  # TU3
    assert check_unbundling([primary()], [make_pair()]) == []
    assert check_unbundling([secondary()], [make_pair()]) == []
    assert check_unbundling([], [make_pair()]) == []


def test_severity_follows_the_modifier_indicator_and_9_is_ignored():  # TU4
    items = [primary(), secondary()]
    assert check_unbundling(items, [make_pair(modifier_indicator="0")])[0].severity == "medium"
    assert check_unbundling(items, [make_pair(modifier_indicator="1")])[0].severity == "low"
    assert check_unbundling(items, [make_pair(modifier_indicator="9")]) == []
    assert check_unbundling(items, [make_pair(modifier_indicator="7")]) == []


def test_unusable_pairs_are_ignored():  # TU5
    items = [primary(), secondary()]
    assert check_unbundling(items, [make_pair(data_source="")]) == []
    assert check_unbundling(items, [make_pair(data_source="  ")]) == []
    assert check_unbundling(items, [BundlePair("93000", "93005", "0", "x", None)]) == []
    assert check_unbundling(items, [make_pair(code_2="93005; drop")]) == []
    assert check_unbundling(items, [make_pair(code_1="FRAUD")]) == []
    assert check_unbundling(items, [make_pair(code_1="93000", code_2="93000")]) == []


@pytest.mark.parametrize("system, flagged", [("CPT", True), ("HCPCS", True), (None, True), ("REV", False), ("DRG", False)])
def test_only_cpt_hcpcs_or_unspecified_systems_are_used(system, flagged):  # TU6
    items = [make_item(id="p", code="93000", code_system=system), make_item(id="s", code="93005", code_system=system)]
    assert bool(check_unbundling(items, [make_pair()])) is flagged


def test_every_code_2_line_is_flagged_and_identical_pairs_collapse():  # TU7
    items = [primary(), make_item(id="s1", code="93005"), make_item(id="s2", code="93005")]
    flags = check_unbundling(items, [make_pair(), make_pair()])
    assert ids(flags) == ["s1", "s2"]


def test_two_primaries_still_give_one_flag_per_secondary():
    items = [make_item(id="p1", code="93000"), make_item(id="p2", code="93000"), secondary()]
    assert ids(check_unbundling(items, [make_pair()])) == ["s"]


def test_two_pairs_hitting_one_line_give_two_flags_with_different_basis():  # TU8
    items = [primary(), make_item(id="q", code="93001"), secondary()]
    pairs = [make_pair(code_1="93000"), make_pair(code_1="93001")]
    flags = check_unbundling(items, pairs)
    assert ids(flags) == ["s", "s"]
    assert len({f.basis for f in flags}) == 2


def test_flag_text_names_codes_and_has_no_banned_words_or_bill_text():  # TU9
    items = [primary(description="say fraud @@"), secondary(description="@@ illegal")]
    flag = check_unbundling(items, [make_pair()])[0]
    text = (flag.reason + flag.basis).lower()
    assert not any(word in text for word in constants.BANNED_WORDS)
    assert "@@" not in text


def test_conflicting_pairs_for_the_same_codes():  # TU10
    items = [primary(), secondary()]
    newest_wins = [make_pair(modifier_indicator="0", data_year=2000), make_pair(modifier_indicator="1", data_year=2001)]
    assert [f.severity for f in check_unbundling(items, newest_wins)] == ["low"]
    tie = [make_pair(modifier_indicator="0"), make_pair(modifier_indicator="1")]
    assert check_unbundling(items, tie) == []  # ambiguous: stay silent


def test_codes_match_after_cleaning_case_and_spaces():
    items = [make_item(id="p", code=" 93000 "), make_item(id="s", code="93005")]
    assert ids(check_unbundling(items, [make_pair(code_1="93000", code_2="93005")])) == ["s"]


def test_engine_adds_unbundling_flags_when_pairs_are_supplied():
    items = [primary(), secondary()]
    assert analyze(items, []) == []
    flags = analyze(items, [], bundle_pairs=[make_pair()])
    assert [(f.line_item_id, f.flag_type) for f in flags] == [("s", "possible_unbundling")]


def test_pair_order_does_not_change_output():
    items = [primary(), make_item(id="q", code="93001"), secondary()]
    pairs = [make_pair(code_1="93000"), make_pair(code_1="93001")]
    assert analyze(items, [], bundle_pairs=pairs) == analyze(items, [], bundle_pairs=list(reversed(pairs)))
