"""Analyze a confirmed bill: LineItem[] -> AnalysisResult.

Boundary-validates untrusted input, calls the deterministic /core engine with ND's
reference data, optionally runs Sam's explain function, and assembles an AnalysisResult.

Rules honored here:
- Never crash on bad input; return a clear, body-free error.
- Never log the request body or any line item content.
- All string fields from the bill are inert data, never instructions.
- explain is best-effort: if it is missing or fails, flags come back with explanation None
  and the analysis still succeeds.
- Numbers are never invented; price_references are passed through from the store.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import replace
from typing import Callable, Optional, Sequence

from contracts.types import AnalysisResult, Flag, LineItem

from core.engine import analyze as core_analyze

from .store import ReferenceStore, _norm_code

# Input bounds. Kept conservative; a real bill is well under these.
MAX_LINE_ITEMS = 200
MAX_STR = 256
MAX_CODE = 64
_ALLOWED_CODE_SYSTEMS = {"CPT", "HCPCS", "DRG", "REV", "ICD10", "OTHER"}


class AnalyzeError(ValueError):
    """Raised for invalid input at the boundary. Message is safe to return (no body)."""


def _check_str(value, field_name: str, limit: int, *, required: bool) -> Optional[str]:
    if value is None:
        if required:
            raise AnalyzeError(f"line item missing required field: {field_name}")
        return None
    if not isinstance(value, str):
        raise AnalyzeError(f"line item field {field_name} must be text")
    if len(value) > limit:
        raise AnalyzeError(f"line item field {field_name} is too long")
    return value


def _check_number(value, field_name: str, *, required: bool) -> Optional[float]:
    if value is None:
        if required:
            raise AnalyzeError(f"line item missing required field: {field_name}")
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AnalyzeError(f"line item field {field_name} must be a number")
    f = float(value)
    if not math.isfinite(f):
        raise AnalyzeError(f"line item field {field_name} must be a finite number")
    return f


def _to_line_item(raw, idx: int) -> LineItem:
    if not isinstance(raw, dict):
        raise AnalyzeError(f"line item {idx} must be an object")
    code_system = _check_str(raw.get("code_system"), "code_system", MAX_STR, required=False)
    if code_system is not None and code_system not in _ALLOWED_CODE_SYSTEMS:
        # Unknown system is inert data; drop to null rather than reject the whole bill.
        code_system = None
    return LineItem(
        id=_check_str(raw.get("id"), "id", MAX_STR, required=True),
        description=_check_str(raw.get("description"), "description", MAX_STR, required=True),
        billed_amount=_check_number(raw.get("billed_amount"), "billed_amount", required=True),
        code=_check_str(raw.get("code"), "code", MAX_CODE, required=False),
        code_system=code_system,  # type: ignore[arg-type]
        raw_description=_check_str(raw.get("raw_description"), "raw_description", MAX_STR, required=False),
        quantity=_check_number(raw.get("quantity"), "quantity", required=False),
        unit=_check_str(raw.get("unit"), "unit", MAX_STR, required=False),
        date_of_service=_check_str(raw.get("date_of_service"), "date_of_service", MAX_STR, required=False),
    )


def validate_line_items(raw_items) -> list[LineItem]:
    """Validate untrusted input into LineItems. Raises AnalyzeError on any problem."""
    if not isinstance(raw_items, list):
        raise AnalyzeError("line_items must be a list")
    if len(raw_items) > MAX_LINE_ITEMS:
        raise AnalyzeError(f"too many line items (max {MAX_LINE_ITEMS})")
    items = [_to_line_item(raw, i) for i, raw in enumerate(raw_items)]
    ids = [it.id for it in items]
    if len(set(ids)) != len(ids):
        raise AnalyzeError("line item ids must be unique")
    return items


def _safe_explain(
    explain: Optional[Callable[[list[Flag]], Sequence[Flag]]], flags: list[Flag]
) -> list[Flag]:
    """Run explain if provided; on any failure, return the original flags unchanged.

    The analysis never fails because of explain. A malformed return is ignored.
    """
    if explain is None:
        return flags
    try:
        result = explain(list(flags))
    except Exception:
        return flags
    if not isinstance(result, (list, tuple)) or len(result) != len(flags):
        return flags
    out: list[Flag] = []
    for original, maybe in zip(flags, result):
        if isinstance(maybe, Flag) and maybe.line_item_id == original.line_item_id \
                and maybe.flag_type == original.flag_type:
            out.append(maybe)
        else:
            out.append(original)
    return out


def analyze_bill(
    line_items,
    store: ReferenceStore,
    *,
    explain: Optional[Callable[[list[Flag]], Sequence[Flag]]] = None,
) -> AnalysisResult:
    """Confirmed line items + reference store -> AnalysisResult. See module docstring."""
    items = validate_line_items(line_items)

    flags = list(
        core_analyze(
            items,
            store.price_references,
            quantity_limits=store.quantity_limits,
            bundle_pairs=store.bundle_pairs,
        )
    )
    flags = _safe_explain(explain, flags)

    codes_on_bill = {_norm_code(it.code) for it in items if it.code}
    price_references = store.references_for(codes_on_bill)

    return AnalysisResult(
        line_items=items,
        flags=flags,
        price_references=price_references,
        letter_draft=None,
    )


def _asdict(result: AnalysisResult) -> dict:
    return dataclasses.asdict(result)


def handle(
    request_dict,
    store: Optional[ReferenceStore] = None,
    *,
    explain: Optional[Callable[[list[Flag]], Sequence[Flag]]] = None,
    processed_dir: Optional[str] = None,
) -> dict:
    """Parse a request dict, run analyze_bill, return a JSON-serializable response.

    On bad input returns {"error": "..."} with a body-free message. Never raises for
    client errors, never logs the request body.
    """
    try:
        if not isinstance(request_dict, dict):
            raise AnalyzeError("request must be an object")
        if store is None:
            from pipeline import config

            store = ReferenceStore.load(processed_dir or config.PROCESSED_DIR)
        result = analyze_bill(request_dict.get("line_items"), store, explain=explain)
        return _asdict(result)
    except AnalyzeError as exc:
        # Safe message only; never the input content.
        return {"error": str(exc)}
