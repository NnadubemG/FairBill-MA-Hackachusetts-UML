"""Price checks: compare the per-unit billed amount to reference prices.

Fail safe: with no usable reference figure, nothing is flagged and nothing is estimated.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional, Sequence

from contracts.types import Flag, LineItem, PriceReference
from core import constants
from core.language import (
    above_reference_text,
    outside_ma_range_text,
    to_decimal,
    to_money,
)
from core.reference import ReferenceIndex, clean_code


def _has_provenance(ref: PriceReference) -> bool:
    """A price figure may only be cited if its source and year are present."""
    return (
        isinstance(ref.data_source, str)
        and ref.data_source.strip() != ""
        and isinstance(ref.data_year, int)
        and not isinstance(ref.data_year, bool)
    )


def _unit_price(item: LineItem) -> Optional[Decimal]:
    """Per-unit billed amount in dollars, or None if it cannot be computed safely.

    billed_amount is the line total; reference prices are per unit.
    """
    total = to_money(item.billed_amount)
    if total is None or total <= 0:
        return None
    if item.quantity is None:
        return total
    quantity = to_decimal(item.quantity)
    if quantity is None or quantity <= 0:
        return None
    try:
        return to_money(total / quantity)
    except ArithmeticError:
        return None


def check_price(items: Sequence[LineItem], index: ReferenceIndex) -> list[Flag]:
    flags: list[Flag] = []
    for item in items:
        match = index.lookup(item)
        if match.status != "found" or match.ref is None:
            continue
        ref = match.ref
        if not _has_provenance(ref):
            continue
        code = clean_code(item.code)
        unit_price = _unit_price(item)
        if code is None or unit_price is None:
            continue

        high = to_money(ref.ma_range_high)
        if high is not None and high > 0 and unit_price > high:
            reason, basis = outside_ma_range_text(
                code, unit_price, to_money(ref.ma_range_low), high, ref.data_source, ref.data_year
            )
            flags.append(
                Flag(
                    line_item_id=item.id,
                    flag_type="price_outside_ma_range",
                    severity=constants.SEVERITY["price_outside_ma_range"],
                    reason=reason,
                    basis=basis,
                    data_source=ref.data_source,
                    data_year=ref.data_year,
                )
            )

        medicare = to_money(ref.medicare_price)
        if medicare is not None and medicare > 0:
            threshold = to_money(medicare * constants.MEDICARE_MULTIPLE)
            if threshold is not None and unit_price > threshold:
                reason, basis = above_reference_text(
                    code, unit_price, medicare, ref.data_source, ref.data_year
                )
                flags.append(
                    Flag(
                        line_item_id=item.id,
                        flag_type="price_above_reference",
                        severity=constants.SEVERITY["price_above_reference"],
                        reason=reason,
                        basis=basis,
                        data_source=ref.data_source,
                        data_year=ref.data_year,
                    )
                )
    return flags
