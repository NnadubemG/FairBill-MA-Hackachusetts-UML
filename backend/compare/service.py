"""Pure lookup functions over a Store. No I/O, no server, no fabrication.

Reuses the pipeline's aggregate.summarize so statewide stats obey min<=median<=max and
match the rest of the system. Every result carries the framing note.
"""

from __future__ import annotations

from pipeline.aggregate import summarize

from .framing import FRAMING_NOTE
from .store import Store, _norm_code

# Fixed serialization order for payer groups (deterministic output).
PAYER_GROUP_ORDER = ["commercial", "medicare_advantage", "medicaid_managed", "cash", "gross"]


def list_procedures(store: Store) -> dict:
    """All curated procedures in stable code order, plus the framing note."""
    return {
        "procedures": [store.procedures[c] for c in store.procedures_order],
        "framing_note": FRAMING_NOTE,
    }


def _collect_data_years(hospitals: list[dict], medicare: dict | None) -> list[int]:
    years: set[int] = set()
    for h in hospitals:
        for ps in h["price_stats"].values():
            y = ps.get("data_year")
            if y is not None:
                years.add(y)
    if medicare and medicare.get("data_year") is not None:
        years.add(medicare["data_year"])
    return sorted(years)


def _hospital_entry(store: Store, hospital_id: str, stats: list[dict]) -> dict:
    info = store.hospitals.get(hospital_id, {})
    by_group: dict[str, dict] = {}
    for ps in stats:
        by_group[ps["payer_group"]] = ps
    # Serialize payer groups in fixed order for determinism.
    ordered = {g: by_group[g] for g in PAYER_GROUP_ORDER if g in by_group}

    missing_note = None
    if "commercial" not in ordered and ordered:
        missing_note = "no commercial negotiated rates in the source files"

    return {
        "hospital_id": hospital_id,
        "name": info.get("name"),
        "city": info.get("city"),
        "type": info.get("type"),
        "price_stats": ordered,
        "chia_tier": store.chia_by_hospital.get(hospital_id),
        "missing_note": missing_note,
    }


def compare(store: Store, code: str) -> dict:
    """Compare a single procedure code across hospitals. Missing values stay null."""
    code = _norm_code(code)

    if code not in store.procedures:
        return {
            "code": code,
            "found": False,
            "plain_label": None,
            "code_system": None,
            "hospitals": [],
            "medicare": None,
            "statewide": {"min": None, "median": None, "max": None},
            "data_years": [],
            "note": "Code not found in the curated list.",
            "framing_note": FRAMING_NOTE,
        }

    proc = store.procedures[code]
    price_rows = store.prices_by_code.get(code, [])

    # Group price rows by hospital.
    by_hospital: dict[str, list[dict]] = {}
    for ps in price_rows:
        by_hospital.setdefault(ps["hospital_id"], []).append(ps)

    hospitals = [
        _hospital_entry(store, hid, by_hospital[hid])
        for hid in sorted(by_hospital)
    ]

    medicare = store.medicare_by_code.get(code)

    # Statewide: one representative value per hospital = its commercial median_rate.
    commercial_medians = []
    for h in hospitals:
        commercial = h["price_stats"].get("commercial")
        if commercial and commercial.get("median_rate") is not None:
            commercial_medians.append(commercial["median_rate"])
    lo, med, hi = summarize(commercial_medians)

    return {
        "code": code,
        "found": True,
        "plain_label": proc.get("plain_label"),
        "code_system": proc.get("code_system"),
        "hospitals": hospitals,
        "medicare": medicare,
        "statewide": {"min": lo, "median": med, "max": hi},
        "data_years": _collect_data_years(hospitals, medicare),
        "framing_note": FRAMING_NOTE,
    }
