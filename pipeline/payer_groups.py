"""Map a raw payer / plan name to one of the five normalized payer groups.

Pure, no I/O. The rule order is first-match-wins, case-insensitive, substring based.
Order matters: "gross" and "cash" are checked before plan-type keywords so a label
like "Cash (gross-of-discount)" still lands in the intended bucket per design.

If nothing matches, the raw name is treated as a commercial/negotiated plan. The
function is total: it returns one of the five enum values for any string and never
raises. This is asserted by property test P1.
"""

from __future__ import annotations

from contracts.types import PayerGroup

# Each tuple: (payer_group, list of lowercase substrings that select it).
# Checked in order; first group with any matching substring wins.
_RULES: list[tuple[PayerGroup, tuple[str, ...]]] = [
    ("gross", ("gross", "chargemaster", "charge master")),
    ("cash", ("cash", "self-pay", "self pay", "selfpay")),
    ("medicaid_managed", ("medicaid", "masshealth")),
    ("medicare_advantage", ("medicare advantage", "medicare adv", "ma plan")),
]

_DEFAULT: PayerGroup = "commercial"


def classify(raw_name: str) -> PayerGroup:
    """Return the normalized payer group for a raw payer/plan name.

    Total function: always returns one of the five PayerGroup values.
    """
    name = (raw_name or "").strip().lower()
    for group, needles in _RULES:
        if any(needle in name for needle in needles):
            return group
    return _DEFAULT
