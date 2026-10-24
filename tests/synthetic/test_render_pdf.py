import dataclasses
import re
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from synthetic import SCENARIOS, generate_bill
from synthetic.render import LINES_PER_PAGE, STYLES, render_pdf


def structure(pdf: bytes):
    """Parse the cross-reference table. Returns {object number: offset}."""
    start = int(re.search(rb"startxref\n(\d+)\n%%EOF\n$", pdf).group(1))
    assert pdf[start:].startswith(b"xref\n")
    header = re.match(rb"xref\n0 (\d+)\n", pdf[start:])
    count = int(header.group(1))
    table = pdf[start + header.end() : start + header.end() + 20 * count]
    entries = [table[i * 20 : (i + 1) * 20] for i in range(count)]
    assert all(len(e) == 20 and e.endswith(b" \n") for e in entries)
    return {n: int(entries[n][:10]) for n in range(1, count)}


def test_pdf_is_structurally_valid():  # TS-R4
    for scenario in SCENARIOS:
        for style in STYLES:
            pdf = render_pdf(generate_bill(2, scenario), style)
            assert pdf.startswith(b"%PDF-")
            assert pdf.rstrip().endswith(b"%%EOF")
            for number, offset in structure(pdf).items():
                assert pdf[offset:].startswith(f"{number} 0 obj\n".encode())


def test_stream_lengths_are_correct():  # TS-R4
    pdf = render_pdf(generate_bill(4, "mixed"), "messy")
    streams = re.findall(rb"/Length (\d+) >>\nstream\n(.*?)\nendstream", pdf, re.DOTALL)
    assert streams
    for length, content in streams:
        assert int(length) == len(content)


def test_pdf_contains_every_code_and_amount():  # TS-R5
    for scenario in SCENARIOS:
        bill = generate_bill(3, scenario)
        pdf = render_pdf(bill, "plain")
        for item in bill.line_items:
            if item.code is not None:  # a no_code line prints a blank code column
                assert item.code.encode() in pdf
            assert f"${Decimal(str(item.billed_amount)):,.2f}".encode() in pdf


def test_special_characters_are_escaped():  # TS-R5
    bill = generate_bill(1, "clean")
    first = dataclasses.replace(bill.line_items[0], raw_description=r"TEST (A) \ B")
    bill = dataclasses.replace(bill, line_items=[first] + bill.line_items[1:])
    pdf = render_pdf(bill)
    assert rb"TEST \(A\) \\ B" in pdf
    structure(pdf)  # still parses


def test_long_bills_use_multiple_pages_and_output_is_deterministic():  # TS-R6
    bill = generate_bill(1, "clean")
    many = [dataclasses.replace(bill.line_items[0], id=str(n)) for n in range(1, 71)]
    bill = dataclasses.replace(bill, line_items=many)
    pdf = render_pdf(bill)
    pages = len(re.findall(rb"/Type /Page(?!s)", pdf))
    assert pages > 1
    assert f"/Count {pages}".encode() in pdf
    assert pdf == render_pdf(bill)
    structure(pdf)


def test_short_bill_is_one_page():
    pdf = render_pdf(generate_bill(1, "clean"))
    assert len(re.findall(rb"/Type /Page(?!s)", pdf)) == 1
    assert LINES_PER_PAGE == 55


def test_non_latin1_text_becomes_question_marks():  # TS-R7
    bill = generate_bill(1, "clean")
    first = dataclasses.replace(bill.line_items[0], raw_description="Caf\u00e9 \u60a3\u8005 \x00\n\r")
    bill = dataclasses.replace(bill, line_items=[first] + bill.line_items[1:])
    pdf = render_pdf(bill)
    assert b"??" in pdf
    structure(pdf)


@settings(max_examples=100, deadline=None)
@given(st.integers(min_value=0, max_value=10_000), st.sampled_from(SCENARIOS), st.sampled_from(STYLES))
def test_ps5_rendering_is_deterministic_and_leaves_the_bill_alone(seed, scenario, style):
    bill = generate_bill(seed, scenario)
    snapshot = generate_bill(seed, scenario)
    assert render_pdf(bill, style) == render_pdf(bill, style)
    assert bill == snapshot
