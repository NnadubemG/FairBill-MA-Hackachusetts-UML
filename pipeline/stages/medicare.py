"""Stage: CMS Physician Fee Schedule -> /data/processed/medicare.json.

Emits PriceReference records (the existing contract) for the Massachusetts locality and
our curated codes only. A code with no row for the MA locality produces NO record --
we never guess a Medicare figure.

Expected PFS CSV columns (header required):
    hcpcs, locality, payment_amount
`locality` is matched against config.MA_PFS_LOCALITY. Rows are streamed row-by-row and
filtered to curated codes while reading, so a large national file never lands in memory.

Every emitted record carries data_source and data_year (provenance).
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

from contracts.types import PriceReference

from .. import config, jsonio
from ..rates import Dollar, parse_rate


def _ma_payment(raw_amount: str) -> Optional[float]:
    """Parse a PFS payment cell to a non-negative dollar, else None.

    Reuses rate parsing so %/formula/blank values never become a number.
    """
    result = parse_rate(raw_amount)
    return result.value if isinstance(result, Dollar) else None


def build_medicare(
    source_csv: str | Path,
    curated: set[str],
    data_source: str,
    data_year: int,
    locality: str | None = None,
    out_path: str | Path | None = None,
) -> int:
    """Build medicare.json. Returns the number of PriceReference records written."""
    locality = locality if locality is not None else config.MA_PFS_LOCALITY
    out_path = Path(out_path) if out_path else config.MEDICARE_JSON

    refs: list[PriceReference] = []
    seen: set[str] = set()
    with open(source_csv, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            code = (row.get("hcpcs") or "").strip()
            if not code or code not in curated:
                continue  # filter to curated codes while reading
            if (row.get("locality") or "").strip() != locality:
                continue  # MA locality only
            if code in seen:
                continue  # first MA row per code wins; avoid dup records
            price = _ma_payment(row.get("payment_amount") or "")
            if price is None:
                continue  # no usable figure -> no record (never guess)
            seen.add(code)
            refs.append(
                PriceReference(
                    code=code,
                    code_system="HCPCS",
                    medicare_price=price,
                    data_source=data_source,
                    data_year=data_year,
                )
            )

    refs.sort(key=lambda r: r.code)
    jsonio.write_json(out_path, refs)
    return len(refs)
