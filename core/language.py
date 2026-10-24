"""Money helpers and fixed flag templates.

Every reason/basis is built from a template here. Only validated values go in:
a code that passed `clean_code`, numbers, and reference-data provenance. Text from
the bill (descriptions, ids) is never interpolated.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Optional

_CENT = Decimal("0.01")


def to_decimal(value: object) -> Optional[Decimal]:
    """Convert an int, float, or Decimal to a finite Decimal. None if unusable."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, Decimal):
        number = value
    elif isinstance(value, (int, float)):
        try:
            number = Decimal(str(value))
        except InvalidOperation:
            return None
    else:
        return None
    return number if number.is_finite() else None


def to_money(value: object) -> Optional[Decimal]:
    """Convert to dollars rounded to cents. None for missing, non-finite, or too-large values."""
    number = to_decimal(value)
    if number is None:
        return None
    try:
        return number.quantize(_CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None


def format_money(amount: Decimal) -> str:
    """Format a Decimal as dollars, e.g. Decimal('1234.5') -> '$1,234.50'."""
    return f"${amount:,.2f}"


def _source(data_source: str, data_year: int) -> str:
    return f"Source: {data_source}, {data_year}."


# --- price flags -----------------------------------------------------------


def outside_ma_range_text(
    code: str,
    unit_price: Decimal,
    low: Optional[Decimal],
    high: Decimal,
    data_source: str,
    data_year: int,
) -> tuple[str, str]:
    if low is not None and low <= high:
        span = f"{format_money(low)} to {format_money(high)}"
    else:
        span = f"up to {format_money(high)}"
    reason = (
        f"The billed amount of {format_money(unit_price)} per unit may be worth asking about. "
        "It is higher than the Massachusetts hospital price range we have on file for this code."
    )
    basis = f"Price range for code {code}: {span} per unit. {_source(data_source, data_year)}"
    return reason, basis


def above_reference_text(
    code: str,
    unit_price: Decimal,
    medicare_price: Decimal,
    data_source: str,
    data_year: int,
) -> tuple[str, str]:
    ratio = unit_price / medicare_price
    reason = (
        f"The billed amount of {format_money(unit_price)} per unit may be worth asking about. "
        f"It is about {ratio:.1f} times the Medicare reference price we have on file for this code."
    )
    basis = (
        f"Medicare reference price for code {code}: {format_money(medicare_price)} per unit. "
        f"{_source(data_source, data_year)}"
    )
    return reason, basis


# --- duplicate and coverage flags (no price figures, so no $ in the text) ---


def duplicate_text(count: int, dated: bool) -> tuple[str, str]:
    matched = "code, description, amount, and date of service" if dated else "code, description, and amount"
    reason = (
        f"This item appears {count} times on the bill with the same {matched}. "
        "It may be worth asking about whether each one is expected."
    )
    basis = f"{count} line items match on {matched}."
    return reason, basis


def no_reference_text(code: str) -> tuple[str, str]:
    reason = (
        f"We do not have a reference price on file for code {code}, so we could not compare it. "
        "It may be worth asking about what this item covers."
    )
    basis = f"No entry for code {code} in the reference data we have."
    return reason, basis


# --- quantity flags (no $ figures) ------------------------------------------


def format_units(value: Decimal) -> str:
    """A unit count without a trailing '.0' (Decimal('2.0') -> '2'). Huge values are not spelled out."""
    if abs(value) >= Decimal(10) ** 12:
        return "a very large number"
    return format(value.normalize(), "f")


def quantity_text(
    code: str, quantity: Decimal, max_units: Decimal, data_source: str, data_year: int
) -> tuple[str, str]:
    reason = (
        f"The quantity of {format_units(quantity)} for this item may be worth asking about. "
        f"It is more than the typical maximum of {format_units(max_units)} units we have on file for this code."
    )
    basis = (
        f"Typical maximum for code {code}: {format_units(max_units)} units. "
        f"{_source(data_source, data_year)}"
    )
    return reason, basis


# --- unbundling flags (no $ figures) ----------------------------------------


def unbundling_text(code_1: str, code_2: str, data_source: str, data_year: int) -> tuple[str, str]:
    reason = (
        f"Code {code_2} appears on the same bill as code {code_1}. "
        "These two codes are often billed together as one service, "
        "so it may be worth asking about whether both are expected."
    )
    basis = (
        f"A published coding edit pairs code {code_1} with code {code_2}. "
        f"{_source(data_source, data_year)}"
    )
    return reason, basis
