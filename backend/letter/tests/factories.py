"""Test helpers for letter tests. Synthetic values only."""

from __future__ import annotations

from backend.letter._contracts import Flag, LineItem
from backend.letter.models import LetterRequest, PatientFields

REASON = (
    "The billed amount of $1,234.50 per unit may be worth asking about. "
    "It is about 1.5 times the Medicare reference price we have on file for this code."
)
BASIS = "Medicare reference price for code 99213: $823.00 per unit. Source: CMS PFS, 2026."


def make_line(
    id: str = "1",
    *,
    code: str | None = "99213",
    amount: float = 1234.5,
    date_of_service: str | None = "2026-03-04",
    description: str = "Office visit",
) -> LineItem:
    return LineItem(
        id=id,
        description=description,
        billed_amount=amount,
        code=code,
        code_system="CPT" if code else None,
        date_of_service=date_of_service,
    )


def make_flag(
    line_item_id: str = "1",
    *,
    flag_type: str = "price_above_reference",
    reason: str = REASON,
    basis: str = BASIS,
    data_source: str | None = "CMS PFS",
    data_year: int | None = 2026,
) -> Flag:
    return Flag(
        line_item_id=line_item_id,
        flag_type=flag_type,  # type: ignore[arg-type]
        severity="medium",
        reason=reason,
        basis=basis,
        data_source=data_source,
        data_year=data_year,
    )


def make_patient(**overrides: str) -> PatientFields:
    base = dict(
        name="Jane Doe",
        account_number="AC-55512345",
        hospital="Riverside General",
        date="October 24, 2026",
        notes="",
    )
    base.update(overrides)
    return PatientFields(**base)


def make_request(
    letter_type: str = "coding_review",
    *,
    patient: PatientFields | None = None,
    flags: list[Flag] | None = None,
    lines: list[LineItem] | None = None,
) -> LetterRequest:
    return LetterRequest(
        letter_type=letter_type,
        patient=patient or make_patient(),
        flags=flags if flags is not None else [],
        line_items=lines if lines is not None else [],
    )
