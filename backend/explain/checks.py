"""Checks that decide whether a model-written explanation may be used.

The model is not trusted. These pure functions are the safety layer: an explanation is
used only if ``accept`` returns True. Otherwise the flag gets its fallback text.

Rules (see the spec):
- no banned word or phrase
- every figure in the text is also in the flag's ``reason``/``basis`` (or is its year)
- no word that implies a new figure ("twice", "half", ...) unless the source has it
- 2 to 3 short sentences, ending with exactly one question
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation

from . import config
from ._contracts import Flag

# --- text normalisation ----------------------------------------------------

_ZERO_WIDTH = re.compile("[\u200b-\u200f\u2060\ufeff]")
_SPACES = re.compile(r"\s+")


def _normalise(text: str) -> str:
    """Lowercase, fold look-alike characters, drop zero-width characters, and collapse
    whitespace. Used so a banned phrase cannot hide behind odd spacing or width."""
    text = unicodedata.normalize("NFKC", text)
    text = _ZERO_WIDTH.sub("", text)
    return _SPACES.sub(" ", text).strip().lower()


# --- banned words ----------------------------------------------------------


def has_banned_word(text: str) -> bool:
    """True if ``text`` contains any banned word or phrase (case-insensitive)."""
    norm = _normalise(text)
    return any(word in norm for word in config.BANNED_WORDS)


# --- figures ---------------------------------------------------------------

# A number: digits with optional thousands commas and optional decimals.
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def figures(text: str) -> set[Decimal]:
    """Return the numeric values found in ``text`` (as Decimals).

    ``$1,234.50`` and ``1234.5`` give the same value. Compared by value, not text.
    """
    found: set[Decimal] = set()
    for match in _NUMBER.findall(_normalise(text)):
        try:
            found.add(Decimal(match.replace(",", "")))
        except InvalidOperation:
            continue
    return found


_WORD = re.compile(r"[a-z]+")
_IMPLIED_STEMS = ("twice", "double", "triple", "half", "halve", "percent")


def implied_figure_words(text: str) -> set[str]:
    """Return stems of words that imply a figure ("twice", "half", "percent", "-fold")."""
    stems: set[str] = set()
    for word in _WORD.findall(_normalise(text)):
        for stem in _IMPLIED_STEMS:
            if word.startswith(stem):
                stems.add(stem)
        if word.endswith("fold"):
            stems.add("fold")
    return stems


# --- sentence shape --------------------------------------------------------

_SENTENCE_SPLIT = re.compile(r"(?<=[.?!])\s+")


def sentence_shape_ok(text: str) -> bool:
    """True if the text is 2 to 3 sentences, short, and ends with exactly one question.

    A split happens only at ``.``/``?``/``!`` followed by whitespace, so ``$1,234.50``
    stays in one piece.
    """
    stripped = text.strip()
    if not stripped:
        return False
    if len(stripped.split()) > config.MAX_WORDS:
        return False
    sentences = _SENTENCE_SPLIT.split(stripped)
    if not (config.MIN_SENTENCES <= len(sentences) <= config.MAX_SENTENCES):
        return False
    if not all(s and s[-1] in ".?!" for s in sentences):
        return False
    # Exactly one question, and it is the last sentence.
    return stripped.count("?") == 1 and sentences[-1].endswith("?")


# --- the gate --------------------------------------------------------------


def _source_text(flag: Flag) -> str:
    return f"{flag.reason} {flag.basis}"


def accept(text: object, flag: Flag) -> bool:
    """True only if ``text`` is safe to use as ``flag.explanation``."""
    if not isinstance(text, str) or not text.strip():
        return False
    if has_banned_word(text):
        return False
    if not sentence_shape_ok(text):
        return False

    source = _source_text(flag)
    allowed = figures(source)
    if flag.data_year is not None:
        allowed.add(Decimal(flag.data_year))
    if not figures(text) <= allowed:
        return False
    if not implied_figure_words(text) <= implied_figure_words(source):
        return False
    return True


__all__ = [
    "has_banned_word",
    "figures",
    "implied_figure_words",
    "sentence_shape_ok",
    "accept",
]
