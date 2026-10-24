"""Entry point for the deterministic checks engine."""

from __future__ import annotations

from typing import Sequence

from contracts.types import Flag, LineItem, PriceReference
from core.checks.coverage import check_coverage
from core.checks.duplicates import check_duplicates
from core.checks.price import check_price
from core.reference import ReferenceIndex


def _sort_key(flag: Flag) -> tuple:
    # Every field is in the key, so the order never depends on input order,
    # even if two items share an id.
    return (
        flag.line_item_id,
        flag.flag_type,
        flag.severity,
        flag.reason,
        flag.basis,
        flag.data_source or "",
        flag.data_year if flag.data_year is not None else 0,
    )


def analyze(items: Sequence[LineItem], refs: Sequence[PriceReference]) -> list[Flag]:
    """Return "may be worth asking about" flags for the given line items.

    Pure: no network, no file access, no randomness. Same input, same output,
    regardless of the order of `items` or `refs`.
    """
    index = ReferenceIndex(refs)
    flags = [
        *check_price(items, index),
        *check_duplicates(items),
        *check_coverage(items, index),
    ]
    return sorted(flags, key=_sort_key)
