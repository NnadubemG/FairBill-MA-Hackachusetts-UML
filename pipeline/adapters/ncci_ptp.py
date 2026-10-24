"""Adapter: CMS NCCI Procedure-to-Procedure (PTP) edit file -> ncci_ptp.csv.

Source: CMS "Medicare NCCI PTP Edits" download (a quarterly ZIP; the useful member is
the Column One/Column Two edit file, published as both text and Excel). Export whichever
member you have to CSV and point this adapter at it.

Real-world layout varies slightly by quarter, but the columns we need are always present
under one of these header spellings:

    Column 1            | Column One | column_1 | code_1
    Column 2            | Column Two | column_2 | code_2
    Modifier            | "Modifier 0=not allowed 1=allowed 9=not applicable" | modifier_indicator

Extra columns (effective date, deletion date, the PTP edit rationale, a leading "*"
pre-existing marker) are ignored. We emit exactly the three columns the ncci stage reads:

    code_1,code_2,modifier_indicator

No filtering to curated codes here -- the stage does that. No value is invented; the
modifier indicator is passed through verbatim and the stage validates it is 0/1/9.
"""

from __future__ import annotations

import csv
from pathlib import Path

# Candidate header spellings, lowercased and stripped, mapped to our canonical names.
_COL1_ALIASES = {"column 1", "column one", "column_1", "col1", "code_1", "code1"}
_COL2_ALIASES = {"column 2", "column two", "column_2", "col2", "code_2", "code2"}
_MOD_ALIASES = {
    "modifier",
    "modifier indicator",
    "modifier_indicator",
    "ptp edit modifier",
    "modifier 0=not allowed 1=allowed 9=not applicable",
}

OUTPUT_HEADER = ["code_1", "code_2", "modifier_indicator"]


def _find_column(header: list[str], aliases: set[str]) -> int | None:
    for i, name in enumerate(header):
        key = (name or "").strip().lower()
        if key in aliases:
            return i
        # Some exports prefix a modifier blurb; match on a leading keyword too.
        if aliases is _MOD_ALIASES and key.startswith("modifier"):
            return i
    return None


def _clean_code(raw: str) -> str:
    """Normalize a HCPCS/CPT code cell: strip whitespace and a leading pre-existing '*'."""
    text = (raw or "").strip()
    if text.startswith("*"):
        text = text[1:].strip()
    return text


class NcciAdapterError(ValueError):
    """Raised when the source file is missing a required NCCI column."""


def adapt_ncci_ptp(source: str | Path, out_csv: str | Path) -> int:
    """Convert a raw NCCI PTP export to the stage CSV. Returns rows written."""
    source = Path(source)
    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    with open(source, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration:
            raise NcciAdapterError("NCCI source file is empty")

        i1 = _find_column(header, _COL1_ALIASES)
        i2 = _find_column(header, _COL2_ALIASES)
        im = _find_column(header, _MOD_ALIASES)
        missing = [
            name
            for name, idx in (("code_1", i1), ("code_2", i2), ("modifier_indicator", im))
            if idx is None
        ]
        if missing:
            raise NcciAdapterError(
                f"NCCI source missing column(s) for: {', '.join(missing)}; "
                f"saw header {header!r}"
            )

        written = 0
        with open(out_csv, "w", encoding="utf-8", newline="") as out:
            writer = csv.writer(out)
            writer.writerow(OUTPUT_HEADER)
            for row in reader:
                if not row or len(row) <= max(i1, i2, im):
                    continue  # short/blank line in the export
                c1 = _clean_code(row[i1])
                c2 = _clean_code(row[i2])
                mod = (row[im] or "").strip()
                if not c1 or not c2:
                    continue
                writer.writerow([c1, c2, mod])
                written += 1
    return written
