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


def _check_reference(
    reference_path: Path, valid: set[str], problems: list[str]
) -> None:
    """Validate reference.json: one combined PriceReference per code for /core."""
    seen_keys: set[tuple] = set()
    for idx, rec in enumerate(jsonio.read_json(reference_path)):
        _check_provenance("reference", idx, rec, problems)
        _check_code_known("reference", idx, rec, valid, problems)
        _check_nonnegative(
            "reference", idx, rec, ("medicare_price", "ma_range_low", "ma_range_high"), problems
        )
        # code_system must be present (non-null, non-empty) -- /core needs it.
        cs = rec.get("code_system")
        if not cs or not str(cs).strip():
            problems.append(f"reference[{idx}] code={rec.get('code')!r}: missing code_system")
        # No duplicate (code, code_system) keys.
        key = (rec.get("code"), cs)
        if key in seen_keys:
            problems.append(f"reference[{idx}]: duplicate (code, code_system) {key!r}")
        seen_keys.add(key)
        # MA range ordering.
        lo, hi = rec.get("ma_range_low"), rec.get("ma_range_high")
        if lo is not None and hi is not None and lo > hi:
            problems.append(
                f"reference[{idx}] code={rec.get('code')!r}: ma_range_low > ma_range_high"
            )


def _check_quantity_limits(path: Path, valid: set[str], problems: list[str]) -> None:
    """Validate quantity_limits.json (QuantityLimit): code known, max_units > 0, provenance."""
    for idx, rec in enumerate(jsonio.read_json(path)):
        _check_provenance("quantity_limits", idx, rec, problems)
        _check_code_known("quantity_limits", idx, rec, valid, problems)
        mu = rec.get("max_units")
        if mu is None or not isinstance(mu, (int, float)) or mu <= 0:
            problems.append(
                f"quantity_limits[{idx}] code={rec.get('code')!r}: max_units must be > 0"
            )


def _check_bundle_pairs(path: Path, valid: set[str], problems: list[str]) -> None:
    """Validate bundle_pairs.json (BundlePair): both codes known, indicator in 0/1/9, provenance."""
    seen: set[tuple] = set()
    for idx, rec in enumerate(jsonio.read_json(path)):
        source, year = rec.get("data_source"), rec.get("data_year")
        if not source or not str(source).strip():
            problems.append(f"bundle_pairs[{idx}]: missing data_source")
        if year is None:
            problems.append(f"bundle_pairs[{idx}]: missing data_year")
        for fld in ("code_1", "code_2"):
            code = rec.get(fld)
            if code not in valid:
                problems.append(f"bundle_pairs[{idx}]: {fld} {code!r} not in procedures.json")
        if rec.get("modifier_indicator") not in {"0", "1", "9"}:
            problems.append(
                f"bundle_pairs[{idx}]: modifier_indicator must be '0', '1', or '9'"
            )
        key = (rec.get("code_1"), rec.get("code_2"))
        if key in seen:
            problems.append(f"bundle_pairs[{idx}]: duplicate pair {key!r}")
        seen.add(key)


def validate(
    prices_path: Path | None = None,
    medicare_path: Path | None = None,
    procedures_path: Path | None = None,
    reference_path: Path | None = None,
    quantity_limits_path: Path | None = None,
    bundle_pairs_path: Path | None = None,
) -> list[str]:
    """Return a list of problem strings. Empty list == valid."""
    prices_path = prices_path or config.PRICES_JSON
    medicare_path = medicare_path or config.MEDICARE_JSON
    procedures_path = procedures_path or config.PROCEDURES_JSON
    reference_path = reference_path or config.REFERENCE_JSON
    quantity_limits_path = quantity_limits_path or config.QUANTITY_LIMITS_JSON
    bundle_pairs_path = bundle_pairs_path or config.BUNDLE_PAIRS_JSON

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

    # These outputs are optional (partial pipelines); validate only if present.
    if Path(reference_path).exists():
        _check_reference(Path(reference_path), valid, problems)
    if Path(quantity_limits_path).exists():
        _check_quantity_limits(Path(quantity_limits_path), valid, problems)
    if Path(bundle_pairs_path).exists():
        _check_bundle_pairs(Path(bundle_pairs_path), valid, problems)

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
