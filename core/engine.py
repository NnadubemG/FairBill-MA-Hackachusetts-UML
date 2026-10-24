"""Entry point for the deterministic checks engine."""

from __future__ import annotations

from typing import Sequence

from contracts.types import Flag, LineItem, PriceReference


def analyze(items: Sequence[LineItem], refs: Sequence[PriceReference]) -> list[Flag]:
    """Return "may be worth asking about" flags for the given line items.

    Pure: no network, no file access, no randomness. Same input, same output.
    Stub until the checks are added (tasks 3 to 5 of the core-checks spec).
    """
    return []
