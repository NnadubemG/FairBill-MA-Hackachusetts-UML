"""Load and validate the curated procedure list (/data/procedure_list.csv).

This list is the single source of codes the whole pipeline filters to. Everything
downstream keeps only records whose code appears here.

Columns (header required): code, code_system, plain_label, category, typical_max_units
- code and plain_label are required (non-empty) on every row.
- code_system, category, typical_max_units may be empty -> become None.
- code_system, when present, must be a known CodeSystem value.

Raises ProcedureListError on any structural problem so a bad list fails loudly rather
than silently producing a wrong curated set.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

from contracts.types import CodeSystem, ProcedureInfo

REQUIRED_COLUMNS = ["code", "code_system", "plain_label", "category", "typical_max_units"]
_VALID_CODE_SYSTEMS = {"CPT", "HCPCS", "DRG", "REV", "ICD10", "OTHER"}


class ProcedureListError(ValueError):
    """Raised when the curated procedure list is structurally invalid."""


def _clean(value: Optional[str]) -> Optional[str]:
    """Trim whitespace; treat empty string as None (missing, never a placeholder)."""
    if value is None:
        return None
    value = value.strip()
    return value or None


def _parse_units(raw: Optional[str], code: str) -> Optional[float]:
    raw = _clean(raw)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError as exc:
        raise ProcedureListError(
            f"typical_max_units for code {code!r} is not a number: {raw!r}"
        ) from exc


def _parse_code_system(raw: Optional[str], code: str) -> Optional[CodeSystem]:
    raw = _clean(raw)
    if raw is None:
        return None
    if raw not in _VALID_CODE_SYSTEMS:
        raise ProcedureListError(
            f"code_system for code {code!r} is not recognized: {raw!r}"
        )
    return raw  # type: ignore[return-value]


def load_procedures(path: str | Path) -> list[ProcedureInfo]:
    """Parse the curated CSV into a list of ProcedureInfo.

    Order of the output follows the order of rows in the file.
    """
    path = Path(path)
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames or []
        missing = [c for c in REQUIRED_COLUMNS if c not in header]
        if missing:
            raise ProcedureListError(
                f"procedure list missing required column(s): {', '.join(missing)}"
            )

        procedures: list[ProcedureInfo] = []
        seen: set[str] = set()
        for lineno, row in enumerate(reader, start=2):  # row 1 is the header
            code = _clean(row.get("code"))
            if code is None:
                raise ProcedureListError(f"empty code on line {lineno}")
            if code in seen:
                raise ProcedureListError(f"duplicate code {code!r} on line {lineno}")
            seen.add(code)

            plain_label = _clean(row.get("plain_label"))
            if plain_label is None:
                raise ProcedureListError(
                    f"empty plain_label for code {code!r} on line {lineno}"
                )

            procedures.append(
                ProcedureInfo(
                    code=code,
                    plain_label=plain_label,
                    code_system=_parse_code_system(row.get("code_system"), code),
                    category=_clean(row.get("category")),
                    typical_max_units=_parse_units(row.get("typical_max_units"), code),
                )
            )
        return procedures


def curated_codes(procedures: list[ProcedureInfo]) -> set[str]:
    """The set of codes the rest of the pipeline filters to."""
    return {p.code for p in procedures}
