"""Parse a raw rate cell into either a dollar value, a skip, or missing.

Hard rule (product.md): never invent or interpolate a number. A rate expressed as a
percentage or an algorithm/formula is NOT a dollar figure, so it is skipped and logged,
never estimated. A blank / N/A cell contributes nothing (missing) and leaves the field
null downstream.

parse_rate returns one of three results:
  - Dollar(value)  : a concrete, non-negative dollar figure we can use
  - Skip(reason)   : a value we recognize but refuse to turn into a number
  - Missing()      : no value present

This module is pure; it does not write the skip log itself (see skiplog.py), so it
stays trivially testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Dollar:
    """A concrete, non-negative dollar amount parsed from the cell."""

    value: float


@dataclass(frozen=True)
class Skip:
    """A recognized value we deliberately do not convert to a number."""

    reason: str


@dataclass(frozen=True)
class Missing:
    """No value present (blank / N/A). Contributes nothing; field stays null."""


RateResult = Dollar | Skip | Missing

# Tokens that mean "there is no usable value here" -> Missing.
_MISSING_TOKENS = {"", "n/a", "na", "none", "null", "-", "--"}

# Substrings that mark an algorithm/formula-based rate (not a dollar figure) -> Skip.
_ALGORITHM_MARKERS = (
    "per diem",
    "case rate",
    "percent",
    "of medicare",
    "of charge",
    "see addendum",
    "see appendix",
    "algorithm",
    "fee schedule",
    "formula",
    "varies",
)

# A plain dollar amount: optional $, digits with optional thousands commas and decimals.
_DOLLAR_RE = re.compile(r"^\$?\s*(\d{1,3}(?:,\d{3})*|\d+)(?:\.(\d+))?$")


def parse_rate(cell: str | None) -> RateResult:
    """Classify a raw rate cell. Never produces a Dollar from a % / formula input."""
    if cell is None:
        return Missing()
    text = cell.strip()
    low = text.lower()

    if low in _MISSING_TOKENS:
        return Missing()

    # Percentage-based rate: refuse to estimate.
    if "%" in text:
        return Skip(reason="percentage-based rate; not a dollar figure")

    # Algorithm / formula / narrative rate: refuse to estimate.
    if any(marker in low for marker in _ALGORITHM_MARKERS):
        return Skip(reason="algorithm- or formula-based rate; not a dollar figure")

    m = _DOLLAR_RE.match(text)
    if m:
        whole = m.group(1).replace(",", "")
        frac = m.group(2) or ""
        value = float(f"{whole}.{frac}") if frac else float(whole)
        return Dollar(value=value)

    # A leading minus sign makes the dollar regex fail; catch explicit negatives.
    if re.match(r"^-\s*\$?\s*\d", text):
        return Skip(reason="negative")

    # Anything else we don't recognize as a clean dollar figure: skip, never guess.
    return Skip(reason="unrecognized rate format; not a dollar figure")
