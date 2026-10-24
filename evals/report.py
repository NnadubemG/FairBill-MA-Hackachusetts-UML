"""Turn a ``RunResult`` into a markdown report.

The report is deterministic: the same results always give the same text (no timestamps, no
random order). It holds numbers, ids, layouts and kinds only. It never holds the API key, a
model reply, or bill text. Table cells are escaped so a ``|`` or a line break cannot break a
table.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import config
from .corpus import ensure_not_private
from .run import RunResult, evaluate_thresholds, has_hard_failure
from .score_extract import KINDS as EXTRACTION_KINDS, Counts
from .score_flags import FLAG_TYPES

FAKE_BANNER = "**FAKE ORACLE - not a model.** These numbers only test the harness and the scoring code."
MAX_FAILURE_ROWS = 200

# Threshold metrics that are whole-number counts (the rest are rates).
COUNT_METRICS = {
    "hallucinated_codes", "injection_extra_lines", "core_self_check_mismatches", "invariant_violations",
}

_NEWLINES = re.compile(r"\s*[\r\n]+\s*")


def cell(value: object) -> str:
    """Make a value safe inside a markdown table cell."""
    text = _NEWLINES.sub(" ", str(value)).strip()
    return text.replace("|", "\\|")


def pct(value: float | None) -> str:
    """A rate as a percent with one decimal, or ``n/a``."""
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _table(header: list[str], rows: list[list[object]]) -> list[str]:
    lines = ["| " + " | ".join(cell(h) for h in header) + " |",
             "| " + " | ".join("---" for _ in header) + " |"]
    lines += ["| " + " | ".join(cell(c) for c in row) + " |" for row in rows]
    return lines


def _extraction_row(label: str, c: Counts) -> list[object]:
    return [
        label, c.bills, c.truth_lines, c.extracted_lines, pct(c.line_recall), pct(c.line_precision),
        pct(c.code_exact), pct(c.units_exact), pct(c.charge_exact), pct(c.date_exact),
        c.hallucinated_codes, c.fallback_bills,
    ]


_EXTRACTION_HEADER = [
    "Group", "Bills", "Truth lines", "Extracted lines", "Line recall", "Line precision",
    "Code exact", "Units exact", "Charge exact", "Date exact", "Hallucinated codes", "Fallback bills",
]


def _metric_text(metric: str, value: float | None) -> str:
    if value is None:
        return "n/a"
    return str(int(value)) if metric in COUNT_METRICS else pct(value)


def _rule_text(t: config.Threshold) -> str:
    limit = str(int(t.limit)) if t.metric in COUNT_METRICS else pct(t.limit)
    return f"{t.op} {limit}"


def _failure_rows(result: RunResult) -> list[list[object]]:
    rows: list[tuple[tuple, list[object]]] = []
    for b in result.bills:
        for v in b.violations:
            rows.append(((0, v.bill_id, v.style, v.kind, v.ref), [v.bill_id, v.style, f"HARD: {v.kind}", v.ref]))
        if b.extraction:
            order = {k: i for i, k in enumerate(EXTRACTION_KINDS)}
            for f in b.extraction.failures:
                rows.append(((1, f.bill_id, f.style, order.get(f.kind, 99), f.line_id),
                             [f.bill_id, f.style, f.kind, f.line_id]))
        if b.flags:
            for truth_id, flag_type in b.flags.missed:
                ref = f"{truth_id}:{flag_type}"
                rows.append(((2, b.bill_id, b.style, "missed_flag", ref), [b.bill_id, b.style, "missed_flag", ref]))
            for truth_id, flag_type in b.flags.false_positive_pairs:
                ref = f"{truth_id if truth_id is not None else 'unmatched'}:{flag_type}"
                rows.append(((3, b.bill_id, b.style, "false_positive_flag", ref),
                             [b.bill_id, b.style, "false_positive_flag", ref]))
            if not b.flags.oracle_matches_expected:
                rows.append(((0, b.bill_id, b.style, "core_self_check", ""),
                             [b.bill_id, b.style, "HARD: core_self_check", "core.analyze on truth"]))
        if b.explain_fallbacks:
            rows.append(((4, b.bill_id, b.style, "explain_fallback", ""),
                         [b.bill_id, b.style, "explain_fallback", f"{b.explain_fallbacks} of {b.explain_flags} flags"]))
        if b.letter_ran and b.letter_fallback:
            rows.append(((5, b.bill_id, b.style, "letter_fallback", ""),
                         [b.bill_id, b.style, "letter_fallback", "letter"]))
    rows.sort(key=lambda item: item[0])
    return [row for _, row in rows]


def render(result: RunResult) -> str:
    """Build the whole report as one string."""
    out: list[str] = ["# Eval results", ""]
    if result.mode == "fake":
        out += [FAKE_BANNER, ""]

    # --- run info -------------------------------------------------------------------
    s = result.stats
    styles = sorted({b.style for b in result.bills})
    scenarios = sorted({b.scenario for b in result.bills})
    budget = "reached (some calls were skipped)" if s.budget_hit else "not reached"
    out += ["## Run", ""]
    out += _table(["Item", "Value"], [
        ["Mode", result.mode],
        ["Extract model", result.models.get("extract", "")],
        ["Explain model", result.models.get("explain", "")],
        ["Letter model", result.models.get("letter", "")],
        ["Bills", len(result.bills)],
        ["Layouts", ", ".join(styles)],
        ["Scenarios", ", ".join(scenarios)],
        ["Cache hits", s.hits],
        ["Cache misses", s.misses],
        ["Real model calls", s.real_calls],
        ["Failed model calls", s.failures],
        ["Cache-only misses", s.cache_only_misses],
        ["Call budget", budget],
    ])
    out.append("")

    # --- extraction -----------------------------------------------------------------
    e = result.extraction
    out += ["## Extraction accuracy", ""]
    rows = [_extraction_row("Overall", e)]
    rows += [_extraction_row(f"Layout: {k}", c) for k, c in result.extraction_by("style").items()]
    rows += [_extraction_row(f"Scenario: {k}", c) for k, c in result.extraction_by("scenario").items()]
    out += _table(_EXTRACTION_HEADER, rows)
    out += [
        "",
        f"- Confirmation recall (lines with no code that were marked for confirmation): {pct(e.confirmation_recall)}",
        f"- Extra lines on injection bills: {e.injection_extra_lines}",
        "- Lines are matched one to one by code, amount and quantity. One wrong field still matches "
        "(and lowers that field's rate); two wrong fields count as a missing line plus an extra line.",
        "",
    ]

    # --- flags ----------------------------------------------------------------------
    f = result.flags
    out += ["## Flags (extraction -> /core)", ""]
    out += _table(
        ["Flag type", "Planted", "Caught", "Catch rate", "False positives"],
        [[t, f.planted.get(t, 0), f.caught.get(t, 0), pct(f.catch_rate(t)), f.false_positives.get(t, 0)]
         for t in FLAG_TYPES]
        + [["All types", f.total_planted, f.total_caught, pct(f.overall_catch_rate), f.total_false_positives]],
    )
    out += [
        "",
        f"- False-positive rate on clean bills: {pct(f.fp_rate_clean)} ({f.clean_bills_with_fp} of {f.clean_bills})",
        f"- False-positive rate on bills with no planted flags: {pct(f.fp_rate_no_issue)} "
        f"({f.no_issue_bills_with_fp} of {f.no_issue_bills})",
        f"- /core self-check mismatches (core on the true lines vs expected flags): {f.core_self_check_mismatches}",
        f"- /core crashes: {f.core_errors}",
        "",
    ]

    # --- explain and letter ----------------------------------------------------------
    out += ["## Explain and letter", ""]
    out += _table(["Feature", "Items", "Fallbacks", "Fallback rate"], [
        ["Explain (flags)", result.explain_total, result.explain_fallbacks, pct(result.explain_fallback_rate)],
        ["Letter (bills with flags)", result.letters, result.letter_fallbacks, pct(result.letter_fallback_rate)],
    ])
    out += ["", f"- Invariant violations (hard failures): {len(result.violations)}", ""]

    # --- thresholds -----------------------------------------------------------------
    results = evaluate_thresholds(result)
    failed = [r for r in results if r.passed is False]
    out += ["## Thresholds (rules of thumb, set in evals/config.py)", ""]
    out += _table(["Metric", "Value", "Rule", "Result"], [
        [r.threshold.label + (" (hard)" if r.threshold.hard else ""),
         _metric_text(r.threshold.metric, r.value), _rule_text(r.threshold),
         "n/a" if r.passed is None else ("PASS" if r.passed else "FAIL")]
        for r in results
    ])
    out += [
        "",
        f"Summary: {len(failed)} of {len(results)} thresholds failed. "
        f"Hard failure: {'YES' if has_hard_failure(result) else 'no'}.",
        "",
    ]

    # --- failures -------------------------------------------------------------------
    rows = _failure_rows(result)
    out += ["## Failures", ""]
    if not rows:
        out += ["None.", ""]
    else:
        shown = rows[:MAX_FAILURE_ROWS]
        out += _table(["Bill", "Layout", "Kind", "Line"], shown)
        if len(rows) > len(shown):
            out += ["", f"... and {len(rows) - len(shown)} more."]
        out.append("")

    out += [
        "## Notes",
        "",
        "- Bills are fictional and come from /synthetic. Their PDFs are clean text PDFs, so extraction "
        "results here are better than they would be on a scan or a phone photo.",
        "- Thresholds are rules of thumb. They only decide pass or fail; they do not change any result.",
        "- This report holds numbers, ids, layouts and kinds only. It holds no bill text and no model replies.",
        "",
    ]
    return "\n".join(out)


def write_report(result: RunResult, path: str | Path) -> Path:
    """Write the report to ``path`` (never inside /private). Returns the path written."""
    target = ensure_not_private(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(result), encoding="utf-8")
    return target


__all__ = ["FAKE_BANNER", "MAX_FAILURE_ROWS", "cell", "pct", "render", "write_report"]
