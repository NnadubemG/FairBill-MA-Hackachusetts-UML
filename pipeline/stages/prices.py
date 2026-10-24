"""Stage: raw hospital files -> /data/processed/prices.json (list of PriceStat).

For each hospital (from the bindings manifest), pick its parser by format_id, stream
rows, filter to curated codes (the parser already does this), then for each row:

- negotiated : classify the raw payer into a payer group; the dollar value joins that
  group's min/median/max aggregation for (hospital, code, payer_group).
- cash       : dollar value joins the "cash" group; stored in cash_price (median if
  several).
- gross      : dollar value joins the "gross" group; stored in gross_charge.

Rates that are not clean dollar figures (percent / algorithm / negative / unrecognized)
are skipped and written to skipped.log -- never estimated. Blank/N/A rows contribute
nothing, so a field with no usable values stays null (never a placeholder).

Every emitted PriceStat carries data_source and data_year (provenance). Output is
sorted by (hospital_id, code, payer_group) so it is deterministic (property P6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from contracts.types import PayerGroup, PriceStat

from .. import config, jsonio
from ..aggregate import summarize
from ..parsers.base import RawPriceRow
from ..payer_groups import classify
from ..rates import Dollar, Missing, Skip, parse_rate
from ..registry import get_parser
from ..skiplog import log_skip
from .hospitals import HospitalBinding


@dataclass
class _Bucket:
    """Accumulates dollar values for one (hospital, code, payer_group)."""

    code_system: Optional[str] = None
    values: list[float] = field(default_factory=list)


def _group_for_row(row: RawPriceRow) -> PayerGroup:
    if row.rate_kind == "cash":
        return "cash"
    if row.rate_kind == "gross":
        return "gross"
    return classify(row.raw_payer)  # negotiated


def _accumulate(
    rows: Iterable[RawPriceRow],
    hospital_id: str,
    skip_log_path: Optional[Path],
) -> dict[tuple[str, PayerGroup], _Bucket]:
    """Collect usable dollar values per (code, payer_group); log skips."""
    buckets: dict[tuple[str, PayerGroup], _Bucket] = {}
    for row in rows:
        result = parse_rate(row.raw_rate)
        if isinstance(result, Missing):
            continue  # no value; field stays null downstream
        if isinstance(result, Skip):
            log_skip(hospital_id, row.code, row.raw_payer, result.reason, skip_log_path)
            continue
        assert isinstance(result, Dollar)

        group = _group_for_row(row)
        key = (row.code, group)
        bucket = buckets.setdefault(key, _Bucket())
        if bucket.code_system is None and row.code_system is not None:
            bucket.code_system = row.code_system
        bucket.values.append(result.value)
    return buckets


def _bucket_to_pricestat(
    hospital_id: str,
    code: str,
    group: PayerGroup,
    bucket: _Bucket,
    data_source: str,
    data_year: int,
) -> PriceStat:
    lo, med, hi = summarize(bucket.values)
    cash_price = med if group == "cash" else None
    gross_charge = med if group == "gross" else None
    # min/median/max apply to negotiated payer groups only.
    if group in ("cash", "gross"):
        lo = med = hi = None
    return PriceStat(
        hospital_id=hospital_id,
        code=code,
        payer_group=group,
        data_source=data_source,
        data_year=data_year,
        code_system=bucket.code_system,  # type: ignore[arg-type]
        min_rate=lo,
        median_rate=med,
        max_rate=hi,
        cash_price=cash_price,
        gross_charge=gross_charge,
    )


def build_prices_for_hospital(
    binding: HospitalBinding,
    curated: set[str],
    data_source: str,
    data_year: int,
    raw_dir: Path | None = None,
    skip_log_path: Path | None = None,
) -> list[PriceStat]:
    """Produce the PriceStat records for a single hospital."""
    raw_dir = raw_dir or config.RAW_DIR
    parser = get_parser(binding.format_id)
    path = str(raw_dir / binding.source_file)
    rows = parser.rows(path, curated)
    buckets = _accumulate(rows, binding.hospital_id, skip_log_path)

    stats: list[PriceStat] = []
    for (code, group), bucket in buckets.items():
        if not bucket.values:
            continue  # nothing usable -> no record (fail safe, no guessed number)
        stats.append(
            _bucket_to_pricestat(
                binding.hospital_id, code, group, bucket, data_source, data_year
            )
        )
    return stats


def build_prices(
    bindings: list[HospitalBinding],
    curated: set[str],
    data_source: str,
    data_year: int,
    out_path: str | Path | None = None,
    raw_dir: Path | None = None,
    skip_log_path: Path | None = None,
) -> int:
    """Build prices.json across all hospitals. Returns the record count."""
    out_path = Path(out_path) if out_path else config.PRICES_JSON

    all_stats: list[PriceStat] = []
    for binding in bindings:
        all_stats.extend(
            build_prices_for_hospital(
                binding, curated, data_source, data_year, raw_dir, skip_log_path
            )
        )

    all_stats.sort(key=lambda s: (s.hospital_id, s.code, s.payer_group))
    jsonio.write_json(out_path, all_stats)
    return len(all_stats)
