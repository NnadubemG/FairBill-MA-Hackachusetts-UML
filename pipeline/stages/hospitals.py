"""Stage: hospitals input CSV -> /data/processed/hospitals.json + an internal manifest.

hospitals.json is a committed output the app consumes. It carries only public fields:
    id, name, city, type   (type e.g. academic / community / specialty)

The prices stage also needs to know which raw file belongs to each hospital and which
parser format it uses. That binding is pipeline-internal, so it is returned separately
(and written to an internal manifest) rather than polluting the public hospitals.json
with file paths.

Input CSV columns (header required):
    id, name, city, type, format_id, source_file
`source_file` is a path relative to /data/raw. `city`/`type` may be blank -> null.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .. import config, jsonio

_REQUIRED_COLUMNS = ["id", "name", "city", "type", "format_id", "source_file"]


class HospitalsInputError(ValueError):
    """Raised when the hospitals input CSV is structurally invalid."""


@dataclass(frozen=True)
class HospitalBinding:
    """Internal: ties a hospital id to its raw file and parser format."""

    hospital_id: str
    format_id: str
    source_file: str


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value or None


def load_hospitals(
    path: str | Path,
) -> tuple[list[dict], list[HospitalBinding]]:
    """Parse the hospitals input into (public_records, bindings)."""
    path = Path(path)
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames or []
        missing = [c for c in _REQUIRED_COLUMNS if c not in header]
        if missing:
            raise HospitalsInputError(
                f"hospitals input missing column(s): {', '.join(missing)}"
            )

        public: list[dict] = []
        bindings: list[HospitalBinding] = []
        seen: set[str] = set()
        for lineno, row in enumerate(reader, start=2):
            hid = _clean(row.get("id"))
            if hid is None:
                raise HospitalsInputError(f"empty hospital id on line {lineno}")
            if hid in seen:
                raise HospitalsInputError(f"duplicate hospital id {hid!r} on line {lineno}")
            seen.add(hid)

            name = _clean(row.get("name"))
            if name is None:
                raise HospitalsInputError(
                    f"empty name for hospital {hid!r} on line {lineno}"
                )
            fmt = _clean(row.get("format_id"))
            src = _clean(row.get("source_file"))
            if fmt is None or src is None:
                raise HospitalsInputError(
                    f"hospital {hid!r} needs format_id and source_file on line {lineno}"
                )

            public.append(
                {
                    "id": hid,
                    "name": name,
                    "city": _clean(row.get("city")),
                    "type": _clean(row.get("type")),
                }
            )
            bindings.append(HospitalBinding(hospital_id=hid, format_id=fmt, source_file=src))
        return public, bindings


def build_hospitals(
    source_csv: str | Path | None = None,
    out_path: str | Path | None = None,
    manifest_path: str | Path | None = None,
) -> int:
    """Build hospitals.json (public) and the internal bindings manifest.

    Returns the number of hospitals written.
    """
    source_csv = Path(source_csv) if source_csv else config.DATA_DIR / "hospitals_input.csv"
    out_path = Path(out_path) if out_path else config.HOSPITALS_JSON
    manifest_path = (
        Path(manifest_path)
        if manifest_path
        else config.PROCESSED_DIR / "hospital_bindings.json"
    )

    public, bindings = load_hospitals(source_csv)
    public = sorted(public, key=lambda r: r["id"])
    bindings_sorted = sorted(
        (
            {
                "hospital_id": b.hospital_id,
                "format_id": b.format_id,
                "source_file": b.source_file,
            }
            for b in bindings
        ),
        key=lambda r: r["hospital_id"],
    )
    jsonio.write_json(out_path, public)
    jsonio.write_json(manifest_path, bindings_sorted)
    return len(public)
