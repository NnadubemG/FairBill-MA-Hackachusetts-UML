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
QUANTITY_LIMITS_JSON = PROCESSED_DIR / "quantity_limits.json"  # QuantityLimit per code
BUNDLE_PAIRS_JSON = PROCESSED_DIR / "bundle_pairs.json"  # BundlePair per code pair for /core
SKIPPED_LOG = PROCESSED_DIR / "skipped.log"

# Hospitals input (not raw; curated by us) and the internal bindings manifest.
HOSPITALS_INPUT_CSV = DATA_DIR / "hospitals_input.csv"
HOSPITAL_BINDINGS_JSON = PROCESSED_DIR / "hospital_bindings.json"

# Conventional raw source filenames under /data/raw (gitignored). Override via CLI.
PFS_RAW = RAW_DIR / "cms_pfs.csv"          # CMS Physician Fee Schedule
NCCI_RAW = RAW_DIR / "ncci_ptp.csv"        # NCCI procedure-to-procedure edits
CHIA_RAW = RAW_DIR / "chia_relative_price.csv"  # CHIA relative price

# CMS Physician Fee Schedule: Massachusetts locality.
# Verified against the CMS locality key: Massachusetts is MAC 14212 with two localities,
# 01 = Metropolitan Boston (Middlesex, Norfolk, Suffolk) and 99 = rest of state.
# Both loaded hospitals (Lahey Burlington, BIDMC Boston) are in locality 01.
# (The old value "10112" was Alabama's statewide locality.)
MA_PFS_MAC = "14212"
MA_PFS_LOCALITY_CODE = "01"
MA_PFS_LOCALITY = MA_PFS_MAC + MA_PFS_LOCALITY_CODE  # "1421201", as written by adapters/cms_pfs.py

# Raw CMS downloads (gitignored), see data/manifest.json.
# PFS national payment amount files for 2026: A is the full table, B/C/D are updates.
PFS_REVISION_ZIPS = [RAW_DIR / "cms" / f"pfs_pfrev26{rev}.zip" for rev in "abcd"]
MUE_RAW_ZIP = RAW_DIR / "cms" / "mue_practitioner_2026q4.zip"  # NCCI MUE, practitioner services

# Stable JSON formatting so processed outputs diff cleanly and are deterministic.
JSON_DUMP_KWARGS = {
    "sort_keys": True,
    "ensure_ascii": False,
    "indent": 2,
}
