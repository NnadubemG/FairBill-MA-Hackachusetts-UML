"""Validation gate for processed outputs. Must pass before committing /data/processed.

Checks prices.json (PriceStat) and medicare.json (PriceReference) against the hard
rules. It never modifies data -- it only reports problems (property P7, fail safe).

Failures:
- missing or empty data_source, or missing data_year
- any present price < 0
- min_rate > median_rate, or median_rate > max_rate (when the pair is present)
- a code not present in procedures.json

Usage:
    python -m pipeline.validate
Exits 0 when clean, 1 when any problem is found.
"""

from __future__ import annotations

import sys
from pathlib import Path

from . import config, jsonio

# Numeric price fields to range-check on a PriceStat record.
_PRICE_FIELDS = ("min_rate", "median_rate", "max_rate", "cash_price", "gross_charge")


def _valid_codes(procedures_path: Path) -> set[str]:
    data = jsonio.read_json(procedures_path)
    return {row["code"] for row in data}


def _check_provenance(label: str, idx: int, rec: dict, problems: list[str]) -> None:
    source = rec.get("data_source")
    year = rec.get("data_year")
    if not source or not str(source).strip():
        problems.append(f"{label}[{idx}] code={rec.get('code')!r}: missing data_source")
    if year is None:
        problems.append(f"{label}[{idx}] code={rec.get('code')!r}: missing data_year")


def _check_code_known(
    label: str, idx: int, rec: dict, valid: set[str], problems: list[str]
) -> None:
    code = rec.get("code")
    if code not in valid:
        problems.append(f"{label}[{idx}]: code {code!r} not in procedures.json")


def _check_nonnegative(
    label: str, idx: int, rec: dict, fields, problems: list[str]
) -> None:
    for fld in fields:
        val = rec.get(fld)
        if val is not None and val < 0:
            problems.append(f"{label}[{idx}] code={rec.get('code')!r}: {fld} is negative ({val})")


def _check_ordering(label: str, idx: int, rec: dict, problems: list[str]) -> None:
    lo, med, hi = rec.get("min_rate"), rec.get("median_rate"), rec.get("max_rate")
    if lo is not None and med is not None and lo > med:
        problems.append(f"{label}[{idx}] code={rec.get('code')!r}: min_rate > median_rate")
    if med is not None and hi is not None and med > hi:
        problems.append(f"{label}[{idx}] code={rec.get('code')!r}: median_rate > max_rate")


def validate(
    prices_path: Path | None = None,
    medicare_path: Path | None = None,
    procedures_path: Path | None = None,
) -> list[str]:
    """Return a list of problem strings. Empty list == valid."""
    prices_path = prices_path or config.PRICES_JSON
    medicare_path = medicare_path or config.MEDICARE_JSON
    procedures_path = procedures_path or config.PROCEDURES_JSON

    problems: list[str] = []
    valid = _valid_codes(procedures_path)

    for idx, rec in enumerate(jsonio.read_json(prices_path)):
        _check_provenance("prices", idx, rec, problems)
        _check_code_known("prices", idx, rec, valid, problems)
        _check_nonnegative("prices", idx, rec, _PRICE_FIELDS, problems)
        _check_ordering("prices", idx, rec, problems)

    for idx, rec in enumerate(jsonio.read_json(medicare_path)):
        _check_provenance("medicare", idx, rec, problems)
        _check_code_known("medicare", idx, rec, valid, problems)
        _check_nonnegative("medicare", idx, rec, ("medicare_price",), problems)

    return problems


def main(argv: list[str] | None = None) -> int:
    problems = validate()
    if problems:
        print(f"VALIDATION FAILED: {len(problems)} problem(s)", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print("VALIDATION OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
