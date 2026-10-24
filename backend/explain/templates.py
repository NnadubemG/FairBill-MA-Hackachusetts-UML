"""Deterministic fallback explanations, one per flag type.

A fallback is the flag's own ``reason`` (already written by ``/core`` from a fixed
template) plus one fixed question for the flag type. It adds no figure and uses no model.
It is a pure function: the same flag always gives the same text.

If a flag's ``reason`` is empty or contains a banned word, the fallback does not copy it.
It uses a fixed generic sentence instead. A last guard checks the final text again.
"""

from __future__ import annotations

import re
from typing import Final

from ._contracts import Flag
from .checks import has_banned_word

# One fixed question per flag type. No digits here, so no figure can be added.
QUESTIONS: Final[dict[str, str]] = {
    "price_above_reference": "Can you explain how this price was set?",
    "price_outside_ma_range": "Can you explain how this price was set?",
    "duplicate_line_item": "Can you confirm that each of these lines is expected?",
    "quantity_implausible": "Can you confirm the number of units billed?",
    "possible_unbundling": "Can you explain why these items were billed separately?",
    "no_reference_found": "Can you tell me what this item covers?",
}
GENERIC_QUESTION: Final[str] = "Can you tell me more about this line?"
GENERIC_LEAD: Final[str] = "This line may be worth asking about."

_SPACES = re.compile(r"\s+")


def question_for(flag_type: str) -> str:
    """Return the fixed question for ``flag_type`` (generic for an unknown type)."""
    return QUESTIONS.get(flag_type, GENERIC_QUESTION)


def _lead(flag: Flag) -> str:
    """The first part of the fallback: the flag's reason, or a generic sentence."""
    reason = _SPACES.sub(" ", flag.reason or "").strip()
    if not reason or has_banned_word(reason):
        return GENERIC_LEAD
    if reason[-1] not in ".?!":
        reason += "."
    return reason


def fallback(flag: Flag) -> str:
    """Return the deterministic explanation for ``flag``."""
    text = f"{_lead(flag)} {question_for(flag.flag_type)}"
    if has_banned_word(text):  # last guard; should not happen
        text = f"{GENERIC_LEAD} {question_for(flag.flag_type)}"
    return text


__all__ = ["QUESTIONS", "GENERIC_QUESTION", "GENERIC_LEAD", "question_for", "fallback"]
