"""Stage: curated procedure list -> /data/processed/procedures.json.

Reads /data/procedure_list.csv, validates it, and writes a deterministic
procedures.json (list of ProcedureInfo) sorted by code.
"""

from __future__ import annotations

from pathlib import Path

from .. import config, jsonio
from ..procedure_list import load_procedures


def build_procedures(
    source_csv: str | Path | None = None,
    out_path: str | Path | None = None,
) -> int:
    """Build procedures.json. Returns the number of procedures written."""
    source_csv = Path(source_csv) if source_csv else config.PROCEDURE_LIST_CSV
    out_path = Path(out_path) if out_path else config.PROCEDURES_JSON

    procedures = load_procedures(source_csv)
    # Stable order so output is deterministic and diffs cleanly.
    procedures = sorted(procedures, key=lambda p: p.code)
    jsonio.write_json(out_path, procedures)
    return len(procedures)
