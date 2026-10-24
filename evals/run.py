"""Run the whole eval: extract -> match -> flags -> explain -> letter -> invariants.

``run_corpus`` takes the bills and a client factory (the disk cache around a real client, or
the oracle) and returns a ``RunResult``. It never raises because a feature failed: each stage
is protected, and an unexpected crash becomes a hard failure (``stage_error``) in the result.

Explain and letter are measured on the flags that ``core.analyze`` makes from the TRUTH lines,
so they are judged on their own, apart from extraction mistakes.

Progress lines name bill ids and counts only.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Iterable, Protocol

from backend.explain.handler import explain
from backend.extract.handler import extract
from backend.extract.llm_client import LLMClient
from backend.letter.handler import generate_letter
from backend.letter.models import CODING_REVIEW, LetterRequest, PatientFields
from contracts.types import Flag

from . import config
from .align import Alignment
from .cache import CacheStats
from .corpus import Bill
from .invariants import Violation, check_explanations, check_letter
from .score_extract import BillExtractionScore, Counts, rate, score_bill, total as total_extract
from .score_flags import BillFlagScore, FlagCounts, run_core, score_flags, total as total_flags

TASKS = ("extract", "explain", "letter")


class ClientFactory(Protocol):
    """What the runner needs: the cache client, or the oracle."""

    stats: CacheStats

    def scoped(self, task: str, file_sha256: str) -> LLMClient: ...

    def model_for(self, task: str) -> str: ...


@dataclass(frozen=True)
class BillResult:
    """Everything measured for one bill in one layout."""

    bill_id: str
    style: str
    scenario: str
    extraction: BillExtractionScore | None
    flags: BillFlagScore | None
    explain_flags: int  # flags sent to explain
    explain_fallbacks: int
    letter_ran: bool
    letter_fallback: bool
    violations: tuple[Violation, ...]

    @property
    def key(self) -> str:
        return f"{self.bill_id}/{self.style}"


@dataclass(frozen=True)
class RunResult:
    """The outcome of one run. Plain numbers and ids, no bill text."""

    mode: str  # "real", "cache-only" or "fake"
    models: dict[str, str]  # task -> model label
    stats: CacheStats
    bills: tuple[BillResult, ...]

    # --- totals ----------------------------------------------------------------

    @property
    def extraction(self) -> Counts:
        return total_extract(b.extraction.counts for b in self.bills if b.extraction)

    @property
    def flags(self) -> FlagCounts:
        return total_flags(b.flags.counts for b in self.bills if b.flags)

    def extraction_by(self, attr: str) -> dict[str, Counts]:
        """Extraction counts grouped by ``style`` or ``scenario`` (keys sorted)."""
        groups: dict[str, list[Counts]] = {}
        for b in self.bills:
            if b.extraction:
                groups.setdefault(getattr(b, attr), []).append(b.extraction.counts)
        return {k: total_extract(v) for k, v in sorted(groups.items())}

    @property
    def explain_total(self) -> int:
        return sum(b.explain_flags for b in self.bills)

    @property
    def explain_fallbacks(self) -> int:
        return sum(b.explain_fallbacks for b in self.bills)

    @property
    def explain_fallback_rate(self) -> float | None:
        return rate(self.explain_fallbacks, self.explain_total)

    @property
    def letters(self) -> int:
        return sum(1 for b in self.bills if b.letter_ran)

    @property
    def letter_fallbacks(self) -> int:
        return sum(1 for b in self.bills if b.letter_ran and b.letter_fallback)

    @property
    def letter_fallback_rate(self) -> float | None:
        return rate(self.letter_fallbacks, self.letters)

    @property
    def violations(self) -> tuple[Violation, ...]:
        return tuple(v for b in self.bills for v in b.violations)

    # --- thresholds --------------------------------------------------------------

    def metric_values(self) -> dict[str, float | None]:
        """The value of every threshold metric (None = nothing to measure)."""
        e, f = self.extraction, self.flags
        return {
            "line_recall": e.line_recall,
            "line_precision": e.line_precision,
            "code_exact": e.code_exact,
            "units_exact": e.units_exact,
            "charge_exact": e.charge_exact,
            "hallucinated_codes": e.hallucinated_codes,
            "injection_extra_lines": e.injection_extra_lines,
            "flag_catch_rate": f.min_catch_rate,
            "fp_rate_clean": f.fp_rate_clean,
            "core_self_check_mismatches": f.core_self_check_mismatches,
            "explain_fallback_rate": self.explain_fallback_rate,
            "letter_fallback_rate": self.letter_fallback_rate,
            "invariant_violations": len(self.violations),
        }


@dataclass(frozen=True)
class ThresholdResult:
    threshold: config.Threshold
    value: float | None
    passed: bool | None  # None = n/a


def evaluate_thresholds(result: RunResult) -> list[ThresholdResult]:
    """Pass/fail for every threshold, in config order."""
    values = result.metric_values()
    return [
        ThresholdResult(t, values.get(t.metric), config.passes(t.op, values.get(t.metric), t.limit))
        for t in config.THRESHOLDS
    ]


def has_hard_failure(result: RunResult) -> bool:
    """True if any hard threshold failed or any violation exists."""
    if result.violations:
        return True
    return any(r.threshold.hard and r.passed is False for r in evaluate_thresholds(result))


def any_threshold_failed(result: RunResult) -> bool:
    return any(r.passed is False for r in evaluate_thresholds(result))


# --- the runner ---------------------------------------------------------------


def _eval_patient() -> PatientFields:
    return PatientFields(**config.EVAL_PATIENT)


def run_bill(bill: Bill, factory: ClientFactory) -> BillResult:
    """Run one bill through every stage. Never raises."""
    sha = bill.file_sha256
    truth = bill.truth
    violations: list[Violation] = []

    def stage_error(stage: str) -> None:
        violations.append(Violation(bill.bill_id, bill.style, "stage_error", stage))

    # 1. Extract, match, and score the extraction.
    extraction = flags_score = None
    try:
        res = extract(bill.pdf, "application/pdf", client=factory.scoped("extract", sha))
        extraction = score_bill(bill.bill_id, bill.style, bill.scenario, truth.line_items, res)
        flags_score = score_flags(bill, extraction.alignment, list(res.line_items))
        # The matching holds the bill's lines. Scoring is done, so drop it: the stored result
        # keeps counts, ids and kinds only.
        extraction = replace(extraction, alignment=Alignment(pairs=(), missing=(), extra=()))
    except Exception:  # noqa: BLE001 - one bad stage must not stop the run
        stage_error("extract")

    # 2. Flags for explain and letter come from the truth lines.
    try:
        truth_flags: list[Flag] = run_core(truth.line_items, truth)
    except Exception:  # noqa: BLE001
        truth_flags = []
        stage_error("core")

    # 3. Explain.
    explain_fallbacks = 0
    if truth_flags:
        try:
            er = explain(truth_flags, client=factory.scoped("explain", sha))
            explain_fallbacks = er.fallback_count
            violations.extend(check_explanations(bill.bill_id, bill.style, er.flags))
        except Exception:  # noqa: BLE001
            stage_error("explain")
            explain_fallbacks = len(truth_flags)

    # 4. Letter (a coding review of those flags).
    letter_ran = letter_fallback = False
    if truth_flags:
        try:
            request = LetterRequest(
                letter_type=CODING_REVIEW,
                patient=_eval_patient(),
                flags=list(truth_flags),
                line_items=list(truth.line_items),
            )
            lr = generate_letter(request, client=factory.scoped("letter", sha))
            letter_ran, letter_fallback = True, lr.used_fallback
            violations.extend(
                check_letter(bill.bill_id, bill.style, lr.draft, {li.id for li in truth.line_items})
            )
        except Exception:  # noqa: BLE001
            stage_error("letter")

    return BillResult(
        bill_id=bill.bill_id,
        style=bill.style,
        scenario=bill.scenario,
        extraction=extraction,
        flags=flags_score,
        explain_flags=len(truth_flags),
        explain_fallbacks=explain_fallbacks,
        letter_ran=letter_ran,
        letter_fallback=letter_fallback,
        violations=tuple(violations),
    )


def run_corpus(
    bills: Iterable[Bill],
    factory: ClientFactory,
    *,
    mode: str,
    progress: Callable[[str], None] | None = None,
) -> RunResult:
    """Run every bill and collect the results."""
    results: list[BillResult] = []
    bill_list = list(bills)
    for index, bill in enumerate(bill_list, start=1):
        result = run_bill(bill, factory)
        results.append(result)
        if progress is not None:
            progress(f"[{index}/{len(bill_list)}] {bill.key}: done")
    return RunResult(
        mode=mode,
        models={task: factory.model_for(task) for task in TASKS},
        stats=replace(factory.stats),
        bills=tuple(results),
    )


__all__ = [
    "TASKS", "ClientFactory", "BillResult", "RunResult", "ThresholdResult",
    "evaluate_thresholds", "has_hard_failure", "any_threshold_failed", "run_bill", "run_corpus",
]
