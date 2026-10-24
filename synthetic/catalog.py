"""Fictional procedure catalog and reference prices for synthetic bills.

Every price here is made up for testing and labelled `synthetic-demo`. None of it is real,
and none of it should ever be shown to a patient as a real reference price.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

from contracts.types import BundlePair, CodeSystem, PriceReference, QuantityLimit

SYNTHETIC_SOURCE: Final = "synthetic-demo"
SYNTHETIC_YEAR: Final = 2026

# Reference range relative to the fictional Medicare price M (see design.md):
# low = 1.1 * M, high = 2.0 * M. Normal amounts are at most 1.5 * M.
RANGE_LOW_PCT: Final = 110
RANGE_HIGH_PCT: Final = 200
NORMAL_MIN_PCT: Final = 110
NORMAL_MAX_PCT: Final = 150
HIGH_PRICE_FACTOR: Final = 10  # anomalous unit price = 10 * ma_range_high

HOSPITAL_NAMES: Final = (
    "Example Valley Medical Center (FICTIONAL)",
    "Sample Harbor Hospital (FICTIONAL)",
    "Demo Hills Health (FICTIONAL)",
)


def cents(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def pct(value: Decimal, percent: int) -> Decimal:
    return cents(value * percent / 100)


@dataclass(frozen=True)
class CatalogEntry:
    code: str  # as printed on a bill
    code_system: CodeSystem
    plain_label: str
    printed: str  # abbreviated description as printed
    medicare_price: Decimal  # fictional, per unit
    max_units: int  # largest normal quantity
    unit: str
    reference_code: str = ""  # code as stored in reference data, if different
    unbundle_only: bool = False  # appears only in the `unbundling` scenario

    @property
    def ref_code(self) -> str:
        return self.reference_code or self.code


CATALOG: Final[tuple[CatalogEntry, ...]] = (
    CatalogEntry("99285", "CPT", "Emergency room visit, high complexity", "ER VISIT LVL5", Decimal("250.00"), 1, "each"),
    CatalogEntry("99284", "CPT", "Emergency room visit, moderate complexity", "ER VISIT LVL4", Decimal("180.00"), 1, "each"),
    CatalogEntry("71046", "CPT", "Chest X-ray, 2 views", "XR CHEST 2V", Decimal("40.00"), 1, "each"),
    CatalogEntry("80053", "CPT", "Comprehensive metabolic blood panel", "CMP PANEL", Decimal("15.00"), 1, "each"),
    CatalogEntry("85025", "CPT", "Complete blood count with differential", "CBC W/DIFF", Decimal("10.50"), 1, "each"),
    CatalogEntry("93000", "CPT", "Electrocardiogram (ECG) tracing", "EKG 12 LEAD", Decimal("17.25"), 1, "each"),
    CatalogEntry("96374", "CPT", "IV push of a single medication", "IV PUSH SNGL", Decimal("60.00"), 1, "each"),
    CatalogEntry("J1100", "HCPCS", "Dexamethasone injection, up to 1 mg", "DEXAMETHASONE INJ", Decimal("1.50"), 8, "each"),
    # Revenue code printed zero-padded on the bill but stored unpadded in reference data,
    # which exercises /core's REV normalization end to end.
    CatalogEntry("0120", "REV", "Room and board, semi-private", "R&B SEMI-PVT", Decimal("900.00"), 3, "day", reference_code="120"),
    # Part of 93000 (complete ECG) in the demo bundle pair below. Never sampled for ordinary bills.
    CatalogEntry("93005", "CPT", "Electrocardiogram tracing only", "EKG TRACING ONLY", Decimal("9.00"), 1, "each", unbundle_only=True),
)

# Entries ordinary bills are built from (everything except unbundle_only).
NORMAL_CATALOG: Final[tuple[CatalogEntry, ...]] = tuple(e for e in CATALOG if not e.unbundle_only)

BUNDLE_PRIMARY_CODE: Final = "93000"
BUNDLE_SECONDARY_CODE: Final = "93005"


@dataclass(frozen=True)
class UnknownEntry:
    """A code that is deliberately NOT in the reference data."""

    code: str
    code_system: CodeSystem
    plain_label: str
    printed: str
    unit_price: Decimal


UNKNOWN_CODES: Final[tuple[UnknownEntry, ...]] = (
    UnknownEntry("Z9101", "HCPCS", "Supply kit (fictional item)", "SPECIAL SUPPLY KIT", Decimal("75.00")),
    UnknownEntry("Z9102", "HCPCS", "Procedure room service (fictional item)", "PROC ROOM SVC", Decimal("220.00")),
)


def reference_for(entry: CatalogEntry) -> PriceReference:
    return PriceReference(
        code=entry.ref_code,
        code_system=entry.code_system,
        medicare_price=float(entry.medicare_price),
        ma_range_low=float(pct(entry.medicare_price, RANGE_LOW_PCT)),
        ma_range_high=float(pct(entry.medicare_price, RANGE_HIGH_PCT)),
        data_source=SYNTHETIC_SOURCE,
        data_year=SYNTHETIC_YEAR,
    )


def all_references() -> list[PriceReference]:
    return [reference_for(entry) for entry in CATALOG]


def all_quantity_limits() -> list[QuantityLimit]:
    """A fictional limit for every catalog entry: its largest normal quantity."""
    return [
        QuantityLimit(
            code=entry.ref_code,
            code_system=entry.code_system,
            max_units=entry.max_units,
            data_source=SYNTHETIC_SOURCE,
            data_year=SYNTHETIC_YEAR,
        )
        for entry in CATALOG
    ]


def all_bundle_pairs() -> list[BundlePair]:
    """One fictional pair: 93005 is normally part of 93000. Indicator "0": not billed together."""
    return [
        BundlePair(
            code_1=BUNDLE_PRIMARY_CODE,
            code_2=BUNDLE_SECONDARY_CODE,
            modifier_indicator="0",
            data_source=SYNTHETIC_SOURCE,
            data_year=SYNTHETIC_YEAR,
        )
    ]
