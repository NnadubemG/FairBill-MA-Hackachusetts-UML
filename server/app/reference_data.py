"""Reference pricing lookup for procedures/compare.

The design assumes reference data (Medicare reference prices, Massachusetts price
ranges) comes from `/data/processed`, owned by a separate data task. That data is
not present yet, so this module loads from an optional JSON file if it exists and
otherwise serves a small built-in sample, degrading gracefully to `null`
references when a code is unknown.

Expected JSON shape (when `/data/processed/procedures.json` exists):
  {
    "<code>": {
      "plain_language_label": "...",
      "description": "...",
      "medicare_reference": <cents|null>,
      "ma_price_range": {"low": <cents|null>, "high": <cents|null>, "source": "..."}
    },
    ...
  }

All money is in whole US cents, matching the contracts.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

from contracts import PriceRange, ProcedureInfo

# <repo>/server/app/reference_data.py -> repo root is parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA_FILE = _REPO_ROOT / "data" / "processed" / "procedures.json"

# Minimal built-in sample so procedures/compare return useful data before the
# real dataset lands. These are illustrative reference points, not authoritative.
_SAMPLE: Dict[str, dict] = {
    "99213": {
        "plain_language_label": "Office visit, established patient (low complexity)",
        "description": "Outpatient office or other visit, established patient, ~15 min.",
        "medicare_reference": 9200,
        "ma_price_range": {"low": 11000, "high": 24000, "source": "sample"},
    },
    "99214": {
        "plain_language_label": "Office visit, established patient (moderate complexity)",
        "description": "Outpatient office or other visit, established patient, ~25 min.",
        "medicare_reference": 13100,
        "ma_price_range": {"low": 16000, "high": 32000, "source": "sample"},
    },
    "80053": {
        "plain_language_label": "Comprehensive metabolic blood panel",
        "description": "A group of blood tests measuring chemistry/organ function.",
        "medicare_reference": 1400,
        "ma_price_range": {"low": 2500, "high": 9000, "source": "sample"},
    },
    "71046": {
        "plain_language_label": "Chest X-ray (two views)",
        "description": "Radiologic exam of the chest, two views.",
        "medicare_reference": 2800,
        "ma_price_range": {"low": 4000, "high": 18000, "source": "sample"},
    },
}


@lru_cache(maxsize=1)
def _load() -> Dict[str, dict]:
    if _DATA_FILE.is_file():
        try:
            return json.loads(_DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            # Fall back to the sample rather than failing the endpoint.
            return dict(_SAMPLE)
    return dict(_SAMPLE)


def _to_price_range(raw: Optional[dict]) -> Optional[PriceRange]:
    if not raw:
        return None
    return PriceRange(
        low=raw.get("low"),
        high=raw.get("high"),
        source=raw.get("source"),
    )


def get_procedure(code: str) -> Optional[ProcedureInfo]:
    rec = _load().get(code)
    if rec is None:
        return None
    return ProcedureInfo(
        code=code,
        plain_language_label=rec.get("plain_language_label", code),
        description=rec.get("description", ""),
        medicare_reference=rec.get("medicare_reference"),
        ma_price_range=_to_price_range(rec.get("ma_price_range")),
    )


def all_procedures() -> list[ProcedureInfo]:
    out: list[ProcedureInfo] = []
    for code in _load():
        info = get_procedure(code)
        if info is not None:
            out.append(info)
    return out


def medicare_reference(code: str) -> Optional[int]:
    info = get_procedure(code)
    return info.medicare_reference if info else None


def ma_price_range(code: str) -> Optional[PriceRange]:
    info = get_procedure(code)
    return info.ma_price_range if info else None
