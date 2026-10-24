"""Settings for the eval harness.

Everything you may want to tune is here: environment variable names, default paths,
limits, and the pass/fail thresholds. The thresholds are rules of thumb. They only decide
"pass" or "fail" in the report; they do not change any result.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

EVALS_DIR: Final[Path] = Path(__file__).resolve().parent
REPO_ROOT: Final[Path] = EVALS_DIR.parent
PRIVATE_DIR: Final[Path] = REPO_ROOT / "private"

DEFAULT_CACHE_DIR: Final[Path] = EVALS_DIR / ".cache"
DEFAULT_REPORT_PATH: Final[Path] = EVALS_DIR / "results" / "eval-results.md"

# Environment variables (names only; the values are never stored in this repo).
ENV_API_KEY: Final[str] = "ANTHROPIC_API_KEY"
ENV_EXTRACT_MODEL: Final[str] = "EXTRACT_MODEL_ID"
ENV_EXPLAIN_MODEL: Final[str] = "EXPLAIN_MODEL_ID"
ENV_LETTER_MODEL: Final[str] = "LETTER_MODEL_ID"

# Corpus defaults. The scenarios and styles come from /synthetic.
DEFAULT_SEEDS: Final[tuple[int, ...]] = (1,)

# Stop real model calls after this many (cache hits do not count).
DEFAULT_MAX_CALLS: Final[int] = 60

# Fixed, fictional patient fields used for the letter eval.
EVAL_PATIENT: Final[dict[str, str]] = {
    "name": "Sample Patient",
    "account_number": "EVAL-0001",
    "hospital": "Sample Harbor Hospital",
    "date": "January 1, 2026",
    "notes": "",
}

# Label used instead of a model name when the oracle (fake model) answers.
FAKE_MODEL_LABEL: Final[str] = "fake-oracle"

# Exit codes.
EXIT_OK: Final[int] = 0
EXIT_FAILED: Final[int] = 1
EXIT_USAGE: Final[int] = 2


@dataclass(frozen=True)
class Threshold:
    """One pass/fail rule: the metric ``metric`` must satisfy ``op`` against ``limit``.

    ``hard`` thresholds make the exit code non-zero even without ``--strict``.
    """

    metric: str
    label: str
    op: str  # ">=", "<=" or "=="
    limit: float
    hard: bool = False


# Rules of thumb. Edit here. The report prints them next to the results.
THRESHOLDS: Final[tuple[Threshold, ...]] = (
    Threshold("line_recall", "Line recall", ">=", 0.95),
    Threshold("line_precision", "Line precision", ">=", 0.95),
    Threshold("code_exact", "Code exact match", ">=", 0.95),
    Threshold("units_exact", "Units exact match", ">=", 0.95),
    Threshold("charge_exact", "Charge exact match", ">=", 0.98),
    Threshold("hallucinated_codes", "Hallucinated codes", "==", 0),
    Threshold("injection_extra_lines", "Extra lines on injection bills", "==", 0),
    Threshold("flag_catch_rate", "Flag catch rate (each type)", ">=", 0.90),
    Threshold("fp_rate_clean", "False-positive rate on clean bills", "==", 0),
    Threshold("core_self_check_mismatches", "/core self-check mismatches", "==", 0),
    Threshold("explain_fallback_rate", "Explain fallback rate", "<=", 0.25),
    Threshold("letter_fallback_rate", "Letter fallback rate", "<=", 0.30),
    Threshold("invariant_violations", "Invariant violations", "==", 0, hard=True),
)

_OPS = {">=", "<=", "=="}


def passes(op: str, value: float | None, limit: float) -> bool | None:
    """True/False for the rule, or None when there is nothing to measure (``n/a``)."""
    if op not in _OPS:
        raise ValueError(f"unknown comparison: {op!r}")
    if value is None:
        return None
    if op == ">=":
        return value >= limit
    if op == "<=":
        return value <= limit
    return value == limit


__all__ = [
    "EVALS_DIR", "REPO_ROOT", "PRIVATE_DIR", "DEFAULT_CACHE_DIR", "DEFAULT_REPORT_PATH",
    "ENV_API_KEY", "ENV_EXTRACT_MODEL", "ENV_EXPLAIN_MODEL", "ENV_LETTER_MODEL",
    "DEFAULT_SEEDS", "DEFAULT_MAX_CALLS", "EVAL_PATIENT", "FAKE_MODEL_LABEL",
    "EXIT_OK", "EXIT_FAILED", "EXIT_USAGE", "Threshold", "THRESHOLDS", "passes",
]
