"""Test helpers: build Flag objects. Synthetic values only."""

from __future__ import annotations

from backend.explain._contracts import Flag

REASON = (
    "The billed amount of $1,234.50 per unit may be worth asking about. "
    "It is about 1.5 times the Medicare reference price we have on file for this code."
)
BASIS = (
    "Medicare reference price for code 99213: $823.00 per unit. "
    "Source: CMS PFS, 2026."
)
GOOD_TEXT = (
    "The price of $1,234.50 per unit may be worth asking about. "
    "It is about 1.5 times the Medicare reference price of $823.00. "
    "Can you explain how this price was set?"
)


def make_flag(
    *,
    line_item_id: str = "1",
    flag_type: str = "price_above_reference",
    severity: str = "medium",
    reason: str = REASON,
    basis: str = BASIS,
    data_source: str | None = "CMS PFS",
    data_year: int | None = 2026,
    explanation: str | None = None,
) -> Flag:
    return Flag(
        line_item_id=line_item_id,
        flag_type=flag_type,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        reason=reason,
        basis=basis,
        data_source=data_source,
        data_year=data_year,
        explanation=explanation,
    )
