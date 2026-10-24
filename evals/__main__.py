"""Command line: ``python -m evals``.

    python -m evals [--fake] [--cache-only] [--max-calls N] [--strict]
                    [--scenarios a,b] [--seeds 1,2] [--styles plain,messy]
                    [--out PATH] [--cache-dir PATH]

Real mode needs ``ANTHROPIC_API_KEY`` and the three model names (``EXTRACT_MODEL_ID``,
``EXPLAIN_MODEL_ID``, ``LETTER_MODEL_ID``) in the environment. ``--cache-only`` needs the
model names (they are part of the cache key) but no key, and never calls the model. ``--fake``
uses the oracle: no key, no network, and the numbers say nothing about a model.

Exit codes: 0 ok; 1 a hard failure, or a failed threshold with ``--strict``; 2 usage or
setup problem (a short message, never a traceback).

Output names bill ids and counts only. It never prints bill text, model replies or the key.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Callable, Sequence, TextIO

from backend.envfile import load_env
from backend.extract.llm_client import LLMClient, make_client

from . import config
from .cache import CachingClient
from .corpus import PrivatePathError, build_corpus, ensure_not_private
from .oracle import OracleClient
from .report import write_report
from .run import TASKS, any_threshold_failed, evaluate_thresholds, has_hard_failure, run_corpus

_MODEL_ENV = {
    "extract": config.ENV_EXTRACT_MODEL,
    "explain": config.ENV_EXPLAIN_MODEL,
    "letter": config.ENV_LETTER_MODEL,
}

FAKE_REPORT_PATH = config.EVALS_DIR / "results" / "fake-run.md"


def default_out(mode: str) -> Path:
    """Default report path. A fake run never uses the real report's name."""
    return FAKE_REPORT_PATH if mode == "fake" else config.DEFAULT_REPORT_PATH


def _csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m evals",
        description="Run the eval harness on synthetic bills and write a markdown report.",
    )
    p.add_argument("--fake", action="store_true", help="use the oracle instead of a model (offline smoke test)")
    p.add_argument("--cache-only", action="store_true", help="answer from the cache only; never call the model")
    p.add_argument("--max-calls", type=int, default=config.DEFAULT_MAX_CALLS,
                   help=f"stop real model calls after N (default {config.DEFAULT_MAX_CALLS})")
    p.add_argument("--strict", action="store_true", help="exit 1 if any threshold fails")
    p.add_argument("--scenarios", type=_csv, default=None, help="comma-separated scenarios (default: all)")
    p.add_argument("--seeds", type=_csv, default=None, help="comma-separated seeds (default: 1)")
    p.add_argument("--styles", type=_csv, default=None, help="comma-separated layouts (default: all)")
    p.add_argument("--out", type=Path, default=None, help="report path (default depends on the mode)")
    p.add_argument("--cache-dir", type=Path, default=config.DEFAULT_CACHE_DIR, help="model-reply cache folder")
    return p


def _fail(err: TextIO, message: str) -> int:
    print(f"error: {message}", file=err)
    return config.EXIT_USAGE


def main(
    argv: Sequence[str] | None = None,
    *,
    build_client: Callable[[str], LLMClient] = make_client,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    """Run the eval. ``build_client(model_env_var)`` makes the real client for one task."""
    out = out or sys.stdout
    err = err or sys.stderr

    try:
        args = _build_parser().parse_args(argv)
    except SystemExit as exc:  # argparse already printed a usage message
        return config.EXIT_USAGE if exc.code not in (0, None) else config.EXIT_OK

    if args.fake and args.cache_only:
        return _fail(err, "--fake and --cache-only cannot be used together")
    if args.max_calls < 0:
        return _fail(err, "--max-calls must be 0 or more")

    mode = "fake" if args.fake else ("cache-only" if args.cache_only else "real")
    try:
        report_path = ensure_not_private(args.out if args.out is not None else default_out(mode))
        cache_dir = ensure_not_private(args.cache_dir)
    except PrivatePathError as exc:
        return _fail(err, str(exc))

    try:
        seeds = None if args.seeds is None else [int(s) for s in args.seeds]
    except ValueError:
        return _fail(err, "--seeds must be whole numbers, for example 1,2,3")
    try:
        bills = build_corpus(scenarios=args.scenarios, seeds=seeds, styles=args.styles)
    except ValueError as exc:
        return _fail(err, str(exc))

    # --- the client factory ---------------------------------------------------------
    if mode == "fake":
        factory = OracleClient(bills)
    else:
        missing = [name for name in _MODEL_ENV.values() if not os.environ.get(name, "").strip()]
        if mode == "real" and not os.environ.get(config.ENV_API_KEY, "").strip():
            missing.insert(0, config.ENV_API_KEY)
        if missing:
            return _fail(err, "missing environment variable(s): " + ", ".join(missing) +
                         ". Set them, or use --fake for an offline smoke test.")
        models = {task: os.environ[name].strip() for task, name in _MODEL_ENV.items()}
        inners: dict[str, LLMClient | None] = {task: None for task in TASKS}
        if mode == "real":
            try:
                inners = {task: build_client(name) for task, name in _MODEL_ENV.items()}
            except Exception as exc:  # noqa: BLE001 - a short message, never a traceback
                return _fail(err, f"could not start the model client ({type(exc).__name__})")
        factory = CachingClient(
            inners, models, cache_dir, cache_only=(mode == "cache-only"), max_calls=args.max_calls
        )

    print(f"Running {len(bills)} bills in {mode} mode.", file=out)
    result = run_corpus(bills, factory, mode=mode, progress=lambda line: print(line, file=out))

    try:
        write_report(result, report_path)
    except OSError as exc:
        return _fail(err, f"could not write the report ({type(exc).__name__})")

    stats = result.stats
    failed = [r for r in evaluate_thresholds(result) if r.passed is False]
    print(f"Report written to {report_path}", file=out)
    print(f"Cache: {stats.hits} hits, {stats.misses} misses, {stats.real_calls} real calls"
          + (" (call budget reached)" if stats.budget_hit else ""), file=out)
    print(f"Thresholds failed: {len(failed)} of {len(config.THRESHOLDS)}", file=out)
    if mode == "fake":
        print("This was a FAKE ORACLE run: the numbers test the harness, not a model.", file=out)

    if has_hard_failure(result):
        print("HARD FAILURE: see the report.", file=err)
        return config.EXIT_FAILED
    if args.strict and any_threshold_failed(result):
        return config.EXIT_FAILED
    return config.EXIT_OK


if __name__ == "__main__":
    # Read the repo-root .env (if any). Real environment variables win. Nothing is printed.
    load_env()
    sys.exit(main())
