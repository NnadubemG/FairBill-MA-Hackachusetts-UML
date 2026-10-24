"""Checks that decide whether a model-written reason paragraph may go in the letter.

The model is not trusted. These pure functions are the safety layer: a paragraph is used
only if ``accept_paragraph`` returns True. Otherwise the fixed fallback paragraph is used.

Rules (see the spec):
- no banned word
- no accusation, legal, money-demand or deadline wording
- every figure is in the facts given for the letter; no word that implies a new figure
- one paragraph, 2 to 4 sentences, short, first person, no greeting or sign-off, no list,
  markdown, link, email or placeholder
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Sequence

from backend.explain.checks import figures, has_banned_word, implied_figure_words

from . import config
from .facts import ItemFact, facts_text
from .tone import has_tone_problem, lower as _lower

_WORD = re.compile(r"[a-z']+")
_SENTENCE_SPLIT = re.compile(r"(?<=[.?!])\s+")
# Characters and starts that mean markdown, links, emails or placeholders.
_FORBIDDEN_CHARS = set("`*#@<>[]{}\\|")
_LIST_START = re.compile(r"^\s*(?:[-•–—]|\d+[.)])\s")


def is_first_person(text: str) -> bool:
    """True if the text uses at least one first-person word (I, my, me, I'd, ...)."""
    return any(w in config.FIRST_PERSON_WORDS for w in _WORD.findall(_lower(text)))


def has_frame_words(text: str) -> bool:
    """True if the text has a greeting or sign-off word (those belong to the template)."""
    return any(w in config.LETTER_FRAME_WORDS for w in _WORD.findall(_lower(text)))


def has_forbidden_format(text: str) -> bool:
    """True for markdown, links, emails, placeholders, lists, line breaks or '!'."""
    if any(ch in _FORBIDDEN_CHARS for ch in text):
        return True
    if "\n" in text or "\r" in text or "!" in text:
        return True
    low = text.lower()
    if "http" in low or "www." in low:
        return True
    return _LIST_START.search(text) is not None


def shape_ok(text: str) -> bool:
    """True for one paragraph of 2 to 4 sentences within the word limit."""
    stripped = text.strip()
    if not stripped:
        return False
    if len(stripped.split()) > config.MAX_PARAGRAPH_WORDS:
        return False
    sentences = _SENTENCE_SPLIT.split(stripped)
    if not (config.MIN_SENTENCES <= len(sentences) <= config.MAX_SENTENCES):
        return False
    return all(s and s[-1] in ".?" for s in sentences)


def _without_dates(text: str, dates: Sequence[str]) -> str:
    """Remove each whole date string, so its parts (month, day) are not read as figures."""
    for d in sorted(set(dates), key=len, reverse=True):
        text = text.replace(d, " ")
    return text


def figures_ok(text: str, items: Sequence[ItemFact]) -> bool:
    """True if every figure (and figure-implying word) in ``text`` is in the facts.

    A date from the facts (``2026-03-04``) is allowed only as a whole. Its month and day
    do not make "3" or "4" allowed on their own.
    """
    source = facts_text(items)
    dates = [item.date for item in items if item.date]
    allowed: set[Decimal] = figures(_without_dates(source, dates))
    if not figures(_without_dates(text, dates)) <= allowed:
        return False
    return implied_figure_words(text) <= implied_figure_words(source)


def accept_paragraph(text: object, items: Sequence[ItemFact]) -> bool:
    """True only if ``text`` is safe to use as the letter's reason paragraph."""
    if not isinstance(text, str) or not text.strip():
        return False
    if has_banned_word(text):
        return False
    if has_tone_problem(text):
        return False
    if has_forbidden_format(text) or has_frame_words(text):
        return False
    if not shape_ok(text):
        return False
    if not is_first_person(text):
        return False
    return figures_ok(text, items)


__all__ = [
    "has_tone_problem",
    "is_first_person",
    "has_frame_words",
    "has_forbidden_format",
    "shape_ok",
    "figures_ok",
    "accept_paragraph",
]
