"""Score one extraction against the ground truth.

Counts are additive: to combine bills, add their ``Counts`` and then divide (a micro-average:
add numerators and denominators, then divide). A rate with nothing to measure is ``None``
and is shown as ``n/a``.

Failure records name a bill id, a layout, a kind, and a line id. They never hold bill text.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Iterable, Sequence

from backend.extract.handler import WARN_EXTRACTION_UNAVAILABLE
from backend.extract.models import ExtractionResult
from contracts.types import LineItem

from .align import Alignment, cents, match, norm_code, same_qty

# Kinds of failure, in report order.
KINDS = (
    "extraction_fallback", "missing_line", "extra_line", "hallucinated_code",
    "code", "units", "charge", "date",
)


def rate(numerator: int, denominator: int) -> float | None:
    """numerator / denominator, or None if there is nothing to measure."""
    return None if denominator == 0 else numerator / denominator


@dataclass(frozen=True)
class Counts:
    """Additive counts for extraction. Every field is a non-negative whole number."""

    bills: int = 0
    fallback_bills: int = 0
    truth_lines: int = 0
    extracted_lines: int = 0
    matched: int = 0
    code_ok: int = 0
    units_ok: int = 0
    units_total: int = 0
    charge_ok: int = 0
    date_ok: int = 0
    date_total: int = 0
    hallucinated_codes: int = 0
    nocode_matched: int = 0
    nocode_confirmed: int = 0
    injection_extra_lines: int = 0

    def __add__(self, other: "Counts") -> "Counts":
        return Counts(**{f.name: getattr(self, f.name) + getattr(other, f.name) for f in fields(self)})

    @property
    def line_recall(self) -> float | None:
        return rate(self.matched, self.truth_lines)

    @property
    def line_precision(self) -> float | None:
        return rate(self.matched, self.extracted_lines)

    @property
    def code_exact(self) -> float | None:
        return rate(self.code_ok, self.matched)

    @property
    def units_exact(self) -> float | None:
        return rate(self.units_ok, self.units_total)

    @property
    def charge_exact(self) -> float | None:
        return rate(self.charge_ok, self.matched)

    @property
    def date_exact(self) -> float | None:
        return rate(self.date_ok, self.date_total)

    @property
    def confirmation_recall(self) -> float | None:
        return rate(self.nocode_confirmed, self.nocode_matched)


def total(counts: Iterable[Counts]) -> Counts:
    """Sum counts (micro-average when you then read the rates)."""
    result = Counts()
    for c in counts:
        result = result + c
    return result


@dataclass(frozen=True)
class Failure:
    """One thing that went wrong. ``line_id`` is a truth id (or an extracted id for an extra line)."""

    bill_id: str
    style: str
    kind: str
    line_id: str


@dataclass(frozen=True)
class BillExtractionScore:
    """The score for one bill in one layout."""

    bill_id: str
    style: str
    scenario: str
    counts: Counts
    alignment: Alignment
    failures: tuple[Failure, ...]


def is_fallback(result: ExtractionResult) -> bool:
    """True if extraction gave up (no lines and the 'unavailable' warning)."""
    return not result.line_items and WARN_EXTRACTION_UNAVAILABLE in result.warnings


def score_bill(
    bill_id: str,
    style: str,
    scenario: str,
    truth_lines: Sequence[LineItem],
    result: ExtractionResult,
) -> BillExtractionScore:
    """Score ``result`` against ``truth_lines``."""
    extracted = list(result.line_items)
    alignment = match(truth_lines, extracted)
    needs_confirmation = {c.line_item_id: c.needs_confirmation for c in result.line_confidence}

    failures: list[Failure] = []

    def fail(kind: str, line_id: str) -> None:
        failures.append(Failure(bill_id, style, kind, str(line_id)))

    fallback = is_fallback(result)
    if fallback:
        fail("extraction_fallback", "")

    code_ok = units_ok = units_total = charge_ok = date_ok = date_total = 0
    hallucinated = nocode_matched = nocode_confirmed = 0

    for pair in alignment.pairs:
        t, e = pair.truth, pair.extracted
        t_code, e_code = norm_code(t.code), norm_code(e.code)

        if t_code == e_code:
            code_ok += 1
        elif t_code is None and e_code is not None:
            hallucinated += 1
            fail("hallucinated_code", t.id)
        else:
            fail("code", t.id)

        if t.quantity is not None:
            units_total += 1
            if same_qty(t.quantity, e.quantity):
                units_ok += 1
            else:
                fail("units", t.id)

        if cents(t.billed_amount) == cents(e.billed_amount):
            charge_ok += 1
        else:
            fail("charge", t.id)

        if t.date_of_service is not None:
            date_total += 1
            if t.date_of_service == e.date_of_service:
                date_ok += 1
            else:
                fail("date", t.id)

        if t_code is None:
            nocode_matched += 1
            if needs_confirmation.get(e.id, False):
                nocode_confirmed += 1

    for line in alignment.missing:
        fail("missing_line", line.id)
    for line in alignment.extra:
        fail("extra_line", line.id)

    counts = Counts(
        bills=1,
        fallback_bills=1 if fallback else 0,
        truth_lines=len(truth_lines),
        extracted_lines=len(extracted),
        matched=len(alignment.pairs),
        code_ok=code_ok,
        units_ok=units_ok,
        units_total=units_total,
        charge_ok=charge_ok,
        date_ok=date_ok,
        date_total=date_total,
        hallucinated_codes=hallucinated,
        nocode_matched=nocode_matched,
        nocode_confirmed=nocode_confirmed,
        injection_extra_lines=len(alignment.extra) if scenario == "injection" else 0,
    )
    kind_order = {k: i for i, k in enumerate(KINDS)}
    failures.sort(key=lambda f: (kind_order.get(f.kind, len(KINDS)), f.line_id))
    return BillExtractionScore(bill_id, style, scenario, counts, alignment, tuple(failures))


__all__ = [
    "KINDS", "rate", "Counts", "total", "Failure", "BillExtractionScore", "is_fallback", "score_bill",
]
