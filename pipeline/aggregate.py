"""Summarize a list of dollar values into (min, median, max).

Pure, deterministic. Operates only on values we already decided are usable dollars
(see rates.py) -- it never invents a number. An empty list yields (None, None, None)
so the field stays null downstream rather than becoming a placeholder.

Because the result comes directly from a real list of numbers, the invariant
min <= median <= max holds by construction (property P3), and the result does not
depend on input order (property P4).
"""

from __future__ import annotations

import statistics
from typing import Optional


def summarize(
    values: list[float],
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Return (min, median, max) for a list of dollar values.

    Empty list -> (None, None, None). Median uses statistics.median (the average of
    the two middle values for an even count).
    """
    if not values:
        return (None, None, None)
    return (min(values), statistics.median(values), max(values))
