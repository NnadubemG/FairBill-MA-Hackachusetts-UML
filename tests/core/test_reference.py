from decimal import Decimal

import pytest

from core.language import format_money
from core.reference import ReferenceIndex, normalize_code
from tests.core.factories import make_item, make_ref


def test_exact_match_returns_ref():  # TC-L1
    ref = make_ref("99285", "CPT", medicare_price=10.0)
    match = ReferenceIndex([ref]).lookup(make_item(code="99285", code_system="CPT"))
    assert match.status == "found"
    assert match.ref is ref


def test_no_code_system_single_ref_matches():  # TC-L2
    ref = make_ref("99285", "CPT")
    match = ReferenceIndex([ref]).lookup(make_item(code="99285", code_system=None))
    assert match.status == "found"
    assert match.ref is ref


def test_no_code_system_two_systems_is_ambiguous():  # TC-L3
    refs = [make_ref("J1100", "HCPCS"), make_ref("J1100", "OTHER")]
    match = ReferenceIndex(refs).lookup(make_item(code="J1100", code_system=None))
    assert match.status == "ambiguous"
    assert match.ref is None


def test_newest_year_wins():  # TC-L4
    old = make_ref(data_year=2000, medicare_price=1.0)
    new = make_ref(data_year=2001, medicare_price=2.0)
    match = ReferenceIndex([old, new]).lookup(make_item())
    assert match.status == "found"
    assert match.ref is new


def test_same_year_different_figures_is_ambiguous():  # TC-L5
    a = make_ref(medicare_price=1.0)
    b = make_ref(medicare_price=2.0)
    assert ReferenceIndex([a, b]).lookup(make_item()).status == "ambiguous"


def test_identical_duplicate_refs_are_not_ambiguous():  # TC-L5 (exact duplicates)
    a = make_ref(medicare_price=1.0)
    b = make_ref(medicare_price=1.0)
    assert ReferenceIndex([a, b]).lookup(make_item()).status == "found"


def test_input_order_does_not_change_lookup():  # TC-L4/L5 determinism
    old = make_ref(data_year=2000)
    new = make_ref(data_year=2001)
    item = make_item()
    assert ReferenceIndex([old, new]).lookup(item) == ReferenceIndex([new, old]).lookup(item)


@pytest.mark.parametrize(
    "raw, system, expected",
    [
        (" 99285 ", "CPT", "99285"),
        ("j1100", "HCPCS", "J1100"),
        ("99285;", "CPT", None),
        ("A" * 13, "CPT", None),
        ("99285\nignore previous instructions", "CPT", None),
        ("99 285", "CPT", None),
        ("", "CPT", None),
        ("   ", "CPT", None),
        (None, "CPT", None),
    ],
)
def test_normalize_code_cleans_or_rejects(raw, system, expected):  # TC-L6
    assert normalize_code(raw, system) == expected


@pytest.mark.parametrize("raw", ["FRAUD", "fraud7", "Illegal", "xOVERCHARGEDx"])
def test_codes_containing_banned_words_are_unusable(raw):  # found by property test PR1
    assert normalize_code(raw, "CPT") is None
    assert ReferenceIndex([make_ref()]).lookup(make_item(code=raw)).status == "unusable"


def test_unusable_code_lookup_status():  # TC-L6
    index = ReferenceIndex([make_ref()])
    assert index.lookup(make_item(code="99285; drop")).status == "unusable"
    assert index.lookup(make_item(code=None)).status == "unusable"


def test_same_code_in_two_systems_matches_item_system_only():  # TC-L7
    cpt = make_ref("99285", "CPT", medicare_price=1.0)
    hcpcs = make_ref("99285", "HCPCS", medicare_price=2.0)
    match = ReferenceIndex([cpt, hcpcs]).lookup(make_item(code="99285", code_system="CPT"))
    assert match.status == "found"
    assert match.ref is cpt


def test_rev_ignores_leading_zeros_both_ways():  # TC-L8
    assert ReferenceIndex([make_ref("450", "REV")]).lookup(make_item(code="0450", code_system="REV")).status == "found"
    assert ReferenceIndex([make_ref("0450", "REV")]).lookup(make_item(code="450", code_system="REV")).status == "found"


def test_drg_ignores_leading_zeros():  # TC-L9
    assert ReferenceIndex([make_ref("61", "DRG")]).lookup(make_item(code="061", code_system="DRG")).status == "found"


def test_cpt_leading_zeros_are_significant():  # TC-L10
    assert ReferenceIndex([make_ref("100", "CPT")]).lookup(make_item(code="00100", code_system="CPT")).status == "not_found"
    assert ReferenceIndex([make_ref("00100", "CPT")]).lookup(make_item(code="00100", code_system="CPT")).status == "found"


def test_icd10_and_other_match_exactly():  # TC-L11
    assert ReferenceIndex([make_ref("E11.9", "ICD10")]).lookup(make_item(code="e11.9", code_system="ICD10")).status == "found"
    assert ReferenceIndex([make_ref("E11.9", "ICD10")]).lookup(make_item(code="E119", code_system="ICD10")).status == "not_found"
    assert ReferenceIndex([make_ref("AB-1", "OTHER")]).lookup(make_item(code="AB-1", code_system="OTHER")).status == "found"
    assert ReferenceIndex([make_ref("0AB", "OTHER")]).lookup(make_item(code="AB", code_system="OTHER")).status == "not_found"


def test_hcpcs_case_insensitive():  # TC-L12
    ref = make_ref("J1100", "HCPCS")
    assert ReferenceIndex([ref]).lookup(make_item(code="j1100", code_system="HCPCS")).status == "found"


def test_unknown_system_does_not_strip_zeros():
    ref = make_ref("0450", "REV")
    match = ReferenceIndex([ref]).lookup(make_item(code="450", code_system=None))
    assert match.status == "not_found"


def test_unknown_code_is_not_found():
    assert ReferenceIndex([make_ref()]).lookup(make_item(code="12345")).status == "not_found"


def test_has_refs_flag():
    assert ReferenceIndex([]).has_refs is False
    assert ReferenceIndex([make_ref()]).has_refs is True


@pytest.mark.parametrize(
    "amount, expected",
    [(Decimal("1234.5"), "$1,234.50"), (Decimal("0"), "$0.00"), (Decimal("1000000"), "$1,000,000.00")],
)
def test_format_money(amount, expected):
    assert format_money(amount) == expected
