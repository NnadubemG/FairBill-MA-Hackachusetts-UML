"""Hard-failure checks on what explain and letter produce.

These are rules that must hold for every output, whatever the model said. The handlers
already enforce them with their own gates, so a violation here means a gate has a hole. Any
violation is a "hard failure": the exit code is non-zero even without ``--strict``.

Violations name a bill id, a layout, a kind, and an id. They never hold text.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Sequence

from jsonschema import Draft7Validator

from backend.explain.checks import figures, has_banned_word
from backend.letter.templates import TOP_LINE
from contracts.types import Flag, LetterDraft

from . import config

KINDS = (
    "stage_error",
    "explain_missing", "explain_banned_word", "explain_figure",
    "letter_banned_word", "letter_schema", "letter_unknown_line", "letter_top_line",
)

_SCHEMA_PATH = config.REPO_ROOT / "contracts" / "letter-draft.schema.json"
_validator: Draft7Validator | None = None


def _letter_validator() -> Draft7Validator:
    global _validator
    if _validator is None:
        _validator = Draft7Validator(json.loads(_SCHEMA_PATH.read_text(encoding="utf-8")))
    return _validator


@dataclass(frozen=True)
class Violation:
    bill_id: str
    style: str
    kind: str
    ref: str  # a flag key (line id + flag type), "letter", or a stage name for stage_error


def check_explanations(bill_id: str, style: str, flags: Sequence[Flag]) -> list[Violation]:
    """Every explained flag has an explanation with no banned word and no invented figure."""
    out: list[Violation] = []
    for flag in flags:
        ref = f"{flag.line_item_id}:{flag.flag_type}"
        text = flag.explanation
        if not isinstance(text, str) or not text.strip():
            out.append(Violation(bill_id, style, "explain_missing", ref))
            continue
        if has_banned_word(text):
            out.append(Violation(bill_id, style, "explain_banned_word", ref))
        allowed: set[Decimal] = figures(f"{flag.reason} {flag.basis}")
        if flag.data_year is not None:
            allowed.add(Decimal(flag.data_year))
        if not figures(text) <= allowed:
            out.append(Violation(bill_id, style, "explain_figure", ref))
    return out


def check_letter(bill_id: str, style: str, draft: LetterDraft, line_ids: set[str]) -> list[Violation]:
    """The letter has no banned word, matches the contract, and cites only real lines."""
    out: list[Violation] = []
    subject, body = draft.subject, draft.body
    if not isinstance(subject, str) or not isinstance(body, str):
        return [Violation(bill_id, style, "letter_schema", "letter")]
    if has_banned_word(subject) or has_banned_word(body):
        out.append(Violation(bill_id, style, "letter_banned_word", "letter"))
    if list(_letter_validator().iter_errors(asdict(draft))):
        out.append(Violation(bill_id, style, "letter_schema", "letter"))
    if not set(draft.referenced_line_item_ids) <= line_ids:
        out.append(Violation(bill_id, style, "letter_unknown_line", "letter"))
    if body.split("\n", 1)[0] != TOP_LINE:
        out.append(Violation(bill_id, style, "letter_top_line", "letter"))
    return out


__all__ = ["KINDS", "Violation", "check_explanations", "check_letter"]
