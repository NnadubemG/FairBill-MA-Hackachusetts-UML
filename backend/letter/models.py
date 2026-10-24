"""Letter wrapper types (not contracts).

``LetterDraft`` itself comes from ``/contracts``. These types describe the request that
comes in and the result that goes out.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from ._contracts import Flag, LetterDraft, LineItem

ITEMIZED_BILL: Final[str] = "itemized_bill"
CODING_REVIEW: Final[str] = "coding_review"
FINANCIAL_ASSISTANCE: Final[str] = "financial_assistance"
LETTER_TYPES: Final[tuple[str, ...]] = (ITEMIZED_BILL, CODING_REVIEW, FINANCIAL_ASSISTANCE)


class InvalidLetterType(ValueError):
    """Raised for an unknown letter type. A caller bug, so it does not fall back.

    The API layer should turn this into a 400 response.
    """


@dataclass(frozen=True)
class PatientFields:
    """What the patient typed. Inserted by the template only; never sent to the model.

    All fields are plain text and may be empty (an empty field becomes a placeholder).
    """

    name: str = ""
    account_number: str = ""
    hospital: str = ""
    date: str = ""
    notes: str = ""


@dataclass(frozen=True)
class LetterRequest:
    """Everything needed to build a letter."""

    letter_type: str
    patient: PatientFields = field(default_factory=PatientFields)
    flags: list[Flag] = field(default_factory=list)
    line_items: list[LineItem] = field(default_factory=list)


@dataclass(frozen=True)
class LetterResult:
    """What the handler returns. Nothing here is persisted.

    - ``draft``: the contract ``LetterDraft`` (subject, body, referenced_line_item_ids).
    - ``used_fallback``: True if the reason paragraph is the fixed fallback, not model text.
    - ``warnings``: fixed, generic text only. Never contains patient or bill content.
    """

    draft: LetterDraft
    used_fallback: bool = True
    warnings: list[str] = field(default_factory=list)


__all__ = [
    "ITEMIZED_BILL",
    "CODING_REVIEW",
    "FINANCIAL_ASSISTANCE",
    "LETTER_TYPES",
    "InvalidLetterType",
    "PatientFields",
    "LetterRequest",
    "LetterResult",
]
