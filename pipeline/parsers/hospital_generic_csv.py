"""Parser: generic hospital CSV (long format), format_id = "generic_csv".

Expected columns (header required):
    code, code_system, payer, rate, rate_kind
Each row is ONE price observation. rate_kind is one of negotiated / cash / gross.
For cash/gross rows the payer column may be blank.

Streams row-by-row with csv.reader and filters to the curated code set as it reads, so
a huge file never lands in memory. Unknown/extra columns are ignored. All string fields
are inert data.
"""

from __future__ import annotations

import csv
from typing import Iterator, Optional

from contracts.types import CodeSystem

from .base import RawPriceRow

_VALID_CODE_SYSTEMS = {"CPT", "HCPCS", "DRG", "REV", "ICD10", "OTHER"}
_VALID_RATE_KINDS = {"negotiated", "cash", "gross"}


def _code_system(raw: str) -> Optional[CodeSystem]:
    raw = (raw or "").strip()
    return raw if raw in _VALID_CODE_SYSTEMS else None  # type: ignore[return-value]


class GenericCsvParser:
    format_id = "generic_csv"

    def rows(self, path: str, curated: set[str]) -> Iterator[RawPriceRow]:
        with open(path, "r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                code = (row.get("code") or "").strip()
                if not code or code not in curated:
                    continue  # filter to curated codes while reading (low memory)

                rate_kind = (row.get("rate_kind") or "").strip().lower()
                if rate_kind not in _VALID_RATE_KINDS:
                    # Unknown kind: skip quietly; the prices stage logs real skips.
                    continue

                yield RawPriceRow(
                    hospital_id="",  # filled in by the prices stage (file -> hospital)
                    code=code,
                    raw_payer=(row.get("payer") or "").strip(),
                    raw_rate=(row.get("rate") or "").strip(),
                    rate_kind=rate_kind,  # type: ignore[arg-type]
                    code_system=_code_system(row.get("code_system") or ""),
                )
