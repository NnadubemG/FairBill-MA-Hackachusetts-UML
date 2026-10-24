"""Match extracted lines to ground-truth lines, one to one.

The model chooses its own line ids, so ids are never compared. Lines are matched by their
content, in stages. In each stage the still-unmatched lines are grouped by a key and paired
in a fixed order. The result does not depend on the order of the extracted lines.

Stages (a rule of thumb, printed in the report):
  1. code, amount and quantity all equal
  2. code and amount equal                 (quantity differs)
  3. amount equal                          (code differs)
  4. code equal, and the code is not None  (amount differs)

So one wrong field still gives a match, and shows up in that field's error rate. Two wrong
fields give a missing line plus an extra line. Lines with no code are never matched by the
code alone (any two uncoded lines would look alike).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Callable, Hashable, Sequence

from contracts.types import LineItem

STAGES = 4


def norm_code(code: object) -> str | None:
    """Upper-case code with all whitespace removed, or None."""
    if not isinstance(code, str):
        return None
    cleaned = "".join(code.split()).upper()
    return cleaned or None


def cents(amount: object) -> int | None:
    """Amount in whole cents, or None if it is not a usable number."""
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        return None
    try:
        number = Decimal(str(amount))
        if not number.is_finite():
            return None
        return int((number * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return None


def norm_qty(quantity: object) -> float | None:
    """Quantity as a float, or None."""
    if isinstance(quantity, bool) or not isinstance(quantity, (int, float)):
        return None
    value = float(quantity)
    return value if math.isfinite(value) else None


def same_qty(a: object, b: object) -> bool:
    """Equal quantities (both None counts as equal)."""
    x, y = norm_qty(a), norm_qty(b)
    if x is None or y is None:
        return x is None and y is None
    return abs(x - y) < 1e-9


def _sort_key(line: LineItem) -> tuple:
    qty = norm_qty(line.quantity)
    amount = cents(line.billed_amount)
    return (
        norm_code(line.code) or "",
        amount if amount is not None else -1,
        qty if qty is not None else -1.0,
        line.date_of_service or "",
        str(line.id),
        str(line.description),
    )


def _key_stage1(line: LineItem) -> Hashable | None:
    amount = cents(line.billed_amount)
    return None if amount is None else (norm_code(line.code), amount, norm_qty(line.quantity))


def _key_stage2(line: LineItem) -> Hashable | None:
    amount = cents(line.billed_amount)
    return None if amount is None else (norm_code(line.code), amount)


def _key_stage3(line: LineItem) -> Hashable | None:
    return cents(line.billed_amount)


def _key_stage4(line: LineItem) -> Hashable | None:
    return norm_code(line.code)


_STAGE_KEYS: tuple[Callable[[LineItem], Hashable | None], ...] = (
    _key_stage1, _key_stage2, _key_stage3, _key_stage4,
)


@dataclass(frozen=True)
class Pair:
    """A truth line matched to an extracted line."""

    truth: LineItem
    extracted: LineItem
    stage: int  # 1 to 4 (see the module docstring)


@dataclass(frozen=True)
class Alignment:
    """The result of matching. ``missing`` are truth lines; ``extra`` are extracted lines."""

    pairs: tuple[Pair, ...]
    missing: tuple[LineItem, ...]
    extra: tuple[LineItem, ...]

    def truth_id_for(self, extracted_id: str) -> str | None:
        """The truth line id matched to an extracted line id, or None if unmatched."""
        for pair in self.pairs:
            if pair.extracted.id == extracted_id:
                return pair.truth.id
        return None


def match(truth: Sequence[LineItem], extracted: Sequence[LineItem]) -> Alignment:
    """Match ``extracted`` lines to ``truth`` lines. See the module docstring."""
    t_lines = sorted(truth, key=_sort_key)
    e_lines = sorted(extracted, key=_sort_key)
    free_t = list(range(len(t_lines)))  # positions still unmatched, in sorted order
    free_e = list(range(len(e_lines)))
    pairs: list[Pair] = []

    for stage, key_of in enumerate(_STAGE_KEYS, start=1):
        if not free_t or not free_e:
            break
        e_by_key: dict[Hashable, list[int]] = {}
        for pos in free_e:
            key = key_of(e_lines[pos])
            if key is not None:
                e_by_key.setdefault(key, []).append(pos)

        taken: dict[Hashable, int] = {}
        matched_t: set[int] = set()
        matched_e: set[int] = set()
        for pos in free_t:
            key = key_of(t_lines[pos])
            candidates = e_by_key.get(key, []) if key is not None else []
            nth = taken.get(key, 0)
            if nth >= len(candidates):
                continue
            taken[key] = nth + 1
            e_pos = candidates[nth]
            pairs.append(Pair(truth=t_lines[pos], extracted=e_lines[e_pos], stage=stage))
            matched_t.add(pos)
            matched_e.add(e_pos)

        free_t = [p for p in free_t if p not in matched_t]
        free_e = [p for p in free_e if p not in matched_e]

    return Alignment(
        pairs=tuple(pairs),
        missing=tuple(t_lines[p] for p in free_t),
        extra=tuple(e_lines[p] for p in free_e),
    )


__all__ = [
    "STAGES", "norm_code", "cents", "norm_qty", "same_qty", "Pair", "Alignment", "match",
]
