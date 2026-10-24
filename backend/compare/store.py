"""In-memory index over the processed JSON bundles. Read-only.

Loads the five files once and builds dict indexes for fast lookup. A missing file is
treated as empty, so the service still returns well-formed results. Reuses the pipeline's
deterministic JSON reader.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pipeline import jsonio


def _norm_code(code: str) -> str:
    return (code or "").strip().upper()


@dataclass
class Store:
    procedures: dict[str, dict] = field(default_factory=dict)
    procedures_order: list[str] = field(default_factory=list)
    hospitals: dict[str, dict] = field(default_factory=dict)
    prices_by_code: dict[str, list[dict]] = field(default_factory=dict)
    medicare_by_code: dict[str, dict] = field(default_factory=dict)
    chia_by_hospital: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def from_dicts(
        cls,
        procedures: list[dict] | None = None,
        hospitals: list[dict] | None = None,
        prices: list[dict] | None = None,
        medicare: list[dict] | None = None,
        chia: list[dict] | None = None,
    ) -> "Store":
        store = cls()
        for p in procedures or []:
            code = _norm_code(p["code"])
            if code not in store.procedures:
                store.procedures_order.append(code)
            store.procedures[code] = p
        for h in hospitals or []:
            store.hospitals[h["id"]] = h
        for ps in prices or []:
            store.prices_by_code.setdefault(_norm_code(ps["code"]), []).append(ps)
        for m in medicare or []:
            # First entry per code wins (pipeline already dedups).
            store.medicare_by_code.setdefault(_norm_code(m["code"]), m)
        for c in chia or []:
            store.chia_by_hospital.setdefault(c["hospital_id"], c)
        # Stable procedure order by code.
        store.procedures_order.sort()
        return store

    @classmethod
    def load(cls, processed_dir: str | Path) -> "Store":
        processed_dir = Path(processed_dir)

        def read(name: str) -> list[dict]:
            path = processed_dir / name
            if not path.exists():
                return []
            data = jsonio.read_json(path)
            return data if isinstance(data, list) else []

        return cls.from_dicts(
            procedures=read("procedures.json"),
            hospitals=read("hospitals.json"),
            prices=read("prices.json"),
            medicare=read("medicare.json"),
            chia=read("chia_tiers.json"),
        )
