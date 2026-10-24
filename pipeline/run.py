"""Pipeline CLI: run one stage or all, with simple mtime-based caching.

    python -m pipeline.run <stage|all> [--force] [--data-source S] [--data-year Y]

Stages: procedures, hospitals, prices, medicare, ncci, chia

Caching: a stage is skipped when its output file already exists and is newer than all of
its declared inputs, unless --force is passed. The cache check is a pure helper
(is_up_to_date) so it is unit-testable (U35) without real data.

Note: prices/medicare/ncci/chia need --data-source and --data-year (provenance) and read
their raw inputs from /data/raw; those are supplied at run time rather than hardcoded.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config

STAGES = ["procedures", "hospitals", "prices", "medicare", "ncci", "chia"]


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


def _run_stage(
    name: str,
    force: bool,
    data_source: str | None,
    data_year: int | None,
) -> str:
    """Dispatch a single stage. Returns a short status string."""
    if name == "procedures":
        from .stages.procedures import build_procedures

        out = config.PROCEDURES_JSON
        inputs = [config.PROCEDURE_LIST_CSV]
        if not force and is_up_to_date(out, inputs):
            return "procedures: cached"
        n = build_procedures()
        return f"procedures: wrote {n}"

    if name == "hospitals":
        from .stages.hospitals import build_hospitals

        out = config.HOSPITALS_JSON
        inputs = [config.DATA_DIR / "hospitals_input.csv"]
        if not force and is_up_to_date(out, inputs):
            return "hospitals: cached"
        n = build_hospitals()
        return f"hospitals: wrote {n}"

    # The remaining stages need provenance + raw inputs supplied at run time.
    if data_source is None or data_year is None:
        raise SystemExit(
            f"stage {name!r} requires --data-source and --data-year"
        )

    if name in ("prices", "medicare", "ncci", "chia"):
        return (
            f"{name}: run from code with real /data/raw inputs "
            f"(source={data_source!r}, year={data_year}); "
            f"not auto-wired in CLI yet"
        )

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
