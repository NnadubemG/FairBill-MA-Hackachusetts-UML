"""Banned-words guardrail.

Mirrors the banned-words list in `.kiro/steering/product.md`. Model-generated
text (letter subject/body, extracted plain-language labels) is passed through
`scrub()` before it is returned, so the app never adopts advice-like, accusatory,
or outcome-promising language as its own.

The list lives HERE as the single stored copy the server uses. If product.md's
list changes, update `_RULES` to match (there is one list, read by both the
extract and letter handlers).

Matching is case-insensitive and catches common variants (plurals / verb
tenses). Substitution replaces a banned term with a neutral alternative. The
function reports whether any violation was found so a handler can optionally
re-prompt once.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Pattern, Tuple


@dataclass(frozen=True)
class _Rule:
    # Regex (case-insensitive) matching the banned term and its obvious variants.
    pattern: Pattern[str]
    # Neutral replacement text.
    replacement: str


def _rule(regex: str, replacement: str) -> _Rule:
    return _Rule(re.compile(regex, re.IGNORECASE), replacement)


# Ordered so more specific multi-word phrases are handled before single words.
# \b word boundaries keep us from clipping inside larger words (e.g. "insurer").
_RULES: List[_Rule] = [
    _rule(r"\blegal\s+advice\b", "general information"),
    _rule(r"\bmedical\s+advice\b", "general information"),
    _rule(r"\bpenalty[\s-]?free\b", "a common next step"),
    _rule(r"\brisk[\s-]?free\b", "a common next step"),
    _rule(r"\bguarantee(?:s|d|ing)?\b", "may help"),
    _rule(r"\bensure(?:s|d|ing)?\b", "can help"),
    _rule(r"\bpromise(?:s|d|ing)?\b", "aims to"),
    _rule(r"\bdiagnos(?:e|es|ed|ing|is)\b", "general information about"),
    _rule(r"\blawsuits?\b", "dispute"),
    _rule(r"\bsu(?:e|es|ed|ing)\b", "file a complaint"),
    _rule(r"\bfraud(?:ulent)?\b", "possible billing error"),
    _rule(r"\bscams?\b", "charge worth questioning"),
    _rule(r"\b(?:illegal|unlawful)\b", "may not be allowed — worth confirming"),
    _rule(r"\bliabilit(?:y|ies)\b", "responsibility — confirm"),
    _rule(r"\bliable\b", "may be responsible — confirm"),
    _rule(r"\bentitled\b", "may be eligible — check"),
    _rule(r"\battorneys?\b", "a qualified professional"),
    _rule(r"\blawyers?\b", "a qualified professional"),
    _rule(r"\bcertainly\b", "often"),
    _rule(r"\bdefinitely\b", "often"),
    _rule(r"\balways\b", "typically"),
    _rule(r"\bnever\b", "rarely"),
    _rule(r"\b(?:win|beat)(?:s|ning)?\b", "resolve"),
]


def scrub(text: str) -> Tuple[str, bool]:
    """Return (cleaned_text, had_violation).

    Applies each rule in order, substituting the neutral alternative. Reports
    True if any banned term was found and replaced.
    """
    if not text:
        return text, False

    had_violation = False
    cleaned = text
    for rule in _RULES:
        cleaned, n = rule.pattern.subn(rule.replacement, cleaned)
        if n:
            had_violation = True
    return cleaned, had_violation


def contains_banned(text: str) -> bool:
    """True if the text contains any banned term (no substitution performed)."""
    if not text:
        return False
    return any(rule.pattern.search(text) for rule in _RULES)
