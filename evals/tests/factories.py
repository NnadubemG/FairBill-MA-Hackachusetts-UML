"""Test helpers for evals tests. Synthetic values only."""

from __future__ import annotations

from backend.extract.handler import WARN_EXTRACTION_UNAVAILABLE
from backend.extract.models import BillMetadata, ExtractionResult, LineConfidence
from contracts.types import LineItem


def line(
    id: str,
    code: str | None = "99213",
    amount: float = 150.0,
    qty: float | None = 1,
    date: str | None = "2026-03-04",
    description: str = "x",
) -> LineItem:
    return LineItem(
        id=id,
        description=description,
        billed_amount=amount,
        code=code,
        code_system="CPT" if code else None,
        quantity=qty,
        date_of_service=date,
    )


def result(lines: list[LineItem], *, confirmed: set[str] | None = None) -> ExtractionResult:
    """An extraction result. Lines whose id is in ``confirmed`` need confirmation."""
    confirmed = confirmed or set()
    return ExtractionResult(
        line_items=list(lines),
        metadata=BillMetadata(),
        line_confidence=[
            LineConfidence(li.id, "low" if li.id in confirmed else "high", li.id in confirmed)
            for li in lines
        ],
        warnings=[],
    )


def fallback_result() -> ExtractionResult:
    return ExtractionResult(
        line_items=[], metadata=BillMetadata(), line_confidence=[],
        warnings=[WARN_EXTRACTION_UNAVAILABLE],
    )


def truth_lines() -> list[LineItem]:
    return [
        line("1", "99213", 150.0, 1, "2026-03-04"),
        line("2", "85025", 42.0, 2, "2026-03-04"),
        line("3", None, 1800.0, None, None),
    ]


def renamed(lines: list[LineItem], prefix: str = "x") -> list[LineItem]:
    """The same lines with different ids (the model picks its own ids)."""
    from dataclasses import replace

    return [replace(li, id=f"{prefix}{i}") for i, li in enumerate(lines)]
