"""Tests for schema loading and contract validation (spec task 3).

Covers the validator's handling of valid/invalid/malformed model output and property
test P1: every returned line validates against the contract; invalid lines are
dropped, never returned.
"""

from __future__ import annotations

import json

from hypothesis import given
from hypothesis import strategies as st
from jsonschema import Draft7Validator

from backend.extract import schema
from backend.extract._contracts import LineItem
from backend.extract.validate import validate_lines

VALID_LINE = {
    "id": "1",
    "description": "Complete blood count",
    "billed_amount": 42.0,
    "code": "85025",
    "code_system": "CPT",
}


def _envelope(*lines: dict) -> str:
    return json.dumps({"line_items": list(lines)})


def test_valid_envelope_round_trips():
    out = validate_lines(_envelope(VALID_LINE))
    assert out.parse_error is None
    assert out.errors == []
    assert len(out.line_items) == 1
    assert isinstance(out.line_items[0], LineItem)
    assert out.line_items[0].code == "85025"


def test_bare_array_accepted():
    out = validate_lines(json.dumps([VALID_LINE]))
    assert len(out.line_items) == 1
    assert out.errors == []


def test_minimal_line_only_required_fields():
    minimal = {"id": "x", "description": "Something", "billed_amount": 10}
    out = validate_lines(_envelope(minimal))
    assert len(out.line_items) == 1
    assert out.line_items[0].code is None


def test_invalid_line_is_dropped_not_returned():
    bad = {"id": "2", "description": "missing amount"}  # no billed_amount
    out = validate_lines(_envelope(VALID_LINE, bad))
    assert len(out.line_items) == 1  # only the valid one
    assert len(out.errors) == 1
    assert out.errors[0].index == 1


def test_extra_property_rejected():
    # additionalProperties: false -> an unknown field invalidates the line.
    extra = {**VALID_LINE, "confidence": "high"}
    out = validate_lines(_envelope(extra))
    assert out.line_items == []
    assert len(out.errors) == 1


def test_bad_code_system_rejected():
    bad = {**VALID_LINE, "code_system": "NOT_A_SYSTEM"}
    out = validate_lines(_envelope(bad))
    assert out.line_items == []


def test_malformed_json_reports_parse_error():
    out = validate_lines("{not json")
    assert out.parse_error is not None
    assert out.line_items == []


def test_non_object_line_reported():
    out = validate_lines(json.dumps(["just a string"]))
    assert out.line_items == []
    assert len(out.errors) == 1


def test_error_message_excludes_offending_value():
    # Privacy: the error should name the field/rule, not echo the bad value.
    secret = "PATIENT NAME 123 Main St"
    bad = {"id": "3", "description": secret}  # missing billed_amount
    out = validate_lines(_envelope(bad))
    assert out.line_items == []
    assert secret not in out.errors[0].message


# --- Property test P1 -------------------------------------------------------

# A strategy that produces a mix of valid and arbitrary (often invalid) line dicts.
_code_systems = st.sampled_from(["CPT", "HCPCS", "DRG", "REV", "ICD10", "OTHER", None])

_valid_lines = st.fixed_dictionaries(
    {
        "id": st.text(min_size=1, max_size=8),
        "description": st.text(min_size=1, max_size=20),
        "billed_amount": st.floats(allow_nan=False, allow_infinity=False,
                                   min_value=-1e6, max_value=1e6),
    },
    optional={
        "code": st.one_of(st.none(), st.text(min_size=1, max_size=6)),
        "code_system": _code_systems,
        "quantity": st.one_of(st.none(), st.integers(min_value=0, max_value=1000)),
    },
)

_junk_lines = st.dictionaries(
    keys=st.text(max_size=5),
    values=st.one_of(st.none(), st.integers(), st.text(max_size=5), st.booleans()),
    max_size=4,
)

_any_lines = st.lists(st.one_of(_valid_lines, _junk_lines), max_size=6)


@given(_any_lines)
def test_p1_only_valid_lines_are_returned(lines):
    raw = json.dumps({"line_items": lines})
    out = validate_lines(raw)
    validator = Draft7Validator(schema.line_item_schema())
    # Every returned LineItem, re-serialized, must satisfy the contract schema.
    for item in out.line_items:
        as_dict = {
            "id": item.id,
            "description": item.description,
            "billed_amount": item.billed_amount,
            "code": item.code,
            "code_system": item.code_system,
            "raw_description": item.raw_description,
            "quantity": item.quantity,
            "unit": item.unit,
        }
        # Drop keys that are None and absent from the original to mirror the schema's
        # optional handling; nullable fields are allowed to be null anyway.
        assert validator.is_valid(as_dict), f"returned line not schema-valid: {as_dict}"
    # Count of valid lines never exceeds the input count.
    assert len(out.line_items) <= len(lines)
