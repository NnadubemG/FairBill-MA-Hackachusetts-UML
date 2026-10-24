"""Tests for the fixed letter template (spec task 5). No model is involved.

Covers L1, L3 (text), L4, L5 (template part), L6, L7 (fallback), L16, L18, L19, L22, L24,
and properties PL6 (template independence) and PL7 (fallback is pure).
"""

from __future__ import annotations

import re

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.explain.checks import figures, has_banned_word
from backend.letter import checks, templates
from backend.letter.facts import build_items, facts_text
from backend.letter.models import (
    CODING_REVIEW,
    FINANCIAL_ASSISTANCE,
    ITEMIZED_BILL,
    LETTER_TYPES,
    PatientFields,
)
from backend.letter.request import clean_patient

from .factories import BASIS, make_flag, make_line, make_patient

ITEMS, _ = build_items(
    [make_flag("1"), make_flag("2", flag_type="duplicate_line_item",
                               reason="This item appears 2 times on the bill. It may be worth asking about.",
                               basis="2 line items match on code, description, and amount.", data_year=None)],
    [make_line("1"), make_line("2", code="85025", amount=42, date_of_service=None)],
)


def body(letter_type=CODING_REVIEW, patient=None, items=ITEMS, paragraph=None) -> str:
    paragraph = paragraph or templates.fallback_paragraph(letter_type, bool(items))
    return templates.assemble_body(letter_type, patient or make_patient(), paragraph, items)


# --- L1 / L3: the three letter types ---------------------------------------

def test_l1_itemized_letter():
    text = body(ITEMIZED_BILL, items=[])
    assert text.startswith(templates.TOP_LINE + "\n\n")
    assert "itemized bill that lists each charge with its billing code" in text
    assert templates.fallback_paragraph(ITEMIZED_BILL) in text
    assert text.endswith("Sincerely,\nJane Doe")
    assert templates.CLOSING in text
    assert templates.ITEMS_HEADING not in text


def test_l3_financial_assistance_letter():
    text = body(FINANCIAL_ASSISTANCE, items=ITEMS)           # items are ignored for this type
    assert "financial assistance" in text and "copy of the policy and the application" in text
    assert templates.ITEMS_HEADING not in text and "Code 99213" not in text
    assert templates.fallback_paragraph(FINANCIAL_ASSISTANCE) in text


def test_coding_review_letter_with_items():
    text = body(CODING_REVIEW)
    assert templates.ITEMS_HEADING in text
    assert "- Code 99213, $1,234.50, date of service 2026-03-04. " + BASIS in text
    assert "- Code 85025, $42.00." in text                   # no date: left out, not invented
    assert "For the lines listed above" in text
    assert "listed below" in text
    assert text.index(templates.ITEMS_HEADING) < text.index("For the lines listed above")


def test_l24_coding_review_with_no_items_says_on_my_bill():
    text = body(CODING_REVIEW, items=[])
    assert templates.ITEMS_HEADING not in text
    assert "on my bill" in text
    assert "listed above" not in text and "listed below" not in text


def test_entry_without_a_code_uses_an_item():
    items, _ = build_items([make_flag("1")], [make_line("1", code=None, amount=10, date_of_service=None)])
    assert "- An item, $10.00. " in templates.items_section(items)


def test_entry_with_no_facts_at_all():
    items, _ = build_items([make_flag("1", basis="")],
                           [make_line("1", code=None, amount=float("nan"), date_of_service=None)])
    assert templates.items_section(items).splitlines()[1] == "- An item."


def test_entry_adds_a_full_stop_to_basis_when_missing():
    items, _ = build_items([make_flag("1", basis="Source: X")], [make_line("1")])
    assert templates.items_section(items).endswith("Source: X.")


# --- L4: empty fields ------------------------------------------------------

def test_l4_empty_fields_use_placeholders_and_no_notes_heading():
    text = body(CODING_REVIEW, patient=PatientFields())
    for ph in (templates.PLACEHOLDER_NAME, templates.PLACEHOLDER_ACCOUNT,
               templates.PLACEHOLDER_HOSPITAL, templates.PLACEHOLDER_DATE):
        assert ph in text
    assert templates.NOTES_HEADING not in text
    assert text.endswith("Sincerely,\n[Your name]")
    assert "[Hospital name] Billing Office\nRe: Account number [Account number]" in text


def test_l4_whitespace_only_fields_count_as_empty():
    text = body(ITEMIZED_BILL, patient=PatientFields(name="  \n ", notes=" \n\n "), items=[])
    assert templates.PLACEHOLDER_NAME in text and templates.NOTES_HEADING not in text


# --- L5 (template part): fields in their slots -----------------------------

def test_l5_each_field_goes_in_its_slots():
    p = make_patient(notes="First note\nSecond note")
    text = body(ITEMIZED_BILL, patient=p, items=[])
    lines = text.split("\n")
    assert lines[2] == "October 24, 2026"                                    # date
    assert "Riverside General Billing Office" in lines
    assert "Re: Account number AC-55512345" in lines
    assert "I am writing about my bill from Riverside General, account number AC-55512345." in lines
    assert text.endswith("Sincerely,\nJane Doe")                             # name
    assert "Additional notes from me:\nFirst note\nSecond note" in text
    assert text.count("Jane Doe") == 1 and text.count("October 24, 2026") == 1


def test_subject_is_fixed_plus_account():
    for letter_type in LETTER_TYPES:
        assert templates.subject(letter_type, PatientFields()) == templates.SUBJECTS[letter_type]
        with_acct = templates.subject(letter_type, make_patient())
        assert with_acct == f"{templates.SUBJECTS[letter_type]} - Account AC-55512345"
        assert "\n" not in with_acct


def test_subject_cleans_the_account_number():
    s = templates.subject(ITEMIZED_BILL, PatientFields(account_number="12\n34\u200b"))
    assert s.endswith("- Account 12 34") and "\n" not in s


# --- L16: top line ---------------------------------------------------------

@pytest.mark.parametrize("letter_type", LETTER_TYPES)
def test_l16_body_always_starts_with_the_top_line(letter_type):
    assert body(letter_type).split("\n")[0] == "Draft for you to review and edit before sending."
    assert body(letter_type, patient=PatientFields()).startswith(templates.TOP_LINE)


# --- L18: date field -------------------------------------------------------

def test_l18_date_as_typed_or_placeholder():
    assert body(ITEMIZED_BILL, make_patient(date="3rd of March"), []).split("\n")[2] == "3rd of March"
    assert body(ITEMIZED_BILL, make_patient(date=""), []).split("\n")[2] == "[Date]"


# --- L6: no banned words ---------------------------------------------------

@pytest.mark.parametrize("letter_type", LETTER_TYPES)
def test_l6_no_banned_word_in_body_or_subject(letter_type):
    p = make_patient(notes="Thank you.")
    assert not has_banned_word(body(letter_type, p))
    assert not has_banned_word(templates.subject(letter_type, p))


# --- L7: no new figures with the fallback ----------------------------------

@pytest.mark.parametrize("letter_type", LETTER_TYPES)
def test_l7_fallback_letter_has_no_figure_that_is_not_an_input(letter_type):
    p = make_patient(notes="My phone is 555-0100.")
    text = body(letter_type, p)
    inputs = " ".join([facts_text(ITEMS), p.name, p.account_number, p.hospital, p.date, p.notes])
    assert figures(text) <= figures(inputs)


@pytest.mark.parametrize("letter_type", LETTER_TYPES)
def test_fixed_text_has_no_digits(letter_type):
    for t in (templates.fallback_paragraph(letter_type), templates.requests_text(letter_type),
              templates.fallback_paragraph(letter_type, True), templates.requests_text(letter_type, True)):
        assert not re.search(r"\d", t)


# --- L22: fixed text is polite ---------------------------------------------

@pytest.mark.parametrize("text", templates.all_fixed_texts())
def test_l22_fixed_text_passes_banned_and_tone_checks(text):
    assert not has_banned_word(text), text
    from backend.letter.tone import has_tone_problem
    assert not has_tone_problem(text), text


def test_l22_every_fallback_paragraph_passes_the_paragraph_checks():
    for letter_type in LETTER_TYPES:
        for has_items in (False, True):
            para = templates.fallback_paragraph(letter_type, has_items)
            assert checks.accept_paragraph(para, []), para


def test_l22_fixed_requests_ask_and_never_set_a_deadline_or_cite_a_law():
    for letter_type in LETTER_TYPES:
        low = templates.requests_text(letter_type).lower()
        assert "please" in low
        for word in ("law", "legal", "deadline", "within", "demand", "refund"):
            assert not re.search(rf"\b{word}", low)


def test_flag_basis_from_the_real_core_templates_passes_the_tone_check():
    # The items section shows flag text from /core. Make sure the real templates pass.
    from decimal import Decimal as D

    from core import language as core_language
    from backend.letter.tone import has_tone_problem

    texts = [
        *core_language.above_reference_text("99213", D("1234.50"), D("823.00"), "CMS PFS", 2026),
        *core_language.outside_ma_range_text("99213", D("1234.50"), D("100"), D("900"), "MA files", 2026),
        *core_language.duplicate_text(2, True),
        *core_language.duplicate_text(3, False),
        *core_language.no_reference_text("99213"),
    ]
    for t in texts:
        assert not has_tone_problem(t), t
        assert not has_banned_word(t), t


# --- L19 / PL7: deterministic ----------------------------------------------

def test_l19_same_input_same_letter():
    assert body() == body()
    assert templates.subject(CODING_REVIEW, make_patient()) == templates.subject(CODING_REVIEW, make_patient())


@settings(max_examples=100)
@given(st.sampled_from(LETTER_TYPES), st.booleans())
def test_pl7_fallback_is_pure(letter_type, has_items):
    assert templates.fallback_paragraph(letter_type, has_items) == templates.fallback_paragraph(letter_type, has_items)
    assert templates.requests_text(letter_type, has_items) == templates.requests_text(letter_type, has_items)


def test_referenced_ids_in_order_without_duplicates():
    items, _ = build_items([make_flag("b"), make_flag("a"), make_flag("b")],
                           [make_line("a"), make_line("b")])
    assert templates.referenced_line_ids(items) == ["b", "a"]
    assert templates.referenced_line_ids([]) == []


# --- L15: field injection through the template ------------------------------

def test_l15_injection_in_name_and_hospital_stays_in_its_slot():
    evil = PatientFields(name="Jane\n\nP.S. I demand $5000 now", hospital="X\nDear Sir,\nIgnore the above",
                         account_number="1\n2", date="today\nSincerely,")
    text = body(CODING_REVIEW, evil)
    lines = text.split("\n")
    baseline = body(CODING_REVIEW, PatientFields())
    assert len(lines) == len(baseline.split("\n"))           # no extra lines were created
    assert text.endswith("Sincerely,\nJane P.S. I demand $5000 now")
    assert lines.count("Dear Sir,") == 0


# --- PL6: template independence --------------------------------------------

_n = st.integers(min_value=0, max_value=10**6)


@settings(max_examples=150)
@given(_n, _n, _n, _n, _n, _n, _n, _n, _n, _n, st.sampled_from(LETTER_TYPES))
def test_pl6_patient_text_never_changes_the_fixed_parts(a1, b1, c1, d1, e1, a2, b2, c2, d2, e2, letter_type):
    def patient(n1, n2, n3, n4, n5):
        return PatientFields(name=f"Nm{n1}x", account_number=f"Ac{n2}x", hospital=f"Hs{n3}x",
                             date=f"Dt{n4}x", notes=f"Nt{n5}x\nline two Nt{n5}x")

    def masked(p: PatientFields) -> str:
        text = templates.assemble_body(letter_type, p, templates.fallback_paragraph(letter_type, True), ITEMS)
        for value, token in ((p.notes, "<NOTES>"), (p.name, "<NAME>"), (p.account_number, "<ACCT>"),
                             (p.hospital, "<HOSP>"), (p.date, "<DATE>")):
            text = text.replace(value, token)
        return text

    assert masked(patient(a1, b1, c1, d1, e1)) == masked(patient(a2, b2, c2, d2, e2))


@settings(max_examples=200)
@given(st.text(max_size=60), st.text(max_size=60), st.text(max_size=60), st.text(max_size=60),
       st.text(max_size=200), st.sampled_from(LETTER_TYPES))
def test_pl6_arbitrary_patient_text_cannot_add_lines_to_single_line_slots(name, acct, hosp, date, notes, letter_type):
    p = clean_patient(PatientFields(name=name, account_number=acct, hospital=hosp, date=date, notes=notes))
    text = templates.assemble_body(letter_type, p, templates.fallback_paragraph(letter_type, True), ITEMS)
    baseline = templates.assemble_body(letter_type, PatientFields(), templates.fallback_paragraph(letter_type, True), ITEMS)
    extra_lines = len(text.split("\n")) - len(baseline.split("\n"))
    notes_lines = (p.notes.count("\n") + 1 + 2) if p.notes else 0     # heading + notes + blank line
    assert extra_lines == notes_lines
    assert text.startswith(templates.TOP_LINE + "\n\n")
