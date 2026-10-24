"""Tests for the reason paragraph checks (spec task 4).

Covers L8 (every kind of bad paragraph is rejected) and property PL2 (an accepted
paragraph is always safe).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.explain.checks import figures, has_banned_word
from backend.letter import checks, config
from backend.letter.facts import build_items, facts_text

from .factories import BASIS, REASON, make_flag, make_line

ITEMS, _ = build_items([make_flag("1")], [make_line("1")])

GOOD = (
    "I would like to understand the charge of $1,234.50 for code 99213. "
    "I am asking how this line was coded and billed. "
    "I would be grateful for a review so that I can understand it better."
)


def ok(text: str, items=ITEMS) -> bool:
    return checks.accept_paragraph(text, items)


def test_good_paragraph_is_accepted():
    assert ok(GOOD)


def test_figures_in_facts_are_allowed_in_any_format():
    assert ok(GOOD.replace("$1,234.50", "1234.5"))
    assert ok(GOOD.replace("code 99213", "code 99213 on 2026-03-04"))      # date part digits
    assert ok(GOOD.replace("99213", "99213 (2026)"))                       # the year


def test_no_items_means_no_figures_allowed():
    assert ok("I would like to understand my bill better. I would be grateful for your help.", [])
    assert not ok(GOOD, [])


# --- L8: bad paragraphs fall back (each alone) -----------------------------

def with_extra(sentence: str) -> str:
    return GOOD + " " + sentence


@pytest.mark.parametrize("word", list(config.BANNED_WORDS))
def test_l8_banned_words(word):
    assert not ok(with_extra(f"I wonder if this is {word}."))


@pytest.mark.parametrize(
    "sentence",
    [
        "I think this was wrong.",
        "I believe there was a mistake.",
        "There may be an error here.",
        "I was overbilled for this.",
        "This feels like a scam.",
        "The price is excessive.",
        "This seems unfair to me.",
        "I think the price was inflated.",
        "They tried to cheat me.",
    ],
)
def test_l8_accusations(sentence):
    assert not ok(with_extra(sentence))


@pytest.mark.parametrize(
    "sentence",
    [
        "I may speak to an attorney.",
        "I may talk to a lawyer about it.",
        "This may be a legal matter.",
        "I know the law on this.",
        "I could file a lawsuit.",
        "I may go to court.",
        "I may file a complaint.",
        "This may be a violation.",
        "I will contact the regulator.",
    ],
)
def test_l8_legal_terms(sentence):
    assert not ok(with_extra(sentence))


@pytest.mark.parametrize(
    "sentence",
    [
        "I would like a refund.",
        "I think you owe me money.",
        "Please reimburse me.",
        "I want compensation.",
        "I demand an answer.",
        "I would like my money back.",
    ],
)
def test_l8_money_demands(sentence):
    assert not ok(with_extra(sentence))


@pytest.mark.parametrize(
    "sentence",
    [
        "Please reply within ten days.",
        "I need an answer immediately.",
        "Please answer by the end of the week.",
        "There is a deadline.",
        "This is urgent.",
        "I need this as soon as possible, no later than Friday.",
    ],
)
def test_l8_deadlines(sentence):
    assert not ok(with_extra(sentence))


@pytest.mark.parametrize(
    "bad",
    [
        GOOD.replace("$1,234.50", "$900.00"),               # new figure
        GOOD.replace("$1,234.50", "$1,324.50"),             # changed figure
        GOOD.replace("99213", "99999"),                     # wrong code
        with_extra("I called 3 times."),                    # new small number
        with_extra("This is about double the usual price."),
        with_extra("I was charged twice."),
        with_extra("It is half of what I expected."),
        with_extra("It is a ten percent difference."),
    ],
)
def test_l8_new_or_changed_figures(bad):
    assert not ok(bad)


def test_date_is_allowed_only_as_a_whole():
    whole = GOOD.replace("code 99213", "code 99213 on 2026-03-04")
    assert ok(whole)
    # The month and day of the date must not make "3" or "4" allowed on their own.
    assert not ok(with_extra("I called 3 times."))
    assert not ok(with_extra("I called 4 times."))
    # A different date is not allowed, even though its year and month are.
    assert not ok(GOOD.replace("code 99213", "code 99213 on 2026-03-05"))
    assert not ok(GOOD.replace("code 99213", "code 99213 on 2026-04-04"))


def test_a_number_that_is_in_the_flag_text_is_still_allowed():
    flag = make_flag("1", basis=BASIS + " 3 line items match.")
    items, _ = build_items([flag], [make_line("1")])
    assert ok(with_extra("I see that 3 line items match."), items)


def test_implied_word_is_allowed_when_the_facts_have_it():
    flag = make_flag("1", reason=REASON + " It appears twice on the bill.")
    items, _ = build_items([flag], [make_line("1")])
    assert ok(with_extra("I see that it appears twice."), items)
    assert not ok(with_extra("I see that it appears twice."), ITEMS)


@pytest.mark.parametrize(
    "bad",
    [
        "Dear Billing Office, " + GOOD,
        GOOD + " Sincerely, Jane.",
        GOOD + " Best regards.",
        GOOD + " Yours truly.",
    ],
)
def test_l8_greeting_or_signoff(bad):
    assert not ok(bad)


@pytest.mark.parametrize(
    "bad",
    [
        "- " + GOOD,
        "1. " + GOOD,
        "• " + GOOD,
        GOOD.replace("review", "`review`"),
        GOOD.replace("review", "**review**"),
        GOOD + " See http://example.com for details.",
        GOOD + " See www.example.com.",
        GOOD + " Write to jane@example.com.",
        GOOD + " My name is [Your name].",
        GOOD + " {name} is the patient.",
        GOOD.replace(". I am asking", ".\nI am asking"),          # line break
        GOOD.replace("review", "review!"),                       # exclamation
        "# Heading\n" + GOOD,
    ],
)
def test_l8_markdown_links_placeholders_and_breaks(bad):
    assert not ok(bad)


def test_line_breaks_at_the_ends_are_harmless_but_not_inside():
    assert ok("\n  " + GOOD + "  \n\n")
    assert not ok(GOOD.replace(". I am asking", ".\n\nI am asking"))


def test_l8_not_first_person():
    text = ("The charge of $1,234.50 for code 99213 needs a review. "
            "This line should be explained. A review would help everyone.")
    assert not ok(text)


def test_curly_apostrophe_counts_as_first_person():
    assert ok("I’d like to understand the charge for code 99213. A review would help me.")


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "   ",
        "I would like a review.",                                                 # 1 sentence
        "I ask. I ask. I ask. I ask. I ask.",                                     # 5 sentences
        "I would like a review. " + " ".join(["word"] * 100) + ".",               # too long
        "I would like a review. I have no end punctuation",                       # no final stop
    ],
)
def test_l8_bad_shape(bad):
    assert not ok(bad)


@pytest.mark.parametrize("bad", [None, 5, ["I would like a review."], {"a": 1}, b"bytes"])
def test_l8_non_string(bad):
    assert not ok(bad)


@pytest.mark.parametrize(
    "disguised",
    ["REFUND", "re\u200bfund", "ＲＥＦＵＮＤ", "FRAUD", "fr\u200baud", "ＬＡＷ"],
)
def test_disguised_words_are_caught(disguised):
    assert not ok(with_extra(f"I would like a {disguised}."))


def test_normal_words_are_not_caught_by_mistake():
    text = ("I would like to understand the charge of $1,234.50 for code 99213. "
            "I am asking about the flaw-free outlaw lawn service line. "
            "I would be grateful for a review.")
    assert ok(text)


# --- Properties ------------------------------------------------------------

_words = st.sampled_from(
    ["I", "my", "me", "would", "like", "understand", "the", "charge", "review", "line",
     "$1,234.50", "1.5", "823", "2026", "99213", "7", "$9.99", "fraud", "refund", "wrong",
     "attorney", "within", "twice", "half", "100%", "law", "owe", "Dear"]
)
_sentence = st.lists(_words, min_size=1, max_size=9).map(" ".join)
_built = st.lists(_sentence, min_size=1, max_size=5).map(lambda s: ". ".join(s) + ".")


@settings(max_examples=400)
@given(st.one_of(st.text(max_size=150), _built, st.just(GOOD)))
def test_pl2_accepted_paragraph_is_always_safe(text):
    if not ok(text):
        return
    allowed = figures(facts_text(ITEMS))
    assert figures(text) <= allowed
    assert not has_banned_word(text)
    assert not checks.has_tone_problem(text)
    assert not checks.has_forbidden_format(text) and not checks.has_frame_words(text)
    assert checks.shape_ok(text) and checks.is_first_person(text)
    assert isinstance(Decimal(0), Decimal)  # keeps the import used
