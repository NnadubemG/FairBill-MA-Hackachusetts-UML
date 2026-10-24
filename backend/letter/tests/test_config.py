"""Tests for letter scaffold, config and wrapper types (spec task 1)."""

from __future__ import annotations

import re

import pytest

from contracts.types import Flag as ContractFlag
from contracts.types import LetterDraft as ContractLetterDraft
from contracts.types import LineItem as ContractLineItem
from core.constants import BANNED_WORDS as CORE_BANNED_WORDS

from backend.letter import config, models
from backend.letter._contracts import Flag, LetterDraft, LineItem


def test_contract_types_are_the_real_classes():
    assert Flag is ContractFlag
    assert LineItem is ContractLineItem
    assert LetterDraft is ContractLetterDraft


def test_banned_words_match_core():
    assert tuple(config.BANNED_WORDS) == tuple(CORE_BANNED_WORDS)


def test_env_var_name():
    assert config.ENV_MODEL_ID == "LETTER_MODEL_ID"


def test_letter_type_ids():
    assert models.LETTER_TYPES == ("itemized_bill", "coding_review", "financial_assistance")


def test_limits_are_sane():
    assert config.MAX_FLAGS == 10
    assert config.MIN_SENTENCES <= config.MAX_SENTENCES
    assert config.MAX_PARAGRAPH_WORDS >= 40
    assert 0 < config.MAX_TOKENS <= 1000
    for limit in (config.MAX_NAME, config.MAX_ACCOUNT, config.MAX_HOSPITAL, config.MAX_DATE):
        assert limit > 0
    assert config.MAX_NOTES >= 200


@pytest.mark.parametrize(
    "patterns",
    [
        config.ACCUSATION_PATTERNS,
        config.LEGAL_PATTERNS,
        config.MONEY_DEMAND_PATTERNS,
        config.DEADLINE_PATTERNS,
    ],
)
def test_tone_patterns_compile_and_are_not_empty(patterns):
    assert patterns
    for p in patterns:
        re.compile(p)


@pytest.mark.parametrize(
    "text,group",
    [
        ("this looks wrong", config.ACCUSATION_PATTERNS),
        ("it was a mistake", config.ACCUSATION_PATTERNS),
        ("I will call my attorney", config.LEGAL_PATTERNS),
        ("under the law", config.LEGAL_PATTERNS),
        ("please give a refund", config.MONEY_DEMAND_PATTERNS),
        ("you owe me", config.MONEY_DEMAND_PATTERNS),
        ("reply within 10 days", config.DEADLINE_PATTERNS),
        ("I need this immediately", config.DEADLINE_PATTERNS),
    ],
)
def test_tone_patterns_catch_examples(text, group):
    assert any(re.search(p, text.lower()) for p in group)


@pytest.mark.parametrize(
    "text",
    ["I would like to understand my bill better.", "Please send the documentation.",
     "I am asking for a review.", "This is a flaw-free outlaw lawn"],   # no false hits on parts of words
)
def test_tone_patterns_leave_normal_text_alone(text):
    for group in (config.ACCUSATION_PATTERNS, config.LEGAL_PATTERNS,
                  config.MONEY_DEMAND_PATTERNS, config.DEADLINE_PATTERNS):
        assert not any(re.search(p, text.lower()) for p in group)


def test_patient_fields_default_to_empty():
    p = models.PatientFields()
    assert (p.name, p.account_number, p.hospital, p.date, p.notes) == ("", "", "", "", "")


def test_request_defaults():
    r = models.LetterRequest(letter_type="itemized_bill")
    assert r.flags == [] and r.line_items == []
    assert r.patient == models.PatientFields()


def test_result_defaults():
    r = models.LetterResult(draft=LetterDraft(subject="s", body="b"))
    assert r.used_fallback is True and r.warnings == []
    assert r.draft.referenced_line_item_ids == []


def test_invalid_letter_type_is_a_value_error():
    assert issubclass(models.InvalidLetterType, ValueError)
