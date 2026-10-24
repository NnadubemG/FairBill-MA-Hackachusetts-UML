"""Command line for the synthetic bill generator.

  python -m synthetic --seed 7 --scenario mixed --style messy --out DIR
  python -m synthetic --samples            # regenerate synthetic/samples/

This is the only part of /synthetic that writes files. File names are built from a validated
scenario name and an integer seed, so nothing is ever written outside the output folder.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from synthetic.generate import SCENARIOS, generate_bill, to_json
from synthetic.render import STYLES, render_pdf, render_text

SAMPLES_DIR = Path(__file__).resolve().parent / "samples"

# Fixed seeds and styles for the committed samples. Plain for the simple scenarios,
# messy for the two that are meant to be hard to read.
SAMPLE_SPECS: tuple[tuple[str, int, str], ...] = (
    ("clean", 1, "plain"),
    ("duplicate", 1, "plain"),
    ("high_price", 1, "plain"),
    ("unknown_code", 1, "plain"),
    ("injection", 1, "messy"),
    ("mixed", 1, "messy"),
    ("quantity", 1, "plain"),
    ("unbundling", 1, "plain"),
)


def write_bill(scenario: str, seed: int, style: str, out_dir: Path) -> list[Path]:
    """Write bill-<scenario>-<seed>.{json,txt,pdf} into out_dir. Returns the paths."""
    bill = generate_bill(seed, scenario)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"bill-{scenario}-{seed}"
    files = {
        out_dir / f"{stem}.json": to_json(bill).encode("utf-8"),
        out_dir / f"{stem}.txt": render_text(bill, style).encode("utf-8"),
        out_dir / f"{stem}.pdf": render_pdf(bill, style),
    }
    for path, data in files.items():
        path.write_bytes(data)  # bytes, so Windows never rewrites line endings
    return list(files)


def write_samples(out_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for scenario, seed, style in SAMPLE_SPECS:
        paths += write_bill(scenario, seed, style, out_dir)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m synthetic", description=__doc__.split("\n")[0])
    parser.add_argument("--seed", type=int, default=1, help="seed (default 1)")
    parser.add_argument("--scenario", choices=SCENARIOS, default="clean")
    parser.add_argument("--style", choices=STYLES, default="plain")
    parser.add_argument("--out", type=Path, help="output folder (created if missing)")
    parser.add_argument("--samples", action="store_true", help="regenerate the committed samples")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.samples:
        out_dir = args.out if args.out else SAMPLES_DIR
    elif args.out:
        out_dir = args.out
    else:
        print("error: --out is required (or use --samples)", file=sys.stderr)
        return 2

    if out_dir.exists() and not out_dir.is_dir():
        print(f"error: {out_dir} exists and is not a folder", file=sys.stderr)
        return 2

    paths = write_samples(out_dir) if args.samples else write_bill(args.scenario, args.seed, args.style, out_dir)
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
