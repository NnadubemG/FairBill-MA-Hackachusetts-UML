"""Pipeline paths and constants. No I/O at import time."""

from __future__ import annotations

from pathlib import Path

# Repo root = parent of the /pipeline package directory.
REPO_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"              # gitignored, large. Never load whole files.
PROCESSED_DIR = DATA_DIR / "processed"  # committed, small.

PROCEDURE_LIST_CSV = DATA_DIR / "procedure_list.csv"

# Processed output files.
HOSPITALS_JSON = PROCESSED_DIR / "hospitals.json"
PROCEDURES_JSON = PROCESSED_DIR / "procedures.json"
PRICES_JSON = PROCESSED_DIR / "prices.json"
MEDICARE_JSON = PROCESSED_DIR / "medicare.json"
NCCI_PAIRS_JSON = PROCESSED_DIR / "ncci_pairs.json"
CHIA_TIERS_JSON = PROCESSED_DIR / "chia_tiers.json"
SKIPPED_LOG = PROCESSED_DIR / "skipped.log"

# CMS Physician Fee Schedule: Massachusetts locality.
# CMS MAC locality 10112 (Massachusetts, statewide) under the MAC 14 (NGS) jurisdiction.
MA_PFS_LOCALITY = "10112"

# Stable JSON formatting so processed outputs diff cleanly and are deterministic.
JSON_DUMP_KWARGS = {
    "sort_keys": True,
    "ensure_ascii": False,
    "indent": 2,
}
