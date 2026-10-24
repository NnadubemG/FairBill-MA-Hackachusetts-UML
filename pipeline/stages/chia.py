"""Stage: CHIA relative price data -> /data/processed/chia_tiers.json.

CHIA publishes a relative price per hospital (a ratio vs. a statewide benchmark) and
often a tier label. We keep one record per hospital that HAS data; a hospital with no
usable relative price and no tier produces NO record (absence, never a placeholder).

chia_tiers.json is a pipeline-internal shape (not a shared contract). Each record:
    {hospital_id, relative_price, tier, data_source, data_year}
relative_price and tier are nullable, but at least one must be present for a record to
exist. Every record carries provenance.

Input CSV columns (header required): hospital_id, relative_price, tier
Streamed row-by-row. relative_price is parsed to a float; blank/non-numeric -> null.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

from .. import config, jsonio


def _parse_relative_price(raw: str) -> Optional[float]:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    # A relative price is a non-negative ratio; reject negatives rather than guess.
    return value if value >= 0 else None


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value or None


def build_chia_tiers(
    source_csv: str | Path,
    data_source: str,
    data_year: int,
    out_path: str | Path | None = None,
) -> int:
    """Build chia_tiers.json. Returns the number of hospital records written."""
    out_path = Path(out_path) if out_path else config.CHIA_TIERS_JSON

    records: list[dict] = []
    seen: set[str] = set()
    with open(source_csv, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            hid = _clean(row.get("hospital_id"))
            if hid is None or hid in seen:
                continue
            relative_price = _parse_relative_price(row.get("relative_price") or "")
            tier = _clean(row.get("tier"))
            # No usable data at all -> no record (absence, not a placeholder).
            if relative_price is None and tier is None:
                continue
            seen.add(hid)
            records.append(
                {
                    "hospital_id": hid,
                    "relative_price": relative_price,
                    "tier": tier,
                    "data_source": data_source,
                    "data_year": data_year,
                }
            )

    records.sort(key=lambda r: r["hospital_id"])
    jsonio.write_json(out_path, records)
    return len(records)
