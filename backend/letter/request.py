"""Clean patient fields and build a ``LetterRequest`` from the frontend JSON.

Patient fields are the patient's own words. They are inserted into the letter by the
template, as typed, after cleaning. Cleaning removes control and invisible characters,
so a field cannot hide text or break the layout. It does not filter words.

Error messages name the field only. They never contain a value (privacy).
"""

from __future__ import annotations

import unicodedata
from typing import Any

from . import config
from ._contracts import Flag, LineItem
from .models import LetterRequest, PatientFields

# Sanity limits on the size of one request (abuse guard).
MAX_FLAGS_IN = 200
MAX_LINES_IN = 500

# Characters in these Unicode categories are dropped (control, invisible format such as
# zero-width and right-to-left override, surrogates, private use, unassigned).
_DROP_CATEGORIES = {"Cc", "Cf", "Cs", "Co", "Cn"}


def _drop_invisible(text: str, *, keep: str = "") -> str:
    """Remove control/invisible characters. Whitespace is kept for the caller to handle."""
    out = []
    for ch in text:
        if ch in keep or ch.isspace():
            out.append(ch)
        elif unicodedata.category(ch) in _DROP_CATEGORIES:
            continue
        else:
            out.append(ch)
    return "".join(out)


def clean_field(text: object, max_len: int) -> str:
    """Return a one-line, safe version of ``text`` of at most ``max_len`` characters."""
    if not isinstance(text, str):
        return ""
    one_line = " ".join(_drop_invisible(text).split())
    return one_line[: max(max_len, 0)].rstrip()


def clean_notes(text: object, max_len: int) -> str:
    """Like ``clean_field`` but keeps line breaks (at most one blank line in a row)."""
    if not isinstance(text, str):
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u2028", "\n").replace("\u2029", "\n")
    text = _drop_invisible(text, keep="\n")
    lines = [" ".join(line.split()) for line in text.split("\n")]
    cleaned: list[str] = []
    blank_run = 0
    for line in lines:
        if line:
            blank_run = 0
            cleaned.append(line)
        else:
            blank_run += 1
            if blank_run == 1:
                cleaned.append("")
    result = "\n".join(cleaned).strip("\n")
    return result[: max(max_len, 0)].rstrip()


def clean_patient(patient: PatientFields) -> PatientFields:
    """Return the patient fields cleaned and cut to their limits. Idempotent."""
    return PatientFields(
        name=clean_field(patient.name, config.MAX_NAME),
        account_number=clean_field(patient.account_number, config.MAX_ACCOUNT),
        hospital=clean_field(patient.hospital, config.MAX_HOSPITAL),
        date=clean_field(patient.date, config.MAX_DATE),
        notes=clean_notes(patient.notes, config.MAX_NOTES),
    )


# --- parse_request ---------------------------------------------------------


def _text_or_none(value: Any, label: str) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise ValueError(f"{label} must be text")


def _required_text(obj: dict, key: str, label: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} is required and must be text")
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    return float(value)


def _patient_field(obj: dict, key: str) -> str:
    value = obj.get(key)
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)  # e.g. an account number sent as a number
    raise ValueError(f"patient.{key} must be text")


def _parse_patient(raw: Any) -> PatientFields:
    if raw is None:
        return PatientFields()
    if not isinstance(raw, dict):
        raise ValueError("patient must be an object")
    return clean_patient(
        PatientFields(
            name=_patient_field(raw, "name"),
            account_number=_patient_field(raw, "account_number"),
            hospital=_patient_field(raw, "hospital"),
            date=_patient_field(raw, "date"),
            notes=_patient_field(raw, "notes"),
        )
    )


def _parse_flag(raw: Any, index: int) -> Flag:
    label = f"flags[{index}]"
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be an object")
    year = raw.get("data_year")
    if year is not None and (isinstance(year, bool) or not isinstance(year, int)):
        raise ValueError(f"{label}.data_year must be a whole number")
    return Flag(
        line_item_id=_required_text(raw, "line_item_id", f"{label}.line_item_id"),
        flag_type=_required_text(raw, "flag_type", f"{label}.flag_type"),  # type: ignore[arg-type]
        severity=raw.get("severity") if isinstance(raw.get("severity"), str) else "info",  # type: ignore[arg-type]
        reason=_required_text(raw, "reason", f"{label}.reason"),
        basis=_required_text(raw, "basis", f"{label}.basis"),
        data_source=_text_or_none(raw.get("data_source"), f"{label}.data_source"),
        data_year=year,
        explanation=_text_or_none(raw.get("explanation"), f"{label}.explanation"),
    )


def _parse_line(raw: Any, index: int) -> LineItem:
    label = f"line_items[{index}]"
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be an object")
    description = raw.get("description")
    quantity = raw.get("quantity")
    return LineItem(
        id=_required_text(raw, "id", f"{label}.id"),
        description=description if isinstance(description, str) else "",
        billed_amount=_number(raw.get("billed_amount"), f"{label}.billed_amount"),
        code=_text_or_none(raw.get("code"), f"{label}.code"),
        code_system=raw.get("code_system") if isinstance(raw.get("code_system"), str) else None,  # type: ignore[arg-type]
        raw_description=_text_or_none(raw.get("raw_description"), f"{label}.raw_description"),
        quantity=None if quantity is None else _number(quantity, f"{label}.quantity"),
        unit=_text_or_none(raw.get("unit"), f"{label}.unit"),
        date_of_service=_text_or_none(raw.get("date_of_service"), f"{label}.date_of_service"),
    )


def parse_request(payload: Any) -> LetterRequest:
    """Build a ``LetterRequest`` from the JSON the frontend sends.

    Raises ``ValueError`` (with the field name, never a value) for a missing or wrongly
    typed ``letter_type``, ``flags`` or ``line_items``. Unknown extra keys are ignored.
    Whether the letter type is one we support is checked later, by the handler.
    """
    if not isinstance(payload, dict):
        raise ValueError("request must be an object")

    letter_type = payload.get("letter_type")
    if not isinstance(letter_type, str) or not letter_type:
        raise ValueError("letter_type is required and must be text")

    raw_flags = payload.get("flags", [])
    raw_lines = payload.get("line_items", [])
    if not isinstance(raw_flags, list):
        raise ValueError("flags must be a list")
    if not isinstance(raw_lines, list):
        raise ValueError("line_items must be a list")
    if len(raw_flags) > MAX_FLAGS_IN:
        raise ValueError("flags has too many entries")
    if len(raw_lines) > MAX_LINES_IN:
        raise ValueError("line_items has too many entries")

    return LetterRequest(
        letter_type=letter_type,
        patient=_parse_patient(payload.get("patient")),
        flags=[_parse_flag(f, i) for i, f in enumerate(raw_flags)],
        line_items=[_parse_line(li, i) for i, li in enumerate(raw_lines)],
    )


__all__ = [
    "MAX_FLAGS_IN",
    "MAX_LINES_IN",
    "clean_field",
    "clean_notes",
    "clean_patient",
    "parse_request",
]
