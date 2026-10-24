"""Load the canonical LineItem JSON Schema and expose the model output shape.

The JSON Schema in ``/contracts/line-item.schema.json`` is the source of truth. We
load it once and reuse it for validation. We also derive the shape the model is asked
to produce: an object with a ``line_items`` array of LineItem objects, plus nullable
bill-level metadata. The metadata shape is extraction-only (not a contract type), so
it is defined here rather than in ``/contracts``.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from ._contracts import LINE_ITEM_SCHEMA_PATH


@lru_cache(maxsize=1)
def line_item_schema() -> dict[str, Any]:
    """Return the canonical LineItem JSON Schema (cached)."""
    with open(LINE_ITEM_SCHEMA_PATH, encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def extraction_output_schema() -> dict[str, Any]:
    """Return the JSON Schema for the model's full structured output.

    Wraps the contract LineItem schema in the envelope the model returns: a list of
    line items plus nullable bill-level metadata. Metadata fields are nullable
    because we never invent a value we did not read from the bill.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["line_items"],
        "properties": {
            "line_items": {
                "type": "array",
                "items": line_item_schema(),
            },
            "metadata": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "hospital_name": {"type": ["string", "null"]},
                    "statement_date": {"type": ["string", "null"]},
                    "total": {"type": ["number", "null"]},
                },
            },
        },
    }


__all__ = ["line_item_schema", "extraction_output_schema"]
