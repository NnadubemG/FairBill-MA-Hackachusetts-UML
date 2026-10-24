"""Tunable constants and fixed vocabulary for the checks engine."""

from __future__ import annotations

from decimal import Decimal
from typing import Final

from contracts.types import FlagSeverity, FlagType

# PLACEHOLDER. A bill is flagged by price_above_reference when the per-unit amount
# exceeds this multiple of the Medicare price. Tune once real data is seen.
MEDICARE_MULTIPLE: Final[Decimal] = Decimal("3.0")

# Severity is for display order only. It never implies wrongdoing.
SEVERITY: Final[dict[FlagType, FlagSeverity]] = {
    "price_outside_ma_range": "medium",
    "price_above_reference": "low",
    "duplicate_line_item": "medium",  # when the duplicated items have a date
    "no_reference_found": "info",
    "quantity_implausible": "low",
}
# possible_unbundling severity depends on the edit's modifier indicator.
UNBUNDLING_SEVERITY: Final[dict[str, FlagSeverity]] = {"0": "medium", "1": "low"}
DUPLICATE_UNDATED_SEVERITY: Final[FlagSeverity] = "low"

# Words and phrases that must never appear in a flag's reason or basis.
# Keep in sync with .kiro/steering/product.md.
BANNED_WORDS: Final[tuple[str, ...]] = (
    "overcharged",
    "illegal",
    "fraud",
    "incorrect charge",
    "you should dispute",
    "you are owed",
)
