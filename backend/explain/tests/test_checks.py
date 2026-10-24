"""Tests for explanation checks (spec task 2).

Covers E2 (banned word), E3/E4/E5/E6 (figures), E7 (implied figure words), E8 (sentence
shape), and properties P1 and P5 (an accepted text is always safe).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.explain import checks, config

from .factories import BASIS, GOOD_TEXT, REASON, make_flag

FLAG = make_flag()


def test_good_text_is_accepted():
    assert checks.accept(GOOD_TEXT, FLAG)


# --- E2: banned words ------------------------------------------------------

@pytest.mark.parametrize("word", list(config.BANNED_WORDS))
def test_e2_each_banned_word_rejected(word):
    text = f"This line may be worth asking about. It looks like {word} to some. Can you explain it?"
    assert checks.has_banned_word(text)
    assert not checks.accept(text, FLAG)


@pytest.mark.parametrize(
    "text",
    [
        "OVERCHARGED",
        "Fraud",
        "You   Should   Dispute this",       # extra spaces
        "you\u00a0are\u00a0owed money",      # non-breaking spaces
        "incor\u200brect charge",            # zero-width character
        "ＩＬＬＥＧＡＬ",                      # full-width letters
    ],
)
def test_e2_disguised_banned_words_caught(text):
    assert checks.has_banned_word(text)


def test_clean_text_has_no_banned_word():
    assert not checks.has_banned_word(GOOD_TEXT)


# --- E3/E4/E5/E6: figures --------------------------------------------------

def test_e3_new_figure_rejected():
    text = GOOD_TEXT.replace("$823.00", "$500.00")
    assert not checks.accept(text, FLAG)


def test_e4_changed_figure_rejected():
    text = GOOD_TEXT.replace("$1,234.50", "$1,324.50")
    assert not checks.accept(text, FLAG)


@pytest.mark.parametrize("variant", ["$1,234.50", "1234.5", "$1234.50", "1,234.5"])
def test_e5_figure_kept_in_any_format(variant):
    text = GOOD_TEXT.replace("$1,234.50", variant)
    assert checks.accept(text, FLAG)


def test_e6_year_allowed():
    text = (
        "The price may be worth asking about. "
        "The reference figure is from 2026. "
        "Can you explain how this price was set?"
    )
    assert checks.accept(text, FLAG)


def test_year_not_allowed_when_flag_has_no_year_and_source_lacks_it():
    flag = make_flag(basis="No year here.", data_year=None, data_source=None,
                     reason="This may be worth asking about. It has no figures.")
    text = (
        "This may be worth asking about. The data is from 2026. "
        "Can you tell me more about this line?"
    )
    assert not checks.accept(text, flag)


def test_figures_compare_by_value():
    assert checks.figures("$1,234.50") == checks.figures("1234.5") == {Decimal("1234.5")}
    assert checks.figures("no numbers here.") == set()
    assert checks.figures("in 2026.") == {Decimal("2026")}   # sentence period not a decimal


def test_code_digits_must_be_in_source():
    bad = GOOD_TEXT.replace("of $823.00.", "of $823.00 for code 99999.")
    assert bad != GOOD_TEXT                      # the edit really happened
    assert not checks.accept(bad, FLAG)
    ok = GOOD_TEXT.replace("of $823.00.", "of $823.00 for code 99213.")
    assert ok != GOOD_TEXT
    assert checks.accept(ok, FLAG)


# --- E7: implied figure words ---------------------------------------------

@pytest.mark.parametrize("word", ["twice", "double", "triple", "half", "percent", "threefold"])
def test_e7_implied_figure_word_rejected(word):
    text = (
        f"The price may be worth asking about. It is about {word} the usual amount. "
        "Can you explain how this price was set?"
    )
    assert not checks.accept(text, FLAG)


def test_e7_allowed_when_source_has_the_word():
    flag = make_flag(reason=REASON + " It is about double the usual amount.")
    text = (
        "The price may be worth asking about. It is about double the usual amount. "
        "Can you explain how this price was set?"
    )
    assert checks.accept(text, flag)


# --- E8: sentence shape ----------------------------------------------------

@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "Only one sentence?",                                              # 1 sentence
        "One. Two. Three. Can you explain it?",                           # 4 sentences
        "This may be worth asking about. It is a statement.",             # no question
        "Can you explain it? Can you also confirm it?",                   # two questions
        "Can you explain it? This may be worth asking about.",            # question not last
        "No terminal punctuation here. Can you explain it",               # last has no "?"
        " ".join(["word"] * 70) + ". Can you explain it?",                # too long
    ],
)
def test_e8_bad_shape_rejected(text):
    assert not checks.sentence_shape_ok(text)
    assert not checks.accept(text, FLAG)


def test_two_and_three_sentences_ok():
    assert checks.sentence_shape_ok("This may be worth asking about. Can you explain it?")
    assert checks.sentence_shape_ok("One thing. Another thing. Can you explain it?")


def test_money_with_decimal_is_not_split():
    assert checks.sentence_shape_ok("It costs $1,234.50 here. Can you explain it?")


@pytest.mark.parametrize("bad", [None, 5, ["x"], {"a": 1}])
def test_non_string_rejected(bad):
    assert not checks.accept(bad, FLAG)


# --- Properties ------------------------------------------------------------

_words = st.sampled_from(
    ["price", "may", "be", "worth", "asking", "about", "$1,234.50", "1.5", "823", "2026",
     "99213", "7", "$9.99", "fraud", "Illegal", "twice", "half", "overcharged", "100%"]
)
_sentence = st.lists(_words, min_size=1, max_size=8).map(lambda w: " ".join(w))
_built = st.tuples(
    st.lists(_sentence, min_size=1, max_size=3),
    _sentence,
).map(lambda t: ". ".join(t[0]) + ". " + t[1] + "?")


@settings(max_examples=300)
@given(st.one_of(st.text(max_size=120), _built, st.just(GOOD_TEXT)))
def test_p1_p5_accepted_text_is_always_safe(text):
    if checks.accept(text, FLAG):
        assert not checks.has_banned_word(text)
        source_figs = checks.figures(REASON + " " + BASIS) | {Decimal(2026)}
        assert checks.figures(text) <= source_figs
        assert checks.implied_figure_words(text) <= checks.implied_figure_words(REASON + " " + BASIS)
        assert checks.sentence_shape_ok(text)
