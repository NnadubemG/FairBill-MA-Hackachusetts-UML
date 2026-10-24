"""Parser: CMS Hospital Price Transparency machine-readable JSON, format_id = "cms_json".

This is the real format every US hospital must publish under 45 CFR 180.50 (the CMS v2.x
"machine-readable file" schema), confirmed against the live Lahey Burlington file.

Shape (top-level is an OBJECT, not an array):

    {
      "hospital_name": "...",
      "last_updated_on": "2026-04-01",
      "version": "3.0.0",
      "standard_charge_information": [
        {
          "description": "...",
          "code_information": [{"code": "99213", "type": "CPT"}, ...],
          "standard_charges": [
            {
              "gross_charge": 123.0,
              "discounted_cash": 95.0,
              "payers_information": [
                {"payer_name": "BCBS", "plan_name": "...",
                 "methodology": "fee schedule", "standard_charge_dollar": 176218.16},
                {"payer_name": "...", "standard_charge_percentage": 45},    # not a $ -> skip
                {"payer_name": "...", "standard_charge_algorithm": "..."}   # not a $ -> skip
              ]
            }
          ]
        }
      ]
    }

The ``standard_charge_information`` array is large (tens of thousands to millions of
items), so we stream it object-by-object using json.JSONDecoder.raw_decode over a
growing buffer -- never loading the whole file. We filter to curated codes while reading.

Normalization into RawPriceRow (the prices stage does payer classification + $ parsing):
- A code_information entry contributes rows only when its ``type`` is CPT or HCPCS and
  its ``code`` is in the curated set.
- gross_charge  -> one row, rate_kind="gross".
- discounted_cash -> one row, rate_kind="cash".
- each payers_information entry with a numeric ``standard_charge_dollar`` -> one
  rate_kind="negotiated" row carrying the payer name. Percentage/algorithm-only entries
  are left for the prices stage to skip (we pass their raw value through verbatim, and
  rates.parse_rate refuses to turn a %/formula into a number).

No value is ever invented. All string fields are inert data.
"""

from __future__ import annotations

import json
from typing import Iterator, Optional

from contracts.types import CodeSystem

from .base import RawPriceRow

_READ_CHUNK = 65536
_CURATED_CODE_TYPES = {"CPT", "HCPCS"}  # the systems our curated list uses
_KEY = "standard_charge_information"


def _code_system(raw: object) -> Optional[CodeSystem]:
    if isinstance(raw, str) and raw.strip().upper() in {"CPT", "HCPCS", "DRG", "REV", "ICD10", "OTHER"}:
        return raw.strip().upper()  # type: ignore[return-value]
    return None


def _num_to_str(value: object) -> str:
    """Render a numeric charge as a plain string for rates.parse_rate; else ""."""
    if isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return value.strip()
    return ""


def _stream_array_at_key(fh, key: str) -> Iterator[dict]:
    """Yield objects from the array found at top-level ``key``, one at a time.

    Scans the raw text for the key, then streams the following JSON array without ever
    holding more than one element (plus a small buffer) in memory. This avoids decoding
    the entire multi-hundred-MB object.
    """
    decoder = json.JSONDecoder()
    buf = ""
    target = f'"{key}"'

    def refill() -> bool:
        nonlocal buf
        chunk = fh.read(_READ_CHUNK)
        if not chunk:
            return False
        buf += chunk
        return True

    # 1) Find the key.
    while target not in buf:
        if not refill():
            return  # key never appears -> no rows
    buf = buf.split(target, 1)[1]

    # 2) Advance to the opening '[' of its array value.
    while True:
        stripped = buf.lstrip()
        if stripped[:1] == ":":
            buf = stripped[1:]
            continue
        if stripped[:1] == "[":
            buf = stripped[1:]
            break
        if stripped and stripped[0] not in " \t\r\n":
            # Value is not an array (unexpected) -> nothing to stream.
            return
        buf = stripped
        if not buf and not refill():
            return

    # 3) Stream elements until the matching ']'.
    while True:
        buf = buf.lstrip()
        while buf[:1] == ",":
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
            if not refill():
                return
            continue
        buf = buf[end:]
        if isinstance(obj, dict):
            yield obj


def _curated_codes_in_item(item: dict, curated: set[str]) -> list[tuple[str, Optional[CodeSystem]]]:
    """Return [(code, code_system)] for this item's CPT/HCPCS codes that are curated."""
    out: list[tuple[str, Optional[CodeSystem]]] = []
    for ci in item.get("code_information") or []:
        if not isinstance(ci, dict):
            continue
        ctype = str(ci.get("type", "")).strip().upper()
        if ctype not in _CURATED_CODE_TYPES:
            continue
        code = str(ci.get("code", "")).strip()
        if code and code in curated:
            out.append((code, _code_system(ctype)))
    return out


class CmsHospitalJsonParser:
    format_id = "cms_json"

    def rows(self, path: str, curated: set[str]) -> Iterator[RawPriceRow]:
        with open(path, "r", encoding="utf-8") as fh:
            for item in _stream_array_at_key(fh, _KEY):
                codes = _curated_codes_in_item(item, curated)
                if not codes:
                    continue  # nothing curated in this item; skip cheaply

                charges = item.get("standard_charges") or []
                for code, csys in codes:
                    for sc in charges:
                        if not isinstance(sc, dict):
                            continue
                        yield from self._rows_for_charge(code, csys, sc)

    @staticmethod
    def _rows_for_charge(
        code: str, csys: Optional[CodeSystem], sc: dict
    ) -> Iterator[RawPriceRow]:
        gross = _num_to_str(sc.get("gross_charge"))
        if gross:
            yield RawPriceRow(
                hospital_id="", code=code, raw_payer="",
                raw_rate=gross, rate_kind="gross", code_system=csys,
            )
        cash = _num_to_str(sc.get("discounted_cash"))
        if cash:
            yield RawPriceRow(
                hospital_id="", code=code, raw_payer="",
                raw_rate=cash, rate_kind="cash", code_system=csys,
            )
        for pi in sc.get("payers_information") or []:
            if not isinstance(pi, dict):
                continue
            # Prefer a concrete dollar; fall back to the raw %/algorithm value so the
            # prices stage logs a real skip rather than us dropping it silently.
            dollar = pi.get("standard_charge_dollar")
            if dollar is not None:
                raw_rate = _num_to_str(dollar)
            elif pi.get("standard_charge_percentage") is not None:
                raw_rate = f"{_num_to_str(pi.get('standard_charge_percentage'))}%"
            elif pi.get("standard_charge_algorithm") is not None:
                raw_rate = "algorithm"
            else:
                raw_rate = ""
            if not raw_rate:
                continue
            payer = str(pi.get("payer_name") or "").strip()
            plan = str(pi.get("plan_name") or "").strip()
            raw_payer = f"{payer} {plan}".strip()
            yield RawPriceRow(
                hospital_id="", code=code, raw_payer=raw_payer,
                raw_rate=raw_rate, rate_kind="negotiated", code_system=csys,
            )
