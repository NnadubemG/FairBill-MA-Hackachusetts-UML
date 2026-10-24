"""Quantity check: a quantity above the typical maximum for a code.

Fail safe: no usable limit, no usable quantity, or a limit without a source and year means
no flag. A limit is never guessed.
"""

from __future__ import annotations

from typing import Sequence

from contracts.types import Flag, LineItem, QuantityLimit
from core import constants
from core.language import quantity_text, to_decimal
from core.reference import ReferenceIndex, clean_code, has_provenance


def check_quantity(items: Sequence[LineItem], index: ReferenceIndex[QuantityLimit]) -> list[Flag]:
    flags: list[Flag] = []
    for item in items:
        quantity = to_decimal(item.quantity)
        if quantity is None or quantity <= 0:
            continue
        match = index.lookup(item)
        if match.status != "found" or match.ref is None:
            continue
        limit = match.ref
        if not has_provenance(limit):
            continue
        max_units = to_decimal(limit.max_units)
        if max_units is None or max_units <= 0 or quantity <= max_units:
            continue
        code = clean_code(item.code)
        if code is None:
            continue
        reason, basis = quantity_text(code, quantity, max_units, limit.data_source, limit.data_year)
        flags.append(
            Flag(
                line_item_id=item.id,
                flag_type="quantity_implausible",
                severity=constants.SEVERITY["quantity_implausible"],
                reason=reason,
                basis=basis,
                data_source=limit.data_source,
                data_year=limit.data_year,
            )
        )
    return flags
