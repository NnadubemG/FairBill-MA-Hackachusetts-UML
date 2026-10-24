"""Adapter: CMS PFS national payment amount files -> data/raw/cms_pfs.csv (medicare stage input).

Source: https://www.cms.gov/medicare/payment/fee-schedules/physician/national-payment-amount-file
PFREV26A is the full 2026 table; PFREV26B, C and D are partial updates. They are applied in
order, so a later revision replaces an earlier row for the same code. Only the non-QP member
(standard fees) is read.

Row layout (quoted, comma-separated): 0 year, 1 MAC, 2 locality, 3 HCPCS, 4 modifier,
5 non-facility amount, 6 facility amount, 7 filler, 8 PC/TC indicator, 9 status code, ...

Kept: MAC + locality from config (Massachusetts, Metropolitan Boston), the global row (blank
modifier; 26/TC/53 rows are partial services), status "A" (active), and the published
non-facility amount. The non-facility amount is the higher of the two, so it under-flags rather
than over-flags. No amount is computed here, and the OPPS imaging cap is not applied.

Usage: python -m pipeline.adapters.cms_pfs
"""

from __future__ import annotations

import csv
import io
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterator

from .. import config


def _rows(zip_path: Path) -> Iterator[list[str]]:
    """Stream rows of the non-QP text file inside one revision ZIP (a ZIP inside a ZIP)."""
    with zipfile.ZipFile(zip_path) as outer:
        inner_name = next(n for n in outer.namelist() if n.lower().endswith("nonqp.zip"))
        with zipfile.ZipFile(io.BytesIO(outer.read(inner_name))) as inner:
            txt = next(n for n in inner.namelist() if n.lower().endswith(".txt"))
            with inner.open(txt) as fh:
                yield from csv.reader(io.TextIOWrapper(fh, encoding="latin-1"))


def adapt_pfs(
    revision_zips: list[Path] | None = None,
    out_csv: Path | None = None,
    mac: str | None = None,
    locality: str | None = None,
) -> int:
    """Write hcpcs,locality,payment_amount for the MA locality. Returns codes written."""
    revision_zips = revision_zips or config.PFS_REVISION_ZIPS
    out_csv = Path(out_csv) if out_csv else config.PFS_RAW
    mac = mac or config.MA_PFS_MAC
    locality = locality or config.MA_PFS_LOCALITY_CODE

    amounts: dict[str, Decimal] = {}
    for zip_path in revision_zips:  # in order: later revisions win
        for r in _rows(Path(zip_path)):
            if len(r) < 10 or r[1].strip() != mac or r[2].strip() != locality:
                continue
            if r[4].strip():
                continue  # modifier row (26, TC, 53): a partial service, not the whole one
            code = r[3].strip()
            try:
                amount = Decimal(r[5].strip())
            except InvalidOperation:
                amount = Decimal(0)
            if r[9].strip() != "A" or amount <= 0:
                amounts.pop(code, None)  # inactive or no amount: never keep a stale figure
                continue
            amounts[code] = amount

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["hcpcs", "locality", "payment_amount"])
        for code in sorted(amounts):
            writer.writerow([code, mac + locality, f"{amounts[code]:.2f}"])
    return len(amounts)


if __name__ == "__main__":
    print(f"cms_pfs: wrote {adapt_pfs()} codes to {config.PFS_RAW}")
