"""Extraction wrapper types.

These compose the contract ``LineItem`` (from ``/contracts``); they do NOT redefine
it. The committed ``LineItem`` schema has no ``confidence`` / ``needs_confirmation``
field, and we do not add fields to the shared contract. Instead, the extraction layer
carries those per-line signals alongside the contract objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ._contracts import LineItem

Confidence = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class LineConfidence:
    """Per-line confidence signal, keyed to a ``LineItem.id``.

    Lives outside the contract so the shared ``LineItem`` stays backward compatible.
    """

    line_item_id: str
    confidence: Confidence
    needs_confirmation: bool


@dataclass(frozen=True)
class BillMetadata:
    """Bill-level fields extracted alongside the line items.

    Every field is nullable: we never invent a value we did not read from the bill.
    """

    hospital_name: str | None = None
    statement_date: str | None = None  # ISO 8601 (YYYY-MM-DD) or None
    total: float | None = None


@dataclass(frozen=True)
class ExtractionResult:
    """What the extraction handler returns. Nothing here is persisted.

    - ``line_items``: validated contract ``LineItem`` objects.
    - ``metadata``: bill-level metadata (nullable fields).
    - ``line_confidence``: one entry per line item, by ``line_item_id``.
    - ``warnings``: human-readable, non-sensitive notes (e.g. dropped invalid line,
      code validation unavailable, extraction fell back). Never contains bill content.
    """

    line_items: list[LineItem] = field(default_factory=list)
    metadata: BillMetadata = field(default_factory=BillMetadata)
    line_confidence: list[LineConfidence] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


__all__ = [
    "Confidence",
    "LineConfidence",
    "BillMetadata",
    "ExtractionResult",
    "LineItem",
]
