"""Tests for the oracle (fake model) and the invariant checks (spec task 5).

Covers X3 (the invariant checker), the oracle replies passing the REAL handlers, and the
extraction part of property PE5 over the whole corpus.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from backend.explain.handler import explain
from backend.extract.handler import extract
from backend.extract.llm_client import LLMError
from backend.letter.handler import generate_letter
from backend.letter.models import CODING_REVIEW, LetterRequest, PatientFields
from contracts.types import LetterDraft

from evals import config
from evals.corpus import build_corpus
from evals.invariants import KINDS, Violation, check_explanations, check_letter
from evals.oracle import ORACLE_LETTER_PARAGRAPH, ORACLE_QUESTION, OracleClient
from evals.score_extract import score_bill
from evals.score_flags import run_core

BILLS = build_corpus()
ORACLE = OracleClient(BILLS)


def extract_via_oracle(bill, oracle=ORACLE):
    return extract(bill.pdf, "application/pdf", client=oracle.scoped("extract", bill.file_sha256))


def flags_of(bill):
    return run_core(bill.truth.line_items, bill.truth)


def letter_request(bill, flags):
    return LetterRequest(
        letter_type=CODING_REVIEW,
        patient=PatientFields(**config.EVAL_PATIENT),
        flags=flags,
        line_items=list(bill.truth.line_items),
    )


# --- the oracle's replies pass the real handlers ---------------------------

@pytest.mark.parametrize("bill", BILLS, ids=lambda b: b.key)
def test_z1_oracle_extract_reply_is_a_perfect_extraction(bill):
    res = extract_via_oracle(bill)
    assert len(res.line_items) == len(bill.truth.line_items)
    s = score_bill(bill.bill_id, bill.style, bill.scenario, bill.truth.line_items, res)
    assert (s.counts.line_recall, s.counts.line_precision) == (1.0, 1.0), s.failures
    assert s.counts.code_exact == 1.0 and s.counts.charge_exact == 1.0
    assert s.counts.units_exact in (None, 1.0) and s.counts.date_exact in (None, 1.0)
    assert s.failures == () and s.counts.fallback_bills == 0
    assert s.counts.confirmation_recall in (None, 1.0)
    meta = bill.truth.bill_metadata
    assert (res.metadata.hospital_name, res.metadata.statement_date, res.metadata.total) == \
           (meta.hospital_name, meta.statement_date, meta.total_billed)


@pytest.mark.parametrize("bill", BILLS, ids=lambda b: b.key)
def test_z2_oracle_explain_reply_is_accepted_by_the_real_explain_gate(bill):
    flags = flags_of(bill)
    res = explain(flags, client=ORACLE.scoped("explain", bill.file_sha256))
    assert res.fallback_count == 0 and res.warnings == []
    assert all(f.explanation.endswith(ORACLE_QUESTION) for f in res.flags)
    assert check_explanations(bill.bill_id, bill.style, res.flags) == []


@pytest.mark.parametrize("bill", [b for b in BILLS if flags_of(b)], ids=lambda b: b.key)
def test_z3_oracle_letter_reply_is_accepted_by_the_real_letter_gate(bill):
    flags = flags_of(bill)
    res = generate_letter(letter_request(bill, flags), client=ORACLE.scoped("letter", bill.file_sha256))
    assert res.used_fallback is False and res.warnings == []
    assert ORACLE_LETTER_PARAGRAPH in res.draft.body
    ids = {li.id for li in bill.truth.line_items}
    assert check_letter(bill.bill_id, bill.style, res.draft, ids) == []


def test_z3_the_oracle_paragraph_is_not_the_fallback_paragraph():
    from backend.letter.templates import fallback_paragraph

    assert ORACLE_LETTER_PARAGRAPH not in {fallback_paragraph(CODING_REVIEW, True),
                                            fallback_paragraph(CODING_REVIEW, False)}


def test_z4_stats_label_and_errors():
    oracle = OracleClient(BILLS)
    b = BILLS[0]
    assert oracle.model_for("extract") == config.FAKE_MODEL_LABEL
    extract_via_oracle(b, oracle)
    assert oracle.stats.real_calls == 1 and oracle.stats.hits == 0
    with pytest.raises(LLMError):
        oracle.scoped("extract", "0" * 64).invoke(system="s", content=[])
    with pytest.raises(LLMError):
        oracle.scoped("unknown-task", b.file_sha256).invoke(system="s", content=[])
    with pytest.raises(LLMError):
        oracle.scoped("explain", b.file_sha256).invoke(system="s", content=[{"type": "text", "text": "not json"}])


def test_z4_an_unknown_file_makes_extract_use_its_fallback():
    from backend.extract.handler import WARN_EXTRACTION_UNAVAILABLE

    res = extract(b"%PDF other", "application/pdf", client=ORACLE.scoped("extract", "f" * 64))
    assert res.line_items == [] and res.warnings == [WARN_EXTRACTION_UNAVAILABLE]


def test_z5_the_extract_transform_hook_can_damage_the_reply():
    bill = next(b for b in BILLS if b.key == "mixed-1/plain")
    drop_last = OracleClient(BILLS, extract_transform=lambda b, lines: lines[:-1])
    res = extract_via_oracle(bill, drop_last)
    assert len(res.line_items) == len(bill.truth.line_items) - 1


# --- X3: the invariant checker ----------------------------------------------

def flag_with(explanation, **kw):
    from contracts.types import Flag

    base = dict(line_item_id="1", flag_type="price_above_reference", severity="medium",
                reason="The billed amount of $1,234.50 per unit may be worth asking about.",
                basis="Medicare reference price for code 99213: $823.00 per unit. Source: CMS PFS, 2026.",
                data_source="CMS PFS", data_year=2026, explanation=explanation)
    base.update(kw)
    return Flag(**base)


def kinds(violations):
    return [v.kind for v in violations]


def test_x3_a_clean_explanation_has_no_violation():
    good = "The price of $1,234.50 may be worth asking about. Can you explain how it was set?"
    assert check_explanations("b-1", "plain", [flag_with(good)]) == []


def test_x3_year_is_allowed_in_an_explanation():
    assert check_explanations("b-1", "plain", [flag_with("This is from 2026. Can you explain it?")]) == []


@pytest.mark.parametrize("missing", [None, "", "   "])
def test_x3_a_missing_explanation_is_a_violation(missing):
    assert kinds(check_explanations("b-1", "plain", [flag_with(missing)])) == ["explain_missing"]


def test_x3_banned_word_and_invented_figure_are_violations():
    assert "explain_banned_word" in kinds(check_explanations("b-1", "plain", [flag_with("This is fraud. Why?")]))
    assert "explain_figure" in kinds(check_explanations("b-1", "plain", [flag_with("It costs $5,000. Why?")]))
    both = check_explanations("b-1", "plain", [flag_with("Overcharged by $5,000. Why?")])
    assert set(kinds(both)) == {"explain_banned_word", "explain_figure"}


def good_draft():
    bill = next(b for b in BILLS if b.key == "mixed-1/plain")
    res = generate_letter(letter_request(bill, flags_of(bill)), client=ORACLE.scoped("letter", bill.file_sha256))
    return bill, res.draft


def test_x3_a_real_letter_has_no_violation():
    bill, draft = good_draft()
    assert check_letter(bill.bill_id, bill.style, draft, {li.id for li in bill.truth.line_items}) == []


def test_x3_letter_violations():
    bill, draft = good_draft()
    ids = {li.id for li in bill.truth.line_items}
    check = lambda d, i=ids: kinds(check_letter("b-1", "plain", d, i))   # noqa: E731

    assert "letter_banned_word" in check(replace(draft, body=draft.body + "\nThis is illegal."))
    assert "letter_banned_word" in check(replace(draft, subject="A fraud subject"))
    assert "letter_top_line" in check(replace(draft, body="Hello\n" + draft.body))
    assert "letter_unknown_line" in check(replace(draft, referenced_line_item_ids=["nope"]))
    assert check(replace(draft, subject=5)) == ["letter_schema"]                       # type: ignore[arg-type]
    assert "letter_schema" in check(replace(draft, referenced_line_item_ids=[1]))       # type: ignore[list-item]
    assert "letter_schema" in check(replace(draft, body=None))                          # type: ignore[arg-type]
    assert check(draft) == []


def test_x3_violations_hold_ids_and_kinds_only():
    v = check_explanations("b-1", "messy", [flag_with("Pure fraud and $9,999. Why?")])
    assert all(isinstance(x, Violation) and x.kind in KINDS for x in v)
    assert all(x.bill_id == "b-1" and x.style == "messy" for x in v)
    assert "fraud" not in repr(v).lower() and "9,999" not in repr(v)


# --- the oracle never needs a key or the network ----------------------------

def test_the_oracle_works_without_any_environment_variables(monkeypatch):
    for name in (config.ENV_API_KEY, config.ENV_EXTRACT_MODEL, config.ENV_EXPLAIN_MODEL,
                 config.ENV_LETTER_MODEL):
        monkeypatch.delenv(name, raising=False)
    bill = BILLS[0]
    assert extract_via_oracle(bill).line_items
