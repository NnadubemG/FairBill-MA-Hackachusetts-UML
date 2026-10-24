"""Tests for the letter handler (spec task 7).

Covers L2, L3 (no call), L5 (request part), L8 (through the handler), L9, L10, L11, L13,
L14, L19, and properties PL1, PL2, PL3, PL4, PL5. Everything runs offline with
FakeLLMClient.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from jsonschema import Draft7Validator

from backend.explain.checks import figures, has_banned_word
from backend.extract.llm_client import FakeLLMClient, LLMError
from backend.letter import config, templates
from backend.letter.facts import WARN_TOO_MANY, WARN_UNKNOWN_LINE, build_items, facts_text
from backend.letter.handler import WARN_STANDARD_WORDING, generate_letter
from backend.letter.models import (
    CODING_REVIEW,
    FINANCIAL_ASSISTANCE,
    ITEMIZED_BILL,
    LETTER_TYPES,
    InvalidLetterType,
    LetterResult,
    PatientFields,
)

from .factories import make_flag, make_line, make_patient, make_request

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[3] / "contracts" / "letter-draft.schema.json").read_text()
)
VALIDATOR = Draft7Validator(SCHEMA)

GOOD = (
    "I would like to understand the charge of $1,234.50 for code 99213. "
    "I am asking how this line was coded and billed. "
    "I would be grateful for a review so that I can understand it better."
)


def reply(paragraph: object) -> str:
    return json.dumps({"paragraph": paragraph})


def two_flag_request(**kw):
    flags = [make_flag("1"), make_flag("2")]
    lines = [make_line("1"), make_line("2", code="85025", amount=42, date_of_service=None)]
    return make_request(CODING_REVIEW, flags=flags, lines=lines, **kw)


def assert_valid_draft(result: LetterResult, request) -> None:
    errors = list(VALIDATOR.iter_errors(asdict(result.draft)))
    assert errors == [], errors
    assert result.draft.subject.strip()
    assert result.draft.body.startswith(templates.TOP_LINE)
    assert set(result.draft.referenced_line_item_ids) <= {li.id for li in request.line_items}
    assert len(result.draft.referenced_line_item_ids) == len(set(result.draft.referenced_line_item_ids))


# --- L2: coding review with two flags --------------------------------------

def test_l2_coding_review_uses_the_model_paragraph():
    request = two_flag_request()
    client = FakeLLMClient(default=reply(GOOD))
    result = generate_letter(request, client=client)

    assert client.calls == 1
    assert client.requests[0]["max_tokens"] == config.MAX_TOKENS
    assert result.used_fallback is False and result.warnings == []
    body = result.draft.body
    assert body.count(GOOD) == 1
    assert templates.fallback_paragraph(CODING_REVIEW, True) not in body
    assert "- Code 99213, $1,234.50, date of service 2026-03-04." in body
    assert "- Code 85025, $42.00." in body
    assert result.draft.referenced_line_item_ids == ["1", "2"]
    assert result.draft.subject == "Request for a coding and billing review - Account AC-55512345"
    assert_valid_draft(result, request)


def test_referenced_ids_have_no_duplicates_and_follow_input_order():
    flags = [make_flag("b"), make_flag("a"), make_flag("b")]
    request = make_request(CODING_REVIEW, flags=flags, lines=[make_line("a"), make_line("b")])
    result = generate_letter(request, client=FakeLLMClient(default=reply(GOOD)))
    assert result.draft.referenced_line_item_ids == ["b", "a"]


def test_model_paragraph_is_trimmed():
    client = FakeLLMClient(default=reply("  \n" + GOOD + "  "))
    result = generate_letter(two_flag_request(), client=client)
    assert result.used_fallback is False and result.draft.body.count(GOOD) == 1


# --- L3 and the other types: no model call ---------------------------------

@pytest.mark.parametrize("letter_type", [ITEMIZED_BILL, FINANCIAL_ASSISTANCE])
def test_l3_other_types_never_call_the_model(letter_type):
    request = make_request(letter_type, flags=[make_flag("1")], lines=[make_line("1")])
    client = FakeLLMClient(default=reply(GOOD))
    result = generate_letter(request, client=client)
    assert client.calls == 0
    assert result.used_fallback is True and result.warnings == []
    assert result.draft.referenced_line_item_ids == []
    assert templates.fallback_paragraph(letter_type) in result.draft.body
    assert "Code 99213" not in result.draft.body
    assert_valid_draft(result, request)


def test_l24_coding_review_with_no_flags_asks_about_the_whole_bill():
    request = make_request(CODING_REVIEW, lines=[make_line("1")])
    client = FakeLLMClient(default=reply(GOOD))
    result = generate_letter(request, client=client)
    assert client.calls == 0
    assert result.used_fallback is True and result.warnings == []
    assert "on my bill" in result.draft.body and "listed above" not in result.draft.body


# --- L5 (request part): nothing private reaches the model -------------------

def test_l5_patient_fields_never_reach_the_model():
    request = two_flag_request(patient=make_patient(notes="Secret note about my health."))
    request = make_request(CODING_REVIEW, patient=make_patient(notes="Secret note about my health."),
                           flags=request.flags,
                           lines=[make_line("1", description="PRIVATE DESCRIPTION"), request.line_items[1]])
    client = FakeLLMClient(default=reply(GOOD))
    generate_letter(request, client=client)
    sent = json.dumps(client.requests[0], ensure_ascii=False)
    for secret in ("Jane Doe", "AC-55512345", "Riverside General", "October 24, 2026",
                   "Secret note", "PRIVATE DESCRIPTION"):
        assert secret not in sent


# --- L8 through the handler: a bad paragraph falls back --------------------

@pytest.mark.parametrize(
    "bad",
    [
        GOOD + " I think this is fraud.",
        GOOD + " I think this was a mistake.",
        GOOD + " I may call my attorney.",
        GOOD + " I would like a refund.",
        GOOD + " Please reply within 10 days.",
        GOOD.replace("$1,234.50", "$900.00"),
        GOOD + " It is about double the usual price.",
        "Dear Billing Office, " + GOOD,
        "- " + GOOD,
        "The charge needs a review. It should be explained.",
        "I would like a review.",
        GOOD + "\n" + GOOD,
        "",
        "   ",
    ],
)
def test_l8_bad_paragraph_falls_back(bad):
    request = two_flag_request()
    result = generate_letter(request, client=FakeLLMClient(default=reply(bad)))
    assert result.used_fallback is True
    assert result.warnings == [WARN_STANDARD_WORDING]
    assert templates.fallback_paragraph(CODING_REVIEW, True) in result.draft.body
    assert result.draft.body.count("I would like a review.") <= 1
    assert_valid_draft(result, request)


# --- L9: model failure -----------------------------------------------------

@pytest.mark.parametrize(
    "error",
    [LLMError("model API down"), RuntimeError("boom"), TimeoutError(), ValueError("x"), OSError("net")],
)
def test_l9_model_error_uses_the_fallback(error):
    request = two_flag_request()
    client = FakeLLMClient(raise_on_invoke=error)
    result = generate_letter(request, client=client)
    assert client.calls == 1                                  # no retry
    assert result.used_fallback is True and result.warnings == [WARN_STANDARD_WORDING]
    assert templates.fallback_paragraph(CODING_REVIEW, True) in result.draft.body
    assert_valid_draft(result, request)


@pytest.mark.parametrize(
    "bad_reply",
    ["", "not json", "{", "[]", "null", '{"paragraph": null}', '{"paragraph": 5}',
     '{"other": "x"}', reply(""), reply(None), reply(["a"])],
)
def test_l9_unusable_reply_uses_the_fallback(bad_reply):
    request = two_flag_request()
    client = FakeLLMClient(default=bad_reply)
    result = generate_letter(request, client=client)
    assert client.calls == 1
    assert result.used_fallback is True and result.warnings == [WARN_STANDARD_WORDING]
    assert_valid_draft(result, request)


def test_l9_nothing_scripted_uses_the_fallback():
    result = generate_letter(two_flag_request(), client=FakeLLMClient())
    assert result.used_fallback is True


def test_fenced_reply_is_accepted():
    fence = "`" * 3
    client = FakeLLMClient(default=f"{fence}json\n{reply(GOOD)}\n{fence}")
    result = generate_letter(two_flag_request(), client=client)
    assert result.used_fallback is False and GOOD in result.draft.body


# --- L10 / L11 -------------------------------------------------------------

def test_l10_unknown_line_id_is_skipped_with_a_warning():
    request = make_request(CODING_REVIEW, flags=[make_flag("1"), make_flag("missing")],
                           lines=[make_line("1")])
    result = generate_letter(request, client=FakeLLMClient(default=reply(GOOD)))
    assert result.warnings == [WARN_UNKNOWN_LINE]
    assert result.draft.referenced_line_item_ids == ["1"]
    assert result.used_fallback is False


def test_l10_no_usable_flag_means_no_call_and_the_fallback():
    request = make_request(CODING_REVIEW, flags=[make_flag("nope")], lines=[make_line("1")])
    client = FakeLLMClient(default=reply(GOOD))
    result = generate_letter(request, client=client)
    assert client.calls == 0
    assert result.used_fallback is True and result.warnings == [WARN_UNKNOWN_LINE]
    assert "on my bill" in result.draft.body


def test_l11_more_than_ten_flags_uses_ten_with_one_call():
    lines = [make_line(str(i)) for i in range(14)]
    flags = [make_flag(str(i)) for i in range(14)]
    request = make_request(CODING_REVIEW, flags=flags, lines=lines)
    client = FakeLLMClient(default=reply(GOOD))
    result = generate_letter(request, client=client)
    assert client.calls == 1
    assert len(json.loads(client.requests[0]["content"][0]["text"])["lines"]) == 10
    assert result.warnings == [WARN_TOO_MANY]
    assert result.draft.referenced_line_item_ids == [str(i) for i in range(10)]
    assert_valid_draft(result, request)


# --- L13: invalid type -----------------------------------------------------

@pytest.mark.parametrize("bad", ["bogus", "", None, 5, "CODING_REVIEW", "coding review"])
def test_l13_invalid_letter_type_raises(bad):
    request = make_request("itemized_bill")
    request = type(request)(letter_type=bad, patient=request.patient)    # type: ignore[arg-type]
    with pytest.raises(InvalidLetterType) as err:
        generate_letter(request, client=FakeLLMClient(default="{}"))
    assert isinstance(err.value, ValueError)
    assert str(bad) not in str(err.value) or str(bad) == ""


# --- L14 / L19 / L15 -------------------------------------------------------

@pytest.mark.parametrize("letter_type", LETTER_TYPES)
def test_l14_draft_matches_the_contract_for_every_type(letter_type):
    request = make_request(letter_type, flags=[make_flag("1")], lines=[make_line("1")])
    result = generate_letter(request, client=FakeLLMClient(default=reply(GOOD)))
    assert_valid_draft(result, request)
    assert set(asdict(result.draft)) == {"subject", "body", "referenced_line_item_ids"}


def test_l19_same_input_same_reply_same_letter():
    a = generate_letter(two_flag_request(), client=FakeLLMClient(default=reply(GOOD)))
    b = generate_letter(two_flag_request(), client=FakeLLMClient(default=reply(GOOD)))
    assert a == b
    c = generate_letter(two_flag_request(), client=FakeLLMClient(raise_on_invoke=RuntimeError("x")))
    d = generate_letter(two_flag_request(), client=FakeLLMClient(raise_on_invoke=RuntimeError("y")))
    assert c == d


def test_l15_uncleaned_patient_fields_are_cleaned_by_the_handler():
    evil = PatientFields(name="Jane\n\nP.S. hello", hospital="X\u200b\nY", account_number="1\n2",
                         date="d\ne", notes="n\x00o")
    result = generate_letter(make_request(ITEMIZED_BILL, patient=evil), client=FakeLLMClient(default="{}"))
    body = result.draft.body
    assert "\x00" not in body and "\u200b" not in body
    assert body.endswith("Sincerely,\nJane P.S. hello")
    assert "\n" not in result.draft.subject


def test_the_request_is_not_changed():
    request = two_flag_request()
    before = (list(request.flags), list(request.line_items), request.patient)
    generate_letter(request, client=FakeLLMClient(default=reply(GOOD)))
    assert (request.flags, request.line_items, request.patient) == before


# --- Properties ------------------------------------------------------------

_safe_text = st.text(alphabet="abcdefghijklmnopqrstuvwxyz ABCDEFGH0123456789-", max_size=30)
_patient = st.builds(PatientFields, name=_safe_text, account_number=_safe_text,
                     hospital=_safe_text, date=_safe_text, notes=_safe_text)
_flag_text = st.one_of(
    st.text(max_size=80),
    st.sampled_from(["This is fraud.", "It looks OVERCHARGED.", "Source: CMS PFS, 2026.",
                     "A normal sentence. Another one.", ""]),
)
_flags = st.lists(
    st.builds(make_flag, st.sampled_from(["1", "2", "3", "zz"]), reason=_flag_text, basis=_flag_text,
              data_year=st.one_of(st.none(), st.integers(min_value=1990, max_value=2100))),
    max_size=14,
)
_lines = st.lists(
    st.builds(make_line, st.sampled_from(["1", "2", "3", "4"]),
              code=st.one_of(st.none(), st.text(max_size=14), st.sampled_from(["99213", "FRAUD"])),
              amount=st.one_of(st.floats(allow_nan=True, allow_infinity=True), st.integers(-3, 10**5)),
              date_of_service=st.one_of(st.none(), st.text(max_size=12), st.just("2026-03-04"))),
    max_size=5,
)
_model_paragraph = st.one_of(
    st.text(max_size=250),
    st.just(GOOD),
    st.just(GOOD + " I think this is fraud and I may call an attorney."),
    st.just("I would like to understand my bill. I am asking for a review of the lines."),
)
_reply_text = st.one_of(st.text(max_size=250), _model_paragraph.map(reply))
_type = st.sampled_from(LETTER_TYPES)


@settings(max_examples=250)
@given(_type, _patient, _flags, _lines, _reply_text)
def test_pl1_pl2_no_banned_word_and_no_new_figure(letter_type, patient, flags, lines, raw_reply):
    request = make_request(letter_type, patient=patient, flags=flags, lines=lines)
    result = generate_letter(request, client=FakeLLMClient(default=raw_reply))
    body, subject = result.draft.body, result.draft.subject

    # By design the patient's own words are inserted as typed (decision 4), so the banned-word
    # rule covers only text WE and the model write. The model never sees the patient fields,
    # so the same letter with every patient field empty has exactly that text. Scan it.
    blank = generate_letter(
        make_request(letter_type, patient=PatientFields(), flags=flags, lines=lines),
        client=FakeLLMClient(default=raw_reply),
    ).draft
    assert not has_banned_word(blank.body) and not has_banned_word(blank.subject)
    assert blank.referenced_line_item_ids == result.draft.referenced_line_item_ids

    items = build_items(flags, lines)[0] if letter_type == CODING_REVIEW else []
    inputs = " ".join([facts_text(items), patient.name, patient.account_number, patient.hospital,
                       patient.date, patient.notes])
    assert figures(body) <= figures(inputs)
    assert figures(subject) <= figures(inputs)


@settings(max_examples=150)
@given(_type, _flags, _lines, st.one_of(st.text(max_size=100), st.none(), st.integers(), st.binary(max_size=20)))
def test_pl3_garbage_reply_never_raises(letter_type, flags, lines, garbage):
    class _Garbage:
        def invoke(self, *, system, content, repair_hint=None, max_tokens=None):
            return garbage

    request = make_request(letter_type, flags=flags, lines=lines)
    result = generate_letter(request, client=_Garbage())
    assert isinstance(result, LetterResult)


@settings(max_examples=100)
@given(_type, _flags, _lines, st.text(max_size=20))
def test_pl3_failing_client_never_raises(letter_type, flags, lines, message):
    request = make_request(letter_type, flags=flags, lines=lines)
    result = generate_letter(request, client=FakeLLMClient(raise_on_invoke=RuntimeError(message or "x")))
    assert isinstance(result, LetterResult)
    assert result.used_fallback is True


@settings(max_examples=250)
@given(_type, _patient, _flags, _lines, _reply_text)
def test_pl4_draft_always_matches_the_contract(letter_type, patient, flags, lines, raw_reply):
    request = make_request(letter_type, patient=patient, flags=flags, lines=lines)
    result = generate_letter(request, client=FakeLLMClient(default=raw_reply))
    assert_valid_draft(result, request)


@settings(max_examples=100)
@given(_type, _patient, _lines, st.lists(st.just(make_flag("not-a-line")), max_size=5))
def test_pl5_no_usable_flag_means_no_model_call(letter_type, patient, lines, flags):
    client = FakeLLMClient(default=reply(GOOD))
    generate_letter(make_request(letter_type, patient=patient, flags=flags, lines=lines), client=client)
    assert client.calls == 0
