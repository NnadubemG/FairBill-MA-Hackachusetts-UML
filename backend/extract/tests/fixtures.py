"""Scripted model-output fixtures for extraction tests.

These are fake, synthetic model responses (JSON strings) — no real bill data. They
feed FakeBedrockClient so the whole suite runs offline with no network and no real
model id. Codes are drawn from the starter procedure list in the team build guide.
"""

from __future__ import annotations

import json


def envelope(lines, *, metadata=None, confidence_hints=None) -> str:
    """Build a model-output envelope JSON string."""
    obj: dict = {"line_items": list(lines)}
    if metadata is not None:
        obj["metadata"] = metadata
    if confidence_hints is not None:
        obj["confidence_hints"] = confidence_hints
    return json.dumps(obj)


# A clean two-line bill, all codes known, high confidence.
CLEAN_BILL = envelope(
    [
        {"id": "1", "description": "Office visit, established patient",
         "billed_amount": 150, "code": "99213", "code_system": "CPT",
         "date_of_service": "2026-03-04"},
        {"id": "2", "description": "Complete blood count", "billed_amount": 42,
         "code": "85025", "code_system": "CPT", "date_of_service": "2026-03-04"},
    ],
    metadata={"hospital_name": "Riverside General", "statement_date": "2026-03-10",
              "total": 192.0},
    confidence_hints={"1": "high", "2": "high"},
)

# A summary-style bill with no codes.
NO_CODES_BILL = envelope(
    [
        {"id": "1", "description": "Emergency room services", "billed_amount": 1800},
        {"id": "2", "description": "Pharmacy", "billed_amount": 240},
    ],
    metadata={"hospital_name": "Lakeshore Medical", "statement_date": None, "total": 2040.0},
)

# A blank page: no lines.
BLANK_BILL = envelope([], metadata={"hospital_name": None, "statement_date": None,
                                    "total": None})

# Invalid first attempt (missing billed_amount), used with a valid retry.
INVALID_FIRST = '{"line_items": [{"id": "1", "description": "needs amount"}]}'

__all__ = [
    "envelope",
    "CLEAN_BILL",
    "NO_CODES_BILL",
    "BLANK_BILL",
    "INVALID_FIRST",
]
