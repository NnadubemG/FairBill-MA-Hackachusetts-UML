"""Unbundling check: two codes that a published edit says are normally billed together.

The flag goes on the code_2 line. It never says the billing is wrong, only that it may be
worth asking about. Anything unclear (mixed dates, unusable pair, unknown indicator) is silent.
"""

from __future__ import annotations

from typing import Optional, Sequence

from contracts.types import BundlePair, Flag, LineItem
from core import constants
from core.dates import service_date
from core.language import unbundling_text
from core.reference import clean_code, has_provenance

# NCCI-style edits cover CPT and HCPCS codes only.
_SYSTEMS = (None, "CPT", "HCPCS")


def _usable_pairs(pairs: Sequence[BundlePair]) -> list[tuple[str, str, BundlePair]]:
    """Pairs with valid codes, provenance and indicator; one per (code_1, code_2)."""
    groups: dict[tuple[str, str], list[BundlePair]] = {}
    for pair in dict.fromkeys(pairs):  # drop exact duplicates
        code_1, code_2 = clean_code(pair.code_1), clean_code(pair.code_2)
        if code_1 is None or code_2 is None or code_1 == code_2:
            continue
        if not has_provenance(pair) or pair.modifier_indicator not in constants.UNBUNDLING_SEVERITY:
            continue
        groups.setdefault((code_1, code_2), []).append(pair)

    usable: list[tuple[str, str, BundlePair]] = []
    for (code_1, code_2), candidates in groups.items():
        newest = max(p.data_year for p in candidates)
        top = [p for p in candidates if p.data_year == newest]
        if len(top) == 1:  # a tie between different pairs is ambiguous: stay silent
            usable.append((code_1, code_2, top[0]))
    return usable


def check_unbundling(items: Sequence[LineItem], pairs: Sequence[BundlePair]) -> list[Flag]:
    usable = _usable_pairs(pairs)
    if not usable:
        return []

    coded: list[tuple[LineItem, str]] = []
    for item in items:
        code: Optional[str] = clean_code(item.code)
        if code is not None and item.code_system in _SYSTEMS:
            coded.append((item, code))

    flags: list[Flag] = []
    for code_1, code_2, pair in usable:
        primaries = [item for item, code in coded if code == code_1]
        for item, code in coded:
            if code != code_2:
                continue
            # Same visit: both undated, or both dated on the same day. Mixed is unclear.
            if not any(service_date(primary) == service_date(item) for primary in primaries):
                continue
            reason, basis = unbundling_text(code_1, code_2, pair.data_source, pair.data_year)
            flags.append(
                Flag(
                    line_item_id=item.id,
                    flag_type="possible_unbundling",
                    severity=constants.UNBUNDLING_SEVERITY[pair.modifier_indicator],
                    reason=reason,
                    basis=basis,
                    data_source=pair.data_source,
                    data_year=pair.data_year,
                )
            )
    return flags
