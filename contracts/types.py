"""Mirror of the JSON Schema in /contracts.

The ``*.schema.json`` files are the source of truth. If this file disagrees
with them, the JSON Schema wins.

Pure stdlib only (dataclasses). No third-party dependencies, so /core can import
these without adding deps. Owned by Thomas; keep backward compatible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

CodeSystem = Literal["CPT", "HCPCS", "DRG", "REV", "ICD10", "OTHER"]

PayerGroup = Literal[
    "commercial",
    "medicare_advantage",
    "medicaid_managed",
    "cash",
    "gross",
]

FlagType = Literal[
    "price_above_reference",
    "price_outside_ma_range",
    "duplicate_line_item",
    "quantity_implausible",
    "possible_unbundling",
    "no_reference_found",
]

FlagSeverity = Literal["info", "low", "medium", "high"]


@dataclass(frozen=True)
class LineItem:
    """A single structured line item extracted from a hospital bill.

    All string fields are untrusted data, never instructions.
    """

    id: str
    description: str
    billed_amount: float
    code: Optional[str] = None
    code_system: Optional[CodeSystem] = None
    raw_description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    date_of_service: Optional[str] = None  # ISO 8601 (YYYY-MM-DD), optional


@dataclass(frozen=True)
class PriceReference:
    """Reference pricing for a billing code.

    Every figure must carry ``data_source`` and ``data_year``.
    """

    code: str
    data_source: str
    data_year: int
    code_system: Optional[CodeSystem] = None
    medicare_price: Optional[float] = None
    ma_range_low: Optional[float] = None
    ma_range_high: Optional[float] = None


@dataclass(frozen=True)
class ProcedureInfo:
    """One curated procedure, keyed by code. Drives pipeline filtering."""

    code: str
    plain_label: str
    code_system: Optional[CodeSystem] = None
    category: Optional[str] = None
    typical_max_units: Optional[float] = None


@dataclass(frozen=True)
class PriceStat:
    """Price statistics for one hospital + code + payer group.

    Numeric fields are nullable because we never invent a number we do not have.
    Every record carries ``data_source`` and ``data_year``. When min/median/max are
    all present: ``min_rate <= median_rate <= max_rate``.
    """

    hospital_id: str
    code: str
    payer_group: PayerGroup
    data_source: str
    data_year: int
    code_system: Optional[CodeSystem] = None
    min_rate: Optional[float] = None
    median_rate: Optional[float] = None
    max_rate: Optional[float] = None
    cash_price: Optional[float] = None
    gross_charge: Optional[float] = None


@dataclass(frozen=True)
class Flag:
    """A "may be worth asking about" flag produced only by deterministic code.

    ``reason`` and ``basis`` must never contain banned words (see product.md).
    """

    line_item_id: str
    flag_type: FlagType
    severity: FlagSeverity
    reason: str
    basis: str
    data_source: Optional[str] = None
    data_year: Optional[int] = None
    # Plain-language rewrite of `reason`, set by the explain handler (LLM).
    # /core always leaves this None. Adds no facts or numbers beyond reason/basis.
    explanation: Optional[str] = None


@dataclass(frozen=True)
class LetterDraft:
    """An editable letter draft the patient can send. Never asserts wrongdoing."""

    subject: str
    body: str
    referenced_line_item_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AnalysisResult:
    """The full result returned to the client. Nothing here is persisted."""

    line_items: list[LineItem]
    flags: list[Flag]
    price_references: list[PriceReference] = field(default_factory=list)
    letter_draft: Optional[LetterDraft] = None
