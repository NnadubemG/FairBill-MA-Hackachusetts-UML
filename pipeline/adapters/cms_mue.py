"""Adapter: CMS NCCI MUE table (practitioner services) -> typical_max_units in procedure_list.csv.

Source: https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edits-mues
(file medicare-ncci-2026-q4-practitioner-services-mue-table.zip, effective 2026-10-01).
An MUE is the most units of a service a provider would normally report for one patient on one
day. It is the honest, published source for typical_max_units, which the quantity_limits stage
turns into QuantityLimit records.

Only the typical_max_units column of curated codes is changed; codes with no MUE row keep their
existing value. Values must be whole numbers above zero; anything else is left alone.

Usage: python -m pipeline.adapters.cms_mue
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

from .. import config


def read_mue(mue_zip: Path) -> dict[str, int]:
    """Return {code: MUE units} from the CSV member of the MUE ZIP."""
    with zipfile.ZipFile(mue_zip) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        text = z.read(name).decode("utf-8-sig", errors="replace")
    units: dict[str, int] = {}
    in_table = False
    for row in csv.reader(io.StringIO(text)):
        if not row:
            continue
        if not in_table:
            in_table = row[0].strip().upper().startswith("HCPCS")  # header row
            continue
        code, value = row[0].strip(), (row[1].strip() if len(row) > 1 else "")
        if code and value.isdigit() and int(value) > 0:
            units[code] = int(value)
    return units


def adapt_mue(mue_zip: Path | None = None, procedure_list: Path | None = None) -> int:
    """Fill typical_max_units from the MUE table. Returns the number of codes filled."""
    mue_zip = Path(mue_zip) if mue_zip else config.MUE_RAW_ZIP
    procedure_list = Path(procedure_list) if procedure_list else config.PROCEDURE_LIST_CSV
    units = read_mue(mue_zip)

    raw = procedure_list.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8")))
    fields = reader.fieldnames or []
    rows = list(reader)
    filled = 0
    for row in rows:
        code = (row.get("code") or "").strip()
        if code in units:
            row["typical_max_units"] = str(units[code])
            filled += 1

    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fields, lineterminator=newline)
    writer.writeheader()
    writer.writerows(rows)
    procedure_list.write_bytes(out.getvalue().encode("utf-8"))
    return filled


if __name__ == "__main__":
    print(f"cms_mue: filled typical_max_units for {adapt_mue()} codes")
