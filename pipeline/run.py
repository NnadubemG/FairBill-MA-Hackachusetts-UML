"""Pipeline CLI: run one stage or all, with simple mtime-based caching.

    python -m pipeline.run <stage|all> [--force] [--data-source S] [--data-year Y]

Stages (dependency order): procedures, hospitals, prices, medicare, ncci, chia, reference

Caching: a stage is skipped when its output file already exists and is newer than all of
its declared inputs, unless --force is passed. The cache check is a pure helper
(is_up_to_date) so it is unit-testable without real data.

Provenance: prices/medicare/ncci/chia read raw files under /data/raw and need a
--data-source and --data-year for their records. `reference` combines medicare + prices
and derives its own provenance. In `all` mode a stage whose raw input or required params
are missing is reported and skipped so partial runs still make progress.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config

# Dependency order matters: prices needs hospitals (bindings); reference needs
# procedures + medicare + prices.
STAGES = ["procedures", "hospitals", "prices", "medicare", "ncci", "chia", "reference"]


def is_up_to_date(output: Path, inputs: list[Path]) -> bool:
    """True when `output` exists and is newer than every existing input.

    A missing output is never up to date. Missing inputs are ignored (can't compare).
    """
    if not output.exists():
        return False
    out_mtime = output.stat().st_mtime
    for inp in inputs:
        if inp.exists() and inp.stat().st_mtime > out_mtime:
            return False
    return True


def _require_params(name: str, data_source: str | None, data_year: int | None) -> None:
    if data_source is None or data_year is None:
        raise SystemExit(f"stage {name!r} requires --data-source and --data-year")


def _curated_codes() -> set[str]:
    """Curated code set from the procedure list (source of truth for filtering)."""
    from .procedure_list import curated_codes, load_procedures

    return curated_codes(load_procedures(config.PROCEDURE_LIST_CSV))


def _run_stage(
    name: str,
    force: bool,
    data_source: str | None,
    data_year: int | None,
) -> str:
    """Dispatch a single stage. Returns a short status string."""
    if name == "procedures":
        from .stages.procedures import build_procedures

        if not force and is_up_to_date(config.PROCEDURES_JSON, [config.PROCEDURE_LIST_CSV]):
            return "procedures: cached"
        return f"procedures: wrote {build_procedures()}"

    if name == "hospitals":
        from .stages.hospitals import build_hospitals

        if not force and is_up_to_date(config.HOSPITALS_JSON, [config.HOSPITALS_INPUT_CSV]):
            return "hospitals: cached"
        return f"hospitals: wrote {build_hospitals()}"

    if name == "prices":
        from .jsonio import read_json
        from .stages.hospitals import HospitalBinding
        from .stages.prices import build_prices

        _require_params(name, data_source, data_year)
        inputs = [config.HOSPITAL_BINDINGS_JSON, config.PROCEDURE_LIST_CSV]
        if not force and is_up_to_date(config.PRICES_JSON, inputs):
            return "prices: cached"
        bindings = [
            HospitalBinding(b["hospital_id"], b["format_id"], b["source_file"])
            for b in read_json(config.HOSPITAL_BINDINGS_JSON)
        ]
        n = build_prices(bindings, _curated_codes(), data_source, data_year)
        return f"prices: wrote {n}"

    if name == "medicare":
        from .stages.medicare import build_medicare

        _require_params(name, data_source, data_year)
        if not force and is_up_to_date(config.MEDICARE_JSON, [config.PFS_RAW]):
            return "medicare: cached"
        n = build_medicare(config.PFS_RAW, _curated_codes(), data_source, data_year)
        return f"medicare: wrote {n}"

    if name == "ncci":
        from .stages.ncci import build_ncci_pairs

        _require_params(name, data_source, data_year)
        if not force and is_up_to_date(config.NCCI_PAIRS_JSON, [config.NCCI_RAW]):
            return "ncci: cached"
        n = build_ncci_pairs(config.NCCI_RAW, _curated_codes(), data_source, data_year)
        return f"ncci: wrote {n}"

    if name == "chia":
        from .stages.chia import build_chia_tiers

        _require_params(name, data_source, data_year)
        if not force and is_up_to_date(config.CHIA_TIERS_JSON, [config.CHIA_RAW]):
            return "chia: cached"
        n = build_chia_tiers(config.CHIA_RAW, data_source, data_year)
        return f"chia: wrote {n}"

    if name == "reference":
        from .stages.reference import write_reference

        inputs = [config.PROCEDURES_JSON, config.MEDICARE_JSON, config.PRICES_JSON]
        if not force and is_up_to_date(config.REFERENCE_JSON, inputs):
            return "reference: cached"
        return f"reference: wrote {write_reference()}"

    raise SystemExit(f"unknown stage: {name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pipeline.run")
    parser.add_argument("stage", choices=STAGES + ["all"])
    parser.add_argument("--force", action="store_true", help="ignore the cache")
    parser.add_argument("--data-source")
    parser.add_argument("--data-year", type=int)
    args = parser.parse_args(argv)

    targets = STAGES if args.stage == "all" else [args.stage]
    for name in targets:
        try:
            print(_run_stage(name, args.force, args.data_source, args.data_year))
        except (SystemExit, FileNotFoundError) as exc:
            if args.stage == "all":
                # In 'all' mode, report and continue past stages whose inputs or
                # required params are not available yet.
                print(f"{name}: skipped ({exc})", file=sys.stderr)
                continue
            raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
