"""Tests for the extraction handler orchestration (spec task 7).

Covers T1 (clean bill), T5 (validation fail then repair on retry), T6 (fails twice
-> keep valid, warn), T8 (blank page -> empty + warn). Uses FakeBedrockClient, fully
offline. procedures_path points at a tmp file (or absent) so the known-code check is
controlled.
"""

from __future__ import annotations

import json

from backend.extract.bedrock_client import FakeBedrockClient
from backend.extract.handler import (
    WARN_NO_LINES,
    WARN_SOME_LINES_DROPPED,
    extract,
)

PNG = ("image/png", b"\x89PNG fake")


def _env(lines, metadata=None, confidence_hints=None):
    obj = {"line_items": lines}
    if metadata is not None:
        obj["metadata"] = metadata
    if confidence_hints is not None:
        obj["confidence_hints"] = confidence_hints
    return json.dumps(obj)


def _procs(tmp_path, codes):
    p = tmp_path / "procedures.json"
    p.write_text(json.dumps([{"code": c, "plain_label": "x"} for c in codes]))
    return p


# --- T1: clean bill --------------------------------------------------------

def test_t1_clean_bill(tmp_path):
    lines = [
        {"id": "1", "description": "Office visit", "billed_amount": 150, "code": "99213",
         "code_system": "CPT"},
        {"id": "2", "description": "Blood count", "billed_amount": 42, "code": "85025",
         "code_system": "CPT"},
    ]
    raw = _env(
        lines,
        metadata={"hospital_name": "Example Hospital", "statement_date": "03/04/2026",
                  "total": "$192.00"},
        confidence_hints={"1": "high", "2": "high"},
    )
    client = FakeBedrockClient(default=raw)
    result = extract(*reversed(PNG), client=client,  # content_type, bytes
                     procedures_path=_procs(tmp_path, ["99213", "85025"]))

    assert len(result.line_items) == 2
    assert result.metadata.hospital_name == "Example Hospital"
    assert result.metadata.statement_date == "2026-03-04"
    assert result.metadata.total == 192.0
    assert all(not c.needs_confirmation for c in result.line_confidence)
    assert result.warnings == []
    assert client.calls == 1  # no retry needed


# --- T5: invalid first, valid on retry -------------------------------------

def test_t5_validation_failure_then_repair(tmp_path):
    bad = '{"line_items": [{"id": "1", "description": "x"}]}'  # missing billed_amount
    good = _env(
        [{"id": "1", "description": "Office visit", "billed_amount": 150, "code": "99213",
          "code_system": "CPT"}],
        confidence_hints={"1": "high"},
    )
    client = FakeBedrockClient(responses=[bad, good])
    result = extract(*reversed(PNG), client=client,
                     procedures_path=_procs(tmp_path, ["99213"]))

    assert client.calls == 2            # retried exactly once
    assert len(result.line_items) == 1  # used the repaired output
    assert result.line_items[0].code == "99213"


# --- T6: fails twice -> keep valid, warn -----------------------------------

def test_t6_fails_twice_keeps_valid_and_warns(tmp_path):
    # Both responses: one valid line + one invalid line.
    valid_line = {"id": "1", "description": "Visit", "billed_amount": 100, "code": "99213",
                  "code_system": "CPT"}
    invalid_line = {"id": "2", "description": "missing amount"}
    raw = _env([valid_line, invalid_line], confidence_hints={"1": "high"})
    client = FakeBedrockClient(responses=[raw, raw])
    result = extract(*reversed(PNG), client=client,
                     procedures_path=_procs(tmp_path, ["99213"]))

    assert client.calls == 2
    assert len(result.line_items) == 1          # only the valid line
    assert result.line_items[0].id == "1"
    assert WARN_SOME_LINES_DROPPED in result.warnings


def test_t6_no_invalid_line_ever_returned(tmp_path):
    raw = _env([{"id": "2", "description": "no amount"}])  # only invalid
    client = FakeBedrockClient(responses=[raw, raw])
    result = extract(*reversed(PNG), client=client, procedures_path=_procs(tmp_path, []))
    assert result.line_items == []
    assert WARN_NO_LINES in result.warnings or WARN_SOME_LINES_DROPPED in result.warnings


# --- T8: blank page --------------------------------------------------------

def test_t8_blank_page_empty_with_warning(tmp_path):
    raw = _env([], metadata={"hospital_name": None, "statement_date": None, "total": None})
    client = FakeBedrockClient(default=raw)
    result = extract(*reversed(PNG), client=client, procedures_path=_procs(tmp_path, []))
    assert result.line_items == []
    assert WARN_NO_LINES in result.warnings


# --- procedures.json absent flows through ----------------------------------

def test_missing_procedures_file_warns(tmp_path):
    raw = _env(
        [{"id": "1", "description": "Visit", "billed_amount": 100, "code": "99213",
          "code_system": "CPT"}],
        confidence_hints={"1": "high"},
    )
    client = FakeBedrockClient(default=raw)
    missing = tmp_path / "does_not_exist.json"
    result = extract(*reversed(PNG), client=client, procedures_path=missing)
    assert len(result.line_items) == 1
    assert any("Code validation was unavailable" in w for w in result.warnings)


# --- date_of_service flows through -----------------------------------------

def test_date_of_service_normalized_in_handler(tmp_path):
    raw = _env(
        [{"id": "1", "description": "Visit", "billed_amount": 100, "code": "99213",
          "code_system": "CPT", "date_of_service": "03/04/2026"}],
        confidence_hints={"1": "high"},
    )
    client = FakeBedrockClient(default=raw)
    result = extract(*reversed(PNG), client=client, procedures_path=_procs(tmp_path, ["99213"]))
    assert result.line_items[0].date_of_service == "2026-03-04"
