"""Code and confidence rules for extracted line items (spec task 6).

These rules decide two things per line:

1. Whether the model's billing code is trustworthy. The model must never guess a
   code. A line the model marked unsure of, or a code we cannot confirm, is handled
   conservatively: unknown codes become null, and anything we cannot confirm is
   marked for user confirmation.
2. The per-line confidence signal and ``needs_confirmation`` flag, carried in the
   extraction wrapper (``LineConfidence``), NOT on the contract ``LineItem``.

Loading the known-code set from ``/data/processed/procedures.json`` is optional: if
the file is absent (ND has not produced it yet) we skip the known-code check, record
a warning, and never error. We never invent a code or a confirmation decision.

Pure except for one explicit file read, which is guarded and side-effect free.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from ._contracts import LineItem
from .config import Thresholds, is_below
from .models import Confidence, LineConfidence

# Default location of ND's curated procedures file. Optional.
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROCEDURES_PATH = _REPO_ROOT / "data" / "processed" / "procedures.json"

CODE_CHECK_UNAVAILABLE = (
    "Code validation was unavailable (procedures list not found); "
    "codes were not checked against the curated list."
)


def load_known_codes(path: Path | None = None) -> set[str] | None:
    """Return the set of curated codes, or None if the file is absent/unreadable.

    None means "cannot check" (caller skips the check + warns). An empty set means
    "file present but no codes" (every code is treated as unknown). We distinguish
    the two on purpose: absence is not emptiness.
    """
    p = path or DEFAULT_PROCEDURES_PATH
    try:
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    codes: set[str] = set()
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and isinstance(item.get("code"), str):
                codes.add(item["code"])
    return codes


def _clear_code(line: LineItem) -> LineItem:
    """Return a copy with code and code_system cleared (model was unsure)."""
    return replace(line, code=None, code_system=None)


def apply_code_and_confidence(
    lines: list[LineItem],
    model_confidence: dict[str, Confidence],
    *,
    known_codes: set[str] | None,
    thresholds: Thresholds | None = None,
) -> tuple[list[LineItem], list[LineConfidence], list[str]]:
    """Apply code + confidence rules.

    Args:
        lines: normalized line items (post task 5).
        model_confidence: per-line id -> confidence the model reported. Missing id
            defaults to "low" (we assume unsure if the model did not say).
        known_codes: curated code set, or None if the check is unavailable.
        thresholds: confirmation threshold config.

    Returns:
        (line_items, line_confidence, warnings).

    Rules:
        - A line whose model confidence is "low" AND has a code -> code cleared to
          null (treated as a guess we will not trust).
        - A line with code == null -> confidence forced to "low",
          needs_confirmation = true.
        - A non-null code NOT in known_codes -> needs_confirmation = true (code kept).
        - known_codes is None -> skip the membership check, add one warning.
        - confidence below threshold -> needs_confirmation = true.
    """
    th = thresholds or Thresholds()
    out_lines: list[LineItem] = []
    confidences: list[LineConfidence] = []
    warnings: list[str] = []

    if known_codes is None:
        warnings.append(CODE_CHECK_UNAVAILABLE)

    for line in lines:
        conf: Confidence = model_confidence.get(line.id, "low")
        needs = False

        # 1. Low-confidence coded line: do not trust the code; clear it.
        if line.code is not None and conf == "low":
            line = _clear_code(line)

        # 2. Null code (originally, or just cleared): force low + confirm.
        if line.code is None:
            conf = "low"
            needs = True
        else:
            # 3. Known-code membership check (only when we have the set).
            if known_codes is not None and line.code not in known_codes:
                needs = True

        # 4. Confidence below the confirmation threshold -> confirm.
        if is_below(conf, th.confirm_below):
            needs = True

        out_lines.append(line)
        confidences.append(
            LineConfidence(line_item_id=line.id, confidence=conf, needs_confirmation=needs)
        )

    return out_lines, confidences, warnings


__all__ = [
    "DEFAULT_PROCEDURES_PATH",
    "CODE_CHECK_UNAVAILABLE",
    "load_known_codes",
    "apply_code_and_confidence",
]
