"""Tone check shared by the letter modules.

True if a text has accusation, legal, money-demand or deadline wording (see the word lists
in ``config.py``; they are rules of thumb). Pure: no I/O.
"""

from __future__ import annotations

import re

from backend.explain.checks import normalise

from . import config

_TONE_REGEXES = tuple(
    re.compile(p)
    for group in (
        config.ACCUSATION_PATTERNS,
        config.LEGAL_PATTERNS,
        config.MONEY_DEMAND_PATTERNS,
        config.DEADLINE_PATTERNS,
    )
    for p in group
)


def lower(text: str) -> str:
    """Normalised lower-case text. Curly apostrophes become plain ones."""
    return normalise(text).replace("\u2019", "'").replace("\u2018", "'")


def has_tone_problem(text: str) -> bool:
    """True if the text has accusation, legal, money-demand or deadline wording."""
    norm = lower(text)
    return any(rx.search(norm) for rx in _TONE_REGEXES)


__all__ = ["lower", "has_tone_problem"]
