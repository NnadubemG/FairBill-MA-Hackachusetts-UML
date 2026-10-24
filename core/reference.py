"""Code normalization and reference lookup.

Bill text is untrusted. A code is usable only if it matches a strict character
pattern; anything else is treated as "no code" and is never echoed into output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Optional, Sequence

from contracts.types import LineItem, PriceReference

_CODE_PATTERN = re.compile(r"[A-Za-z0-9.\-]{1,12}")

# Bills and reference files format these inconsistently (0450 vs 450), so
# leading zeros are ignored. In CPT/HCPCS they are significant (00100 != 100).
_ZERO_PADDED_SYSTEMS = frozenset({"REV", "DRG"})


def clean_code(code: object) -> Optional[str]:
    """Strip, validate, and uppercase a code. None if unusable."""
    if not isinstance(code, str):
        return None
    stripped = code.strip()
    if _CODE_PATTERN.fullmatch(stripped) is None:
        return None
    return stripped.upper()


def normalize_code(code: object, code_system: Optional[str]) -> Optional[str]:
    """Normalize a code for matching. Returns None if the code is unusable."""
    cleaned = clean_code(code)
    if cleaned is None:
        return None
    if code_system in _ZERO_PADDED_SYSTEMS:
        return cleaned.lstrip("0") or "0"
    return cleaned


MatchStatus = Literal["found", "not_found", "ambiguous", "unusable"]


@dataclass(frozen=True)
class Match:
    """Result of looking up a line item's reference.

    found:      `ref` is the reference to use.
    not_found:  a usable code with no matching reference.
    ambiguous:  more than one possible reference; callers must stay silent.
    unusable:   the item has no code, or the code failed validation.
    """

    status: MatchStatus
    ref: Optional[PriceReference] = None


_NOT_FOUND = Match("not_found")
_AMBIGUOUS = Match("ambiguous")
_UNUSABLE = Match("unusable")


def _resolve(candidates: Sequence[PriceReference]) -> Match:
    """Pick the newest reference. A tie between different refs is ambiguous."""
    unique = list(dict.fromkeys(candidates))  # drop exact duplicates, keep order
    newest_year = max(ref.data_year for ref in unique)
    newest = [ref for ref in unique if ref.data_year == newest_year]
    if len(newest) == 1:
        return Match("found", newest[0])
    return _AMBIGUOUS


class ReferenceIndex:
    """Index of PriceReference objects for lookup by code and code system."""

    def __init__(self, refs: Sequence[PriceReference]) -> None:
        self.has_refs: bool = len(refs) > 0
        self._by_key: dict[tuple[str, Optional[str]], list[PriceReference]] = {}
        self._by_raw: dict[str, list[PriceReference]] = {}
        for ref in refs:
            key_code = normalize_code(ref.code, ref.code_system)
            raw_code = clean_code(ref.code)
            if key_code is None or raw_code is None:
                continue  # unusable reference code: ignore it
            self._by_key.setdefault((key_code, ref.code_system), []).append(ref)
            self._by_raw.setdefault(raw_code, []).append(ref)

    def lookup(self, item: LineItem) -> Match:
        code = normalize_code(item.code, item.code_system)
        if code is None:
            return _UNUSABLE

        if item.code_system is not None:
            candidates = self._by_key.get((code, item.code_system), [])
            return _resolve(candidates) if candidates else _NOT_FOUND

        # No code system on the item: exact code only, and only if every
        # reference with that code is in one system.
        candidates = self._by_raw.get(code, [])
        if not candidates:
            return _NOT_FOUND
        if len({ref.code_system for ref in candidates}) > 1:
            return _AMBIGUOUS
        return _resolve(candidates)
