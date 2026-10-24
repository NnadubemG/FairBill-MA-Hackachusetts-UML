import re
from decimal import Decimal

import pytest

from synthetic import SCENARIOS, generate_bill
from synthetic.render import STYLES, render_text


def money(amount: float) -> str:
    return f"{Decimal(str(amount)):,.2f}"


def test_plain_text_contains_every_line_item():  # TS-R1
    for scenario in SCENARIOS:
        for seed in range(25):
            bill = generate_bill(seed, scenario)
            text = render_text(bill, "plain")
            for item in bill.line_items:
                if item.code is not None:  # a no_code line prints a blank code column
                    assert item.code in text
                assert f"${money(item.billed_amount)}" in text
                for word in (item.raw_description or "").split():
                    assert word in text
            assert bill.bill_metadata.hospital_name in text
            assert f"${money(bill.bill_metadata.total_billed)}" in text


def test_messy_text_changes_format_but_keeps_content():  # TS-R2
    for scenario in SCENARIOS:
        for seed in range(25):
            bill = generate_bill(seed, scenario)
            text = render_text(bill, "messy")
            assert re.search(r"\b\d\d/\d\d/\d\d\b", text)
            assert "$" not in text
            assert "ACCT STMT" in text and "PLEASE REMIT" in text
            for item in bill.line_items:
                if item.code is not None:
                    assert item.code in text
                assert money(item.billed_amount) in text
                for word in (item.raw_description or "").split():
                    assert word in text


def test_messy_dates_match_the_ground_truth_date():  # TS-R2
    bill = generate_bill(3, "clean")
    year, month, day = bill.line_items[0].date_of_service.split("-")
    assert f"{month}/{day}/{year[2:]}" in render_text(bill, "messy")
    assert bill.line_items[0].date_of_service in render_text(bill, "plain")


def test_thousands_separator_is_used():
    bill = generate_bill(0, "high_price")
    big = max(bill.line_items, key=lambda i: i.billed_amount)
    assert big.billed_amount >= 1000
    assert "," in money(big.billed_amount)
    assert money(big.billed_amount) in render_text(bill, "plain")


def test_long_descriptions_wrap_without_losing_text():
    bill = generate_bill(1, "injection")
    text = render_text(bill, "plain")
    injected = next(i for i in bill.line_items if "IGNORE PREVIOUS" in i.raw_description)
    for word in injected.raw_description.split():
        assert word in text
    assert max(len(line) for line in text.splitlines()) <= 80


def test_rendering_is_deterministic_and_does_not_change_the_bill():  # TS-R3
    bill = generate_bill(5, "mixed")
    before = generate_bill(5, "mixed")
    for style in STYLES:
        assert render_text(bill, style) == render_text(bill, style)
    assert bill == before


def test_unknown_style_raises_with_valid_names():  # TS-R3
    with pytest.raises(ValueError) as error:
        render_text(generate_bill(1, "clean"), "fancy")
    assert all(name in str(error.value) for name in STYLES)
