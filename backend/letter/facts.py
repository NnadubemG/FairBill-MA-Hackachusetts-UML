"""Facts a letter may cite: a line's safe code, amount and date, and a flag's text.

A letter may cite only these facts (plus the patient's own fields). Everything here is
pure: no network, no files, no logging.

- A code is used only if it is 1 to 12 letters, digits, dots or dashes and has no banned
  word (the same safety rule ``/core`` uses). Otherwise the line is shown without a code.
- An amount is used only if it is a finite, non-negative number.
- A date is used only if it is a real ISO date (YYYY-MM-DD).
- Line descriptions are never used (untrusted bill text).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Sequence

from backend.explain.checks import has_banned_word

from . import config
from ._contracts import Flag, LineItem
from .request import clean_field

WARN_UNKNOWN_LINE = (
    "Some selected items could not be matched to a bill line and were left out of the letter."
)
WARN_TOO_MANY = f"Only the first {config.MAX_FLAGS} items were included in the letter."

_CODE_PATTERN = re.compile(r"[A-Za-z0-9.\-]{1,12}")
_ISO_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_CENT = Decimal("0.01")
_MAX_AMOUNT = Decimal("1000000000000")  # one trillion; anything bigger is not a bill
_MAX_FLAG_TEXT = 500


def safe_code(code: object) -> str | None:
    """Return the code upper-cased if it is safe to print, else None."""
    if not isinstance(code, str):
        return None
    stripped = code.strip()
    if _CODE_PATTERN.fullmatch(stripped) is None:
        return None
    if has_banned_word(stripped):
        return None
    return stripped.upper()


def format_amount(amount: object) -> str | None:
    """Format a dollar amount like ``$1,234.50``, or None if it cannot be trusted."""
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        return None
    try:
        number = Decimal(str(amount))
        if not number.is_finite() or number < 0 or number > _MAX_AMOUNT:
            return None
        if number == 0:
            number = Decimal(0)  # drop the sign of negative zero ("-0.0")
        return f"${number.quantize(_CENT, rounding=ROUND_HALF_UP):,.2f}"
    except InvalidOperation:
        return None


def format_date(value: object) -> str | None:
    """Return the date if it is a real ISO date (YYYY-MM-DD), else None."""
    if not isinstance(value, str):
        return None
    match = _ISO_DATE.fullmatch(value.strip())
    if match is None:
        return None
    try:
        date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None
    return value.strip()


def _safe_flag_text(text: object) -> str:
    """One-line flag text, or empty if it is missing or contains a banned word."""
    cleaned = clean_field(text, _MAX_FLAG_TEXT)
    return "" if has_banned_word(cleaned) else cleaned


@dataclass(frozen=True)
class ItemFact:
    """The facts for one flag and its line. All values are already made safe.

    ``reason`` and ``basis`` are empty if the flag text was missing or unsafe.
    ``code``, ``amount`` and ``date`` are None if they could not be trusted.
    """

    key: str
    line_item_id: str
    flag_type: str
    reason: str
    basis: str
    code: str | None
    amount: str | None
    date: str | None
    data_year: int | None


def build_items(
    flags: Sequence[Flag], lines: Sequence[LineItem]
) -> tuple[list[ItemFact], list[str]]:
    """Match flags to lines (input order) and return safe facts plus generic warnings.

    A flag whose line id is not in ``lines`` is skipped. At most ``MAX_FLAGS`` items are
    kept. If two lines share an id, the first one wins.
    """
    by_id: dict[str, LineItem] = {}
    for line in lines:
        by_id.setdefault(line.id, line)

    items: list[ItemFact] = []
    unknown = False
    over_cap = False
    for flag in flags:
        line = by_id.get(flag.line_item_id)
        if line is None:
            unknown = True
            continue
        if len(items) >= config.MAX_FLAGS:
            over_cap = True
            continue
        year = flag.data_year if isinstance(flag.data_year, int) and not isinstance(flag.data_year, bool) else None
        items.append(
            ItemFact(
                key=f"f{len(items)}",
                line_item_id=line.id,
                flag_type=str(flag.flag_type),
                reason=_safe_flag_text(flag.reason),
                basis=_safe_flag_text(flag.basis),
                code=safe_code(line.code),
                amount=format_amount(line.billed_amount),
                date=format_date(line.date_of_service),
                data_year=year,
            )
        )

    warnings: list[str] = []
    if unknown:
        warnings.append(WARN_UNKNOWN_LINE)
    if over_cap:
        warnings.append(WARN_TOO_MANY)
    return items, warnings


def facts_text(items: Sequence[ItemFact]) -> str:
    """All fact text for the items, joined. The reason paragraph may only use figures
    that appear in this text. It is built from the same fields the model is given."""
    parts: list[str] = []
    for item in items:
        parts.extend([item.reason, item.basis])
        for value in (item.code, item.amount, item.date):
            if value:
                parts.append(value)
        if item.data_year is not None:
            parts.append(str(item.data_year))
    return "\n".join(p for p in parts if p)


__all__ = [
    "WARN_UNKNOWN_LINE",
    "WARN_TOO_MANY",
    "ItemFact",
    "safe_code",
    "format_amount",
    "format_date",
    "build_items",
    "facts_text",
]
