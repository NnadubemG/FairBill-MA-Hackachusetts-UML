"""Score flags: does a bill read by the model still get the right flags?

Flags come from ``core.analyze`` only; the harness never makes its own. For each bill:

- **Pipeline run:** ``core.analyze`` on the *extracted* lines. Each flag is mapped back to a
  truth line id through the extraction matching. A flag on an extracted line that has no
  truth match maps to ``None`` and counts as a false positive.
- **Oracle run:** ``core.analyze`` on the *truth* lines, compared with ``expected_flags``.
  Any difference is a ``/core`` self-check failure (it points at /core or /synthetic, not at
  extraction).

Counts are additive, like the extraction counts. A rate with nothing to measure is ``None``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence, get_args

from contracts.types import Flag, FlagType, LineItem, SyntheticBill
from core.engine import analyze as core_analyze

from .align import Alignment
from .corpus import Bill
from .score_extract import rate

FLAG_TYPES: tuple[str, ...] = tuple(get_args(FlagType))

# A flag pair: (truth line id or None when unmatched, flag type).
Pair = tuple[str | None, str]


def run_core(lines: Sequence[LineItem], truth: SyntheticBill) -> list[Flag]:
    """Run /core on ``lines`` with the bill's own reference data."""
    return list(
        core_analyze(
            lines,
            truth.price_references,
            quantity_limits=truth.quantity_limits,
            bundle_pairs=truth.bundle_pairs,
        )
    )


def _merge(a: dict[str, int], b: dict[str, int]) -> dict[str, int]:
    out = dict(a)
    for key, value in b.items():
        out[key] = out.get(key, 0) + value
    return out


@dataclass(frozen=True)
class FlagCounts:
    """Additive flag counts."""

    bills: int = 0
    planted: dict[str, int] = field(default_factory=dict)  # by flag type
    caught: dict[str, int] = field(default_factory=dict)
    false_positives: dict[str, int] = field(default_factory=dict)  # by flag type
    clean_bills: int = 0
    clean_bills_with_fp: int = 0
    no_issue_bills: int = 0  # bills with no expected flags (clean and injection)
    no_issue_bills_with_fp: int = 0
    core_self_check_mismatches: int = 0
    core_errors: int = 0

    def __add__(self, other: "FlagCounts") -> "FlagCounts":
        return FlagCounts(
            bills=self.bills + other.bills,
            planted=_merge(self.planted, other.planted),
            caught=_merge(self.caught, other.caught),
            false_positives=_merge(self.false_positives, other.false_positives),
            clean_bills=self.clean_bills + other.clean_bills,
            clean_bills_with_fp=self.clean_bills_with_fp + other.clean_bills_with_fp,
            no_issue_bills=self.no_issue_bills + other.no_issue_bills,
            no_issue_bills_with_fp=self.no_issue_bills_with_fp + other.no_issue_bills_with_fp,
            core_self_check_mismatches=self.core_self_check_mismatches + other.core_self_check_mismatches,
            core_errors=self.core_errors + other.core_errors,
        )

    def catch_rate(self, flag_type: str) -> float | None:
        return rate(self.caught.get(flag_type, 0), self.planted.get(flag_type, 0))

    @property
    def total_planted(self) -> int:
        return sum(self.planted.values())

    @property
    def total_caught(self) -> int:
        return sum(self.caught.values())

    @property
    def total_false_positives(self) -> int:
        return sum(self.false_positives.values())

    @property
    def overall_catch_rate(self) -> float | None:
        return rate(self.total_caught, self.total_planted)

    @property
    def min_catch_rate(self) -> float | None:
        """The lowest catch rate among types that have planted flags (None if none do)."""
        rates = [self.catch_rate(t) for t in self.planted if self.planted[t] > 0]
        rates = [r for r in rates if r is not None]
        return min(rates) if rates else None

    @property
    def fp_rate_clean(self) -> float | None:
        return rate(self.clean_bills_with_fp, self.clean_bills)

    @property
    def fp_rate_no_issue(self) -> float | None:
        return rate(self.no_issue_bills_with_fp, self.no_issue_bills)


def total(counts: Iterable[FlagCounts]) -> FlagCounts:
    result = FlagCounts()
    for c in counts:
        result = result + c
    return result


@dataclass(frozen=True)
class BillFlagScore:
    """The flag score for one bill in one layout."""

    bill_id: str
    style: str
    scenario: str
    counts: FlagCounts
    missed: tuple[Pair, ...]
    false_positive_pairs: tuple[Pair, ...]
    oracle_matches_expected: bool


def _sorted_pairs(pairs: Iterable[Pair]) -> tuple[Pair, ...]:
    return tuple(sorted(pairs, key=lambda p: (p[0] is None, p[0] or "", p[1])))


def score_flags(bill: Bill, alignment: Alignment, extracted_lines: Sequence[LineItem]) -> BillFlagScore:
    """Score the flags for one bill. ``alignment`` is the extraction matching for this bill."""
    truth = bill.truth
    expected: set[Pair] = {(e.line_item_id, e.flag_type) for e in truth.expected_flags}

    # Which truth line does each extracted line id stand for?
    truth_id_of = {pair.extracted.id: pair.truth.id for pair in alignment.pairs}

    core_errors = 0
    try:
        flags = run_core(extracted_lines, truth)
    except Exception:  # noqa: BLE001 - a /core crash must not stop the whole eval
        flags, core_errors = [], 1
    got: set[Pair] = {(truth_id_of.get(f.line_item_id), f.flag_type) for f in flags}

    try:
        oracle: set[Pair] = {(f.line_item_id, f.flag_type) for f in run_core(truth.line_items, truth)}
    except Exception:  # noqa: BLE001
        oracle, core_errors = set(), core_errors + 1
    oracle_ok = oracle == expected

    caught = got & expected
    missed = expected - got
    false_pos = got - expected

    planted: dict[str, int] = {}
    caught_by_type: dict[str, int] = {}
    fp_by_type: dict[str, int] = {}
    for _, flag_type in expected:
        planted[flag_type] = planted.get(flag_type, 0) + 1
    for _, flag_type in caught:
        caught_by_type[flag_type] = caught_by_type.get(flag_type, 0) + 1
    for _, flag_type in false_pos:
        fp_by_type[flag_type] = fp_by_type.get(flag_type, 0) + 1

    is_clean = bill.scenario == "clean"
    no_issue = not expected
    counts = FlagCounts(
        bills=1,
        planted=planted,
        caught=caught_by_type,
        false_positives=fp_by_type,
        clean_bills=1 if is_clean else 0,
        clean_bills_with_fp=1 if (is_clean and false_pos) else 0,
        no_issue_bills=1 if no_issue else 0,
        no_issue_bills_with_fp=1 if (no_issue and false_pos) else 0,
        core_self_check_mismatches=0 if oracle_ok else 1,
        core_errors=core_errors,
    )
    return BillFlagScore(
        bill_id=bill.bill_id,
        style=bill.style,
        scenario=bill.scenario,
        counts=counts,
        missed=_sorted_pairs(missed),
        false_positive_pairs=_sorted_pairs(false_pos),
        oracle_matches_expected=oracle_ok,
    )


__all__ = [
    "FLAG_TYPES", "Pair", "run_core", "FlagCounts", "total", "BillFlagScore", "score_flags",
]
