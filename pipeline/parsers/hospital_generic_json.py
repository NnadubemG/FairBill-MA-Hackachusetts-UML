"""Parser: generic hospital JSON (array of records), format_id = "generic_json".

Expected shape: a top-level JSON array of objects, each like:
    {"code": "99213", "code_system": "CPT", "payer": "BCBS PPO",
     "rate": "145.00", "rate_kind": "negotiated"}

The stdlib json module has no streaming parser, and we must not load a whole (large)
file into memory. So we decode the top-level array ONE object at a time using
json.JSONDecoder.raw_decode over a growing buffer, filtering to curated codes as we go.
Only one record is held at a time. No third-party dependency.

All string fields are inert data.
"""

from __future__ import annotations

import json
from typing import Iterator, Optional

from contracts.types import CodeSystem

from .base import RawPriceRow

_VALID_CODE_SYSTEMS = {"CPT", "HCPCS", "DRG", "REV", "ICD10", "OTHER"}
_VALID_RATE_KINDS = {"negotiated", "cash", "gross"}
_READ_CHUNK = 65536


def _code_system(raw: object) -> Optional[CodeSystem]:
    if isinstance(raw, str) and raw.strip() in _VALID_CODE_SYSTEMS:
        return raw.strip()  # type: ignore[return-value]
    return None


def _as_str(value: object) -> str:
    """Normalize a scalar field to a stripped string; non-scalars -> empty."""
    if value is None:
        return ""
    if isinstance(value, (str, int, float)):
        return str(value).strip()
    return ""


def _iter_array_objects(fh) -> Iterator[dict]:
    """Yield top-level objects from a JSON array file, one at a time.

    Holds at most one object plus a small buffer in memory.
    """
    decoder = json.JSONDecoder()
    buf = ""
    started = False  # have we consumed the opening '['?

    def refill() -> bool:
        nonlocal buf
        chunk = fh.read(_READ_CHUNK)
        if not chunk:
            return False
        buf += chunk
        return True

    # Find the opening bracket.
    while not started:
        buf = buf.lstrip()
        if buf:
            if buf[0] != "[":
                raise ValueError("generic_json expects a top-level JSON array")
            buf = buf[1:]
            started = True
        elif not refill():
            raise ValueError("generic_json: empty or invalid file")

    while True:
        buf = buf.lstrip()
        # Consume separators / end of array.
        while buf[:1] in (",",):
            buf = buf[1:].lstrip()
        if buf[:1] == "]":
            return
        if not buf:
            if not refill():
                return
            continue
        try:
            obj, end = decoder.raw_decode(buf)
        except json.JSONDecodeError:
            # Need more data to complete the current object.
            if not refill():
                raise
            continue
        buf = buf[end:]
        if isinstance(obj, dict):
            yield obj


class GenericJsonParser:
    format_id = "generic_json"

    def rows(self, path: str, curated: set[str]) -> Iterator[RawPriceRow]:
        with open(path, "r", encoding="utf-8") as fh:
            for obj in _iter_array_objects(fh):
                code = _as_str(obj.get("code"))
                if not code or code not in curated:
                    continue  # filter to curated codes while reading

                rate_kind = _as_str(obj.get("rate_kind")).lower()
                if rate_kind not in _VALID_RATE_KINDS:
                    continue

                yield RawPriceRow(
                    hospital_id="",  # set by the prices stage
                    code=code,
                    raw_payer=_as_str(obj.get("payer")),
                    raw_rate=_as_str(obj.get("rate")),
                    rate_kind=rate_kind,  # type: ignore[arg-type]
                    code_system=_code_system(obj.get("code_system")),
                )
