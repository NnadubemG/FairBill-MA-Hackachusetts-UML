"""Post-processing for extracted line items: normalization and merge.

This module is pure (no network, no disk, no clock, no randomness) so it is easy to
test. Task 5 scope: money/date normalization and continuation-row merge. Code and
confidence rules come in task 6.

Dates (both ``LineItem.date_of_service`` and bill-level ``statement_date``) are
normalized to ISO 8601 ``YYYY-MM-DD``. Money is normalized to a float. Values that
cannot be confidently parsed are left as ``None`` rather than guessed — we never
invent a number or a date.
"""

from __future__ import annotations

import re
from dataclasses import replace

from ._contracts import LineItem

# ---------------------------------------------------------------------------
# Money normalization
# ---------------------------------------------------------------------------

# Strip currency symbols, thousands separators, and surrounding whitespace.
# A trailing/leading parenthesis pair denotes a negative amount on many bills.
_MONEY_STRIP = re.compile(r"[,$\s]")


def normalize_money(value: object) -> float | None:
    """Return a float dollar amount, or None if it cannot be parsed.

    Accepts numbers directly. For strings: strips ``$``, commas, and whitespace;
    treats ``(123.45)`` as ``-123.45``. Returns None for empty/unparseable input
    (we never guess an amount).
    """
    if isinstance(value, bool):  # guard: bool is a subclass of int
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    if text.endswith("-"):  # trailing-minus accounting style
        negative = True
        text = text[:-1]

    cleaned = _MONEY_STRIP.sub("", text)
    if cleaned in ("", "-", "+"):
        return None
    try:
        amount = float(cleaned)
    except ValueError:
        return None
    return -amount if negative else amount


# ---------------------------------------------------------------------------
# Date normalization
# ---------------------------------------------------------------------------

_MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "jan", "feb", "mar", "apr", "may", "jun",
            "jul", "aug", "sep", "oct", "nov", "dec",
        ],
        start=1,
    )
}

_ISO_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
# Numeric date with / or - separators: m/d/y or y/m/d depending on part widths.
_NUM_RE = re.compile(r"^(\d{1,4})[/\-](\d{1,2})[/\-](\d{1,4})$")
# "Mon DD, YYYY" or "DD Mon YYYY".
_TEXT_RE = re.compile(
    r"^(?:([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})|(\d{1,2})\s+([A-Za-z]{3,9})\.?\s+(\d{4}))$"
)


def _valid_ymd(y: int, m: int, d: int) -> str | None:
    if not (1 <= m <= 12 and 1 <= d <= 31 and 1000 <= y <= 9999):
        return None
    return f"{y:04d}-{m:02d}-{d:02d}"


def normalize_date(value: object) -> str | None:
    """Return an ISO 8601 ``YYYY-MM-DD`` string, or None if unparseable.

    Handles ISO, ``MM/DD/YYYY`` (and ``YYYY/MM/DD``), and textual month forms like
    ``Mar 4, 2026`` / ``4 Mar 2026``. Ambiguity is resolved toward the US
    month-first convention used on US hospital bills. Anything else -> None; we never
    guess a date.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None

    m = _ISO_RE.match(text)
    if m:
        return _valid_ymd(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    m = _NUM_RE.match(text)
    if m:
        a, b, c = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if len(m.group(1)) == 4:  # YYYY/MM/DD
            return _valid_ymd(a, b, c)
        if len(m.group(3)) == 4:  # MM/DD/YYYY (US bills)
            return _valid_ymd(c, a, b)
        return None  # two-digit year: too ambiguous to guess

    m = _TEXT_RE.match(text)
    if m:
        if m.group(1):  # "Mon DD, YYYY"
            mon = _MONTHS.get(m.group(1)[:3].lower())
            if mon:
                return _valid_ymd(int(m.group(3)), mon, int(m.group(2)))
        else:  # "DD Mon YYYY"
            mon = _MONTHS.get(m.group(5)[:3].lower())
            if mon:
                return _valid_ymd(int(m.group(6)), mon, int(m.group(4)))
    return None


# ---------------------------------------------------------------------------
# LineItem normalization + continuation-row merge
# ---------------------------------------------------------------------------


def normalize_line(line: LineItem) -> LineItem:
    """Return a LineItem with money as float and dates in ISO form.

    ``billed_amount`` is required by the contract; if it cannot be parsed we leave it
    as-is (validation already guaranteed it is a number, so this is defensive).
    ``date_of_service`` normalizes to ISO or None.
    """
    amount = normalize_money(line.billed_amount)
    dos = normalize_date(line.date_of_service) if line.date_of_service else None
    return replace(
        line,
        billed_amount=amount if amount is not None else line.billed_amount,
        date_of_service=dos,
    )


def _is_continuation(line: LineItem) -> bool:
    """A continuation fragment: no amount of its own and no code, just more text.

    Such rows are wrapped description text from the row above (common on dense
    statements), not a line in their own right.
    """
    amount = normalize_money(line.billed_amount)
    return (amount is None or amount == 0.0) and not line.code and bool(
        (line.description or "").strip()
    )


def merge_continuations(lines: list[LineItem]) -> list[LineItem]:
    """Merge continuation fragments into the preceding real line.

    A fragment (no own amount, no code, only extra description text) is appended to
    the description of the line above it. A leading fragment with no prior line is
    kept as-is (we do not drop data).
    """
    merged: list[LineItem] = []
    for line in lines:
        if merged and _is_continuation(line):
            prev = merged[-1]
            extra = (line.description or "").strip()
            combined = f"{prev.description} {extra}".strip() if extra else prev.description
            merged[-1] = replace(prev, description=combined)
        else:
            merged.append(line)
    return merged


def normalize_and_merge(lines: list[LineItem]) -> list[LineItem]:
    """Normalize each line, then merge continuation fragments.

    Normalization runs first so continuation detection sees parsed amounts.
    """
    normalized = [normalize_line(line) for line in lines]
    return merge_continuations(normalized)


__all__ = [
    "normalize_money",
    "normalize_date",
    "normalize_line",
    "merge_continuations",
    "normalize_and_merge",
]
