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
REFERENCE_JSON = PROCESSED_DIR / "reference.json"  # one PriceReference per code for /core
SKIPPED_LOG = PROCESSED_DIR / "skipped.log"

# Hospitals input (not raw; curated by us) and the internal bindings manifest.
HOSPITALS_INPUT_CSV = DATA_DIR / "hospitals_input.csv"
HOSPITAL_BINDINGS_JSON = PROCESSED_DIR / "hospital_bindings.json"

# Conventional raw source filenames under /data/raw (gitignored). Override via CLI.
PFS_RAW = RAW_DIR / "cms_pfs.csv"          # CMS Physician Fee Schedule
NCCI_RAW = RAW_DIR / "ncci_ptp.csv"        # NCCI procedure-to-procedure edits
CHIA_RAW = RAW_DIR / "chia_relative_price.csv"  # CHIA relative price

# CMS Physician Fee Schedule: Massachusetts locality.
# CMS MAC locality 10112 (Massachusetts, statewide) under the MAC 14 (NGS) jurisdiction.
MA_PFS_LOCALITY = "10112"

# Stable JSON formatting so processed outputs diff cleanly and are deterministic.
JSON_DUMP_KWARGS = {
    "sort_keys": True,
    "ensure_ascii": False,
    "indent": 2,
}
