"""Stage: procedures.json -> /data/processed/quantity_limits.json.

Emits one QuantityLimit (contracts/quantity-limit.schema.json) per curated procedure that
has a typical_max_units. /core uses these to flag quantities that may be worth asking
about; /core never invents a limit, so this stage is the only source.

Rules:
- No record when typical_max_units is null (we have no limit to assert).
- max_units must be > 0; a non-positive value is dropped (never emit an invalid limit).
- data_source must be non-empty and data_year an integer -- supplied at run time so the
  provenance is honest rather than hardcoded. code_system carried from the procedure.
- Sorted by code, deterministic.
"""

from __future__ import annotations

from pathlib import Path

from contracts.types import QuantityLimit

from .. import config, jsonio


def build_quantity_limits(
    data_source: str,
    data_year: int,
    procedures_path: str | Path | None = None,
    out_path: str | Path | None = None,
) -> int:
    """Build quantity_limits.json. Returns the number of records written."""
    procedures_path = Path(procedures_path) if procedures_path else config.PROCEDURES_JSON
    out_path = Path(out_path) if out_path else config.QUANTITY_LIMITS_JSON

    if not str(data_source).strip():
        raise ValueError("quantity_limits requires a non-empty data_source")

    procedures = jsonio.read_json(procedures_path) if Path(procedures_path).exists() else []

    limits: list[QuantityLimit] = []
    for p in procedures:
        units = p.get("typical_max_units")
        if units is None:
            continue  # no limit to assert
        if not isinstance(units, (int, float)) or units <= 0:
            continue  # never emit a non-positive / invalid limit
        limits.append(
            QuantityLimit(
                code=p["code"],
                max_units=units,
                data_source=data_source,
                data_year=data_year,
                code_system=p.get("code_system"),
            )
        )

    limits.sort(key=lambda q: q.code)
    jsonio.write_json(out_path, limits)
    return len(limits)
