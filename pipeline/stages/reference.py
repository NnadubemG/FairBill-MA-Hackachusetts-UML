"""Stage: combine Medicare price + MA gross range -> /data/processed/reference.json.

/core needs exactly ONE PriceReference per code. This stage merges:
  - medicare_price  (from the medicare stage, per unit), and
  - ma_range_low/high = lowest/highest gross_charge across MA hospitals for that code
    (gross payer group in prices.json, per unit)
into a single PriceReference per curated code.

Never invents a number: a field with no data stays null; a code with neither a Medicare
price nor a range yields no record. code_system is always set (from procedures.json);
if it cannot be determined, the stage raises rather than emit a null that would break
/core. If the two sources have different years, the older year is used and noted in
data_source.

Pure transform over loaded JSON. Reuses the PriceReference contract and jsonio.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from contracts.types import PriceReference

from .. import config, jsonio


class ReferenceError(ValueError):
    """Raised when a reference record cannot be built safely (e.g. unknown code_system)."""


def _resolve_code_system(
    code: str,
    proc: Optional[dict],
    medicare: Optional[dict],
    gross_rows: list[dict],
) -> str:
    # Source of truth: procedures.json. Fall back to medicare, then any gross row.
    for candidate in (
        proc.get("code_system") if proc else None,
        medicare.get("code_system") if medicare else None,
        *[g.get("code_system") for g in gross_rows],
    ):
        if candidate:
            return candidate
    raise ReferenceError(
        f"code {code!r}: no code_system in procedures/medicare/prices; "
        f"cannot emit a reference with a null code_system (breaks /core)."
    )


def _provenance(
    medicare_price: Optional[float],
    medicare: Optional[dict],
    range_present: bool,
    gross_rows: list[dict],
) -> tuple[str, int]:
    years: list[int] = []
    med_src = None
    med_yr = None
    if medicare_price is not None and medicare is not None:
        med_src = (medicare.get("data_source") or "").strip() or "CMS PFS"
        med_yr = medicare.get("data_year")
        if med_yr is not None:
            years.append(med_yr)

    gross_src = None
    gross_yr = None
    if range_present and gross_rows:
        srcs = {(g.get("data_source") or "").strip() for g in gross_rows if g.get("data_source")}
        gross_src = next(iter(srcs)) if len(srcs) == 1 else "MA gross charges"
        gyears = [g.get("data_year") for g in gross_rows if g.get("data_year") is not None]
        if gyears:
            gross_yr = min(gyears)
            years.append(gross_yr)

    data_year = min(years) if years else None
    if data_year is None:
        raise ReferenceError("reference record has no usable data_year")

    # Build a descriptive data_source.
    if med_src and gross_src:
        if med_yr is not None and gross_yr is not None and med_yr != gross_yr:
            data_source = (
                f"{med_src} {med_yr}; MA gross charges {gross_yr} (older year shown)"
            )
        else:
            data_source = f"{med_src}; MA gross charges"
    elif med_src:
        data_source = med_src
    else:  # range only
        data_source = gross_src or "MA gross charges"

    return data_source, data_year


def build_reference(
    procedures: list[dict],
    medicare: list[dict],
    prices: list[dict],
) -> list[PriceReference]:
    """Pure: combine inputs into one PriceReference per code that has data."""
    proc_by_code = {p["code"]: p for p in procedures}
    med_by_code: dict[str, dict] = {}
    for m in medicare:
        med_by_code.setdefault(m["code"], m)  # first per code

    gross_by_code: dict[str, list[dict]] = {}
    for ps in prices:
        if ps.get("payer_group") == "gross" and ps.get("gross_charge") is not None:
            gross_by_code.setdefault(ps["code"], []).append(ps)

    refs: list[PriceReference] = []
    for code in proc_by_code:
        medicare_rec = med_by_code.get(code)
        gross_rows = gross_by_code.get(code, [])

        medicare_price = medicare_rec.get("medicare_price") if medicare_rec else None
        gross_values = [g["gross_charge"] for g in gross_rows]
        ma_range_low = min(gross_values) if gross_values else None
        ma_range_high = max(gross_values) if gross_values else None
        range_present = ma_range_low is not None or ma_range_high is not None

        if medicare_price is None and not range_present:
            continue  # neither -> no record (R1.4)

        code_system = _resolve_code_system(code, proc_by_code.get(code), medicare_rec, gross_rows)
        data_source, data_year = _provenance(
            medicare_price, medicare_rec, range_present, gross_rows
        )

        refs.append(
            PriceReference(
                code=code,
                code_system=code_system,  # type: ignore[arg-type]
                medicare_price=medicare_price,
                ma_range_low=ma_range_low,
                ma_range_high=ma_range_high,
                data_source=data_source,
                data_year=data_year,
            )
        )

    refs.sort(key=lambda r: r.code)
    return refs


def write_reference(
    procedures_path: str | Path | None = None,
    medicare_path: str | Path | None = None,
    prices_path: str | Path | None = None,
    out_path: str | Path | None = None,
) -> int:
    """Load processed files, build reference.json, return the record count."""
    procedures_path = Path(procedures_path) if procedures_path else config.PROCEDURES_JSON
    medicare_path = Path(medicare_path) if medicare_path else config.MEDICARE_JSON
    prices_path = Path(prices_path) if prices_path else config.PRICES_JSON
    out_path = Path(out_path) if out_path else config.REFERENCE_JSON

    def read(p: Path) -> list[dict]:
        if not p.exists():
            return []
        data = jsonio.read_json(p)
        return data if isinstance(data, list) else []

    refs = build_reference(read(procedures_path), read(medicare_path), read(prices_path))
    jsonio.write_json(out_path, refs)
    return len(refs)
