"""Validate model output against the canonical LineItem contract.

Every line the handler returns must validate against
``/contracts/line-item.schema.json``. Lines that fail validation are never returned;
they are reported so the handler can retry once and then warn about what was dropped.

Uses the ``jsonschema`` library (already available). No model output is logged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft7Validator

from ._contracts import LineItem
from .jsonutil import parse_model_json
from .schema import line_item_schema


@dataclass(frozen=True)
class LineError:
    """A single rejected line: its index in the model output and why it failed.

    ``message`` describes the schema violation (field names only). It never includes
    the full offending value, to avoid logging bill content downstream.
    """

    index: int
    message: str


@dataclass(frozen=True)
class ValidationOutcome:
    """Result of validating model output.

    - ``line_items``: the lines that validated, as contract ``LineItem`` objects.
    - ``errors``: one ``LineError`` per rejected line.
    - ``parse_error``: set if the raw string was not valid JSON at all.
    """

    line_items: list[LineItem]
    errors: list[LineError]
    parse_error: str | None = None


def _validator() -> Draft7Validator:
    return Draft7Validator(line_item_schema())


def _to_line_item(obj: dict[str, Any]) -> LineItem:
    """Build a contract LineItem from a validated dict.

    Only known contract fields are passed through; the schema's
    ``additionalProperties: false`` already guarantees no extras survived validation.
    """
    return LineItem(
        id=obj["id"],
        description=obj["description"],
        billed_amount=obj["billed_amount"],
        code=obj.get("code"),
        code_system=obj.get("code_system"),
        raw_description=obj.get("raw_description"),
        quantity=obj.get("quantity"),
        unit=obj.get("unit"),
        date_of_service=obj.get("date_of_service"),
    )


def validate_lines(raw: str) -> ValidationOutcome:
    """Validate a raw model response string into contract ``LineItem`` objects.

    Accepts either the full envelope ``{"line_items": [...], "metadata": {...}}`` or a
    bare array of line objects. Each line is validated independently against the
    canonical schema; only valid lines are returned.
    """
    try:
        parsed = parse_model_json(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        return ValidationOutcome(
            line_items=[], errors=[], parse_error=f"invalid JSON: {exc.__class__.__name__}"
        )

    if isinstance(parsed, dict):
        candidate_lines = parsed.get("line_items", [])
    elif isinstance(parsed, list):
        candidate_lines = parsed
    else:
        return ValidationOutcome(
            line_items=[], errors=[], parse_error="expected object or array at top level"
        )

    if not isinstance(candidate_lines, list):
        return ValidationOutcome(
            line_items=[], errors=[], parse_error="`line_items` must be an array"
        )

    validator = _validator()
    valid: list[LineItem] = []
    errors: list[LineError] = []

    for index, line in enumerate(candidate_lines):
        if not isinstance(line, dict):
            errors.append(LineError(index=index, message="line is not an object"))
            continue
        line_errors = sorted(validator.iter_errors(line), key=lambda e: list(e.path))
        if line_errors:
            # Report the field path and rule only, not the offending value.
            first = line_errors[0]
            where = ".".join(str(p) for p in first.path) or "<root>"
            errors.append(
                LineError(index=index, message=f"schema violation at '{where}': {first.validator}")
            )
            continue
        valid.append(_to_line_item(line))

    return ValidationOutcome(line_items=valid, errors=errors)


__all__ = ["LineError", "ValidationOutcome", "validate_lines"]
