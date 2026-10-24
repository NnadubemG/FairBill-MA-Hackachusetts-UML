"""Extraction handler: orchestrates the full pipeline.

Flow (design doc):
  bytes -> prompts -> client.invoke -> validate -> (retry once) -> postprocess
        -> code/confidence rules -> ExtractionResult

The handler never raises for an expected model failure (task 8 adds the fallback). In
task 7 it wires the happy path plus the single validation retry. All string content
from the bill is untrusted; nothing is logged or written to disk.
"""

from __future__ import annotations

from pathlib import Path

from . import prompts
from .bedrock_client import BedrockClient
from .codes import apply_code_and_confidence, load_known_codes
from .config import Thresholds
from .models import BillMetadata, Confidence, ExtractionResult
from .postprocess import normalize_and_merge, normalize_date, normalize_money
from .validate import ValidationOutcome, validate_lines

# Bill-level warnings (no bill content).
WARN_SOME_LINES_DROPPED = (
    "Some line items could not be read reliably and were left out. "
    "Please review and add any missing lines by hand."
)
WARN_NO_LINES = (
    "No line items could be read from this document automatically. "
    "You can enter the lines by hand."
)
WARN_EXTRACTION_UNAVAILABLE = (
    "Automatic extraction was unavailable. Please enter the bill lines by hand."
)


def _parse_metadata(raw: str) -> BillMetadata:
    """Pull bill-level metadata from the model envelope. Never guesses values."""
    import json

    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return BillMetadata()
    if not isinstance(parsed, dict):
        return BillMetadata()
    meta = parsed.get("metadata")
    if not isinstance(meta, dict):
        return BillMetadata()

    hospital = meta.get("hospital_name")
    hospital = hospital if isinstance(hospital, str) and hospital.strip() else None

    date = normalize_date(meta.get("statement_date")) if meta.get("statement_date") else None
    total = normalize_money(meta.get("total"))

    return BillMetadata(hospital_name=hospital, statement_date=date, total=total)


def _model_confidence(raw: str) -> dict[str, Confidence]:
    """Read optional per-line confidence hints the model may include.

    The contract LineItem has no confidence field, so if the model emits confidence
    it does so in a side channel (`confidence_hints`: {line_id: "high|medium|low"}).
    Missing or malformed -> empty dict (every line defaults to low downstream).
    """
    import json

    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    hints = parsed.get("confidence_hints")
    if not isinstance(hints, dict):
        return {}
    out: dict[str, Confidence] = {}
    for key, val in hints.items():
        if isinstance(key, str) and val in ("high", "medium", "low"):
            out[key] = val  # type: ignore[assignment]
    return out


def extract(
    bill_bytes: bytes,
    content_type: str,
    *,
    client: BedrockClient,
    procedures_path: Path | None = None,
    thresholds: Thresholds | None = None,
) -> ExtractionResult:
    """Extract line items from a bill using the given model client.

    ``client`` is injected (use FakeBedrockClient for dev/tests). This task-7 version
    wires the happy path and the single validation retry. The broad model-failure
    fallback (never raise) is completed in task 8.
    """
    warnings: list[str] = []

    # --- Model call + validation, with a deterministic fallback -------------
    # Any failure from building prompts, calling the model, or validating is caught
    # and turned into a safe empty result. The handler never raises for an expected
    # model/content failure (R7). We do not log the exception message or any bill
    # content; only a generic warning is surfaced.
    try:
        system = prompts.build_system_prompt()
        content = prompts.build_user_content(bill_bytes, content_type)

        # First attempt.
        raw = client.invoke(system=system, content=content)
        outcome: ValidationOutcome = validate_lines(raw)

        # Retry once if nothing validated or the model emitted invalid lines.
        if outcome.parse_error is not None or outcome.errors:
            hint = outcome.parse_error or (
                outcome.errors[0].message if outcome.errors else "output did not validate"
            )
            raw_retry = client.invoke(system=system, content=content, repair_hint=hint)
            retry_outcome = validate_lines(raw_retry)
            # Prefer the retry if it produced at least as many valid lines.
            if len(retry_outcome.line_items) >= len(outcome.line_items):
                if retry_outcome.errors or retry_outcome.parse_error:
                    warnings.append(WARN_SOME_LINES_DROPPED)
                outcome = retry_outcome
                raw = raw_retry
            else:
                warnings.append(WARN_SOME_LINES_DROPPED)
        elif not outcome.line_items:
            # Clean parse but zero lines (e.g. blank page).
            warnings.append(WARN_NO_LINES)
    except Exception:  # noqa: BLE001 - deterministic fallback for ANY model failure
        # No content or exception detail is logged or surfaced (privacy).
        return ExtractionResult(
            line_items=[],
            metadata=BillMetadata(),
            line_confidence=[],
            warnings=[WARN_EXTRACTION_UNAVAILABLE],
        )

    # Post-process: normalize + merge continuation rows.
    lines = normalize_and_merge(outcome.line_items)

    # Code + confidence rules.
    known = load_known_codes(procedures_path)
    model_conf = _model_confidence(raw)
    lines, confidences, code_warnings = apply_code_and_confidence(
        lines, model_conf, known_codes=known, thresholds=thresholds
    )
    warnings.extend(code_warnings)

    if not lines and WARN_NO_LINES not in warnings:
        warnings.append(WARN_NO_LINES)

    metadata = _parse_metadata(raw)

    return ExtractionResult(
        line_items=lines,
        metadata=metadata,
        line_confidence=confidences,
        warnings=warnings,
    )


__all__ = [
    "extract",
    "WARN_SOME_LINES_DROPPED",
    "WARN_NO_LINES",
    "WARN_EXTRACTION_UNAVAILABLE",
]
