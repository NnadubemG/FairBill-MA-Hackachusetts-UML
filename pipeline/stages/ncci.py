"""Stage: NCCI procedure-to-procedure edits -> /data/processed/bundle_pairs.json.

NCCI PTP edits are code pairs: a column-1 code and a column-2 code, with a modifier
indicator:
    "0" = the pair may not be billed together
    "1" = may be billed together only with an appropriate modifier
    "9" = the edit does not apply
We keep only pairs where BOTH codes are in our curated set, dropping any pair that
touches a non-curated code, and retain the modifier indicator verbatim.

Output conforms to contracts/bundle-pair.schema.json (BundlePair), which /core consumes
for possible_unbundling flags. Each record:
    {code_1, code_2, modifier_indicator, data_source, data_year}

Input CSV columns (header required): code_1, code_2, modifier_indicator
Streamed row-by-row; filtered to curated codes while reading. Every record carries
provenance.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .. import config, jsonio

_VALID_INDICATORS = {"0", "1", "9"}


def build_ncci_pairs(
    source_csv: str | Path,
    curated: set[str],
    data_source: str,
    data_year: int,
    out_path: str | Path | None = None,
) -> int:
    """Build bundle_pairs.json (BundlePair records). Returns the number of pairs written."""
    out_path = Path(out_path) if out_path else config.BUNDLE_PAIRS_JSON

    records: list[dict] = []
    seen: set[tuple[str, str]] = set()
    with open(source_csv, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            c1 = (row.get("code_1") or "").strip()
            c2 = (row.get("code_2") or "").strip()
            # Both codes must be curated; otherwise drop the pair.
            if not c1 or not c2 or c1 not in curated or c2 not in curated:
                continue
            indicator = (row.get("modifier_indicator") or "").strip()
            if indicator not in _VALID_INDICATORS:
                continue  # unknown indicator: skip rather than guess
            if (c1, c2) in seen:
                continue
            seen.add((c1, c2))
            records.append(
                {
                    "code_1": c1,
                    "code_2": c2,
                    "modifier_indicator": indicator,
                    "data_source": data_source,
                    "data_year": data_year,
                }
            )

    records.sort(key=lambda r: (r["code_1"], r["code_2"]))
    jsonio.write_json(out_path, records)
    return len(records)
