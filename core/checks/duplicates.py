"""Duplicate check: the same item appearing more than once on one bill.

Needs no reference data. Descriptions and ids are used for grouping only and are
never placed in the output text (bill text is untrusted).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional, Sequence

from contracts.types import Flag, LineItem
from core import constants
from core.language import duplicate_text, to_money
from core.reference import normalize_code

GroupKey = tuple[object, Optional[str], str, Decimal, Optional[date]]


def _code_key(item: LineItem) -> Optional[str]:
    """Normalized code for grouping. An invalid code still groups by its own text."""
    normalized = normalize_code(item.code, item.code_system)
    if normalized is not None:
        return normalized
    if isinstance(item.code, str) and item.code.strip():
        return "raw:" + item.code.strip().casefold()
    return None


def _date_key(item: LineItem) -> Optional[date]:
    value = item.date_of_service
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None  # unreadable date: treated as undated


def _group_key(item: LineItem) -> Optional[GroupKey]:
    amount = to_money(item.billed_amount)
    if amount is None or amount <= 0:
        return None  # nothing to compare, or a credit/informational line: stay silent
    description = ""
    if isinstance(item.description, str):
        description = " ".join(item.description.split()).casefold()
    code = _code_key(item)
    if code is None and description == "":
        return None
    return (code, item.code_system, description, amount, _date_key(item))


def check_duplicates(items: Sequence[LineItem]) -> list[Flag]:
    groups: dict[GroupKey, list[LineItem]] = {}
    for item in items:
        key = _group_key(item)
        if key is not None:
            groups.setdefault(key, []).append(item)

    flags: list[Flag] = []
    for key, members in groups.items():
        if len(members) < 2:
            continue
        dated = key[4] is not None
        reason, basis = duplicate_text(len(members), dated)
        severity = (
            constants.SEVERITY["duplicate_line_item"]
            if dated
            else constants.DUPLICATE_UNDATED_SEVERITY
        )
        for member in members:
            flags.append(
                Flag(
                    line_item_id=member.id,
                    flag_type="duplicate_line_item",
                    severity=severity,
                    reason=reason,
                    basis=basis,
                    data_source=None,
                    data_year=None,
                )
            )
    return flags
