"""Reference data for the analyze handler. Read-only, injectable, missing = empty.

Holds the three reference lists /core consumes: PriceReference (reference.json),
QuantityLimit (quantity_limits.json), BundlePair (bundle_pairs.json). Built from dicts
for tests (each synthetic bill carries its own), or loaded from /data/processed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from contracts.types import BundlePair, PriceReference, QuantityLimit
from pipeline import jsonio


def _norm_code(code) -> str:
    return (str(code) if code is not None else "").strip().upper()


@dataclass
class ReferenceStore:
    price_references: list[PriceReference] = field(default_factory=list)
    quantity_limits: list[QuantityLimit] = field(default_factory=list)
    bundle_pairs: list[BundlePair] = field(default_factory=list)

    @classmethod
    def from_dicts(
        cls,
        price_references: list[dict] | None = None,
        quantity_limits: list[dict] | None = None,
        bundle_pairs: list[dict] | None = None,
    ) -> "ReferenceStore":
        return cls(
            price_references=[_price_ref(d) for d in (price_references or [])],
            quantity_limits=[_quantity_limit(d) for d in (quantity_limits or [])],
            bundle_pairs=[_bundle_pair(d) for d in (bundle_pairs or [])],
        )

    @classmethod
    def load(cls, processed_dir: str | Path) -> "ReferenceStore":
        processed_dir = Path(processed_dir)

        def read(name: str) -> list[dict]:
            path = processed_dir / name
            if not path.exists():
                return []
            data = jsonio.read_json(path)
            return data if isinstance(data, list) else []

        return cls.from_dicts(
            price_references=read("reference.json"),
            quantity_limits=read("quantity_limits.json"),
            bundle_pairs=read("bundle_pairs.json"),
        )

    def references_for(self, codes: set[str]) -> list[PriceReference]:
        """PriceReferences whose code is on the bill (normalized), sorted by code."""
        wanted = {_norm_code(c) for c in codes}
        hits = [r for r in self.price_references if _norm_code(r.code) in wanted]
        return sorted(hits, key=lambda r: r.code)


def _price_ref(d: dict) -> PriceReference:
    return PriceReference(
        code=d["code"],
        data_source=d["data_source"],
        data_year=d["data_year"],
        code_system=d.get("code_system"),
        medicare_price=d.get("medicare_price"),
        ma_range_low=d.get("ma_range_low"),
        ma_range_high=d.get("ma_range_high"),
    )


def _quantity_limit(d: dict) -> QuantityLimit:
    return QuantityLimit(
        code=d["code"],
        max_units=d["max_units"],
        data_source=d["data_source"],
        data_year=d["data_year"],
        code_system=d.get("code_system"),
    )


def _bundle_pair(d: dict) -> BundlePair:
    return BundlePair(
        code_1=d["code_1"],
        code_2=d["code_2"],
        modifier_indicator=d["modifier_indicator"],
        data_source=d["data_source"],
        data_year=d["data_year"],
    )
