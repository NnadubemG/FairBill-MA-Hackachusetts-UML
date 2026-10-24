"""Download raw public source files into /data/raw (gitignored).

Usage:
    python -m pipeline.download <source_key> [<source_key> ...]
    python -m pipeline.download all
    python -m pipeline.download --list

Design rules (product.md / tech.md):
- Never touch /data/processed here; this only fetches raw inputs.
- Big files download with HTTP range-resume support so an interrupted run can continue.
- Nothing from a bill/patient is involved; these are public institutional files.
- The manifest (/data/manifest.json) is updated after every attempt so Thomas has an
  audit trail. A failed or license-gated source is recorded as failed/manual, never
  silently skipped.

Stdlib only (urllib). No new dependency. Large files are streamed to disk in chunks and
never loaded into memory or printed to the console.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from . import config

MANIFEST_PATH = config.DATA_DIR / "manifest.json"
RAW_DIR = config.RAW_DIR

_CHUNK = 1 << 20  # 1 MiB
_USER_AGENT = "FairBill-MA-pipeline/1.0 (public price transparency fetch)"


@dataclass(frozen=True)
class Source:
    """One downloadable (or manual) raw source."""

    key: str
    name: str
    url: str | None          # None => inherently manual (form / license gate)
    local_path: str          # relative to /data/raw
    fmt: str                 # cms_json / cms_csv / pfs_csv / ncci_txt / xlsx / manual_csv
    notes: str = ""
    manual: bool = False     # True => do not attempt an automated download


# The curated source catalog. One entry per file we want in /data/raw.
SOURCES: list[Source] = [
    Source(
        key="lahey",
        name="Lahey Hospital & Medical Center (Burlington) standard charges",
        url="https://www.lahey.org/042704686_lahey-hospital-medical-center-burlington_standardcharges.json",
        local_path="hospitals/lahey_burlington.json",
        fmt="cms_json",
        notes="CMS hospital price transparency v2.0 JSON. ~25 MB. Format test case.",
    ),
    Source(
        key="massgeneral",
        name="Massachusetts General Hospital standard charges",
        url=None,
        local_path="hospitals/mass_general.csv",
        fmt="cms_csv",
        notes=(
            "~1.8 GB CSV delivered as a ZIP from Mass General Brigham. Direct link is "
            "not script-discoverable; open "
            "https://www.massgeneral.org/notices/billing/cms-required-hospital-charge-data "
            "and download the standard charges file manually into data/raw/hospitals/."
        ),
        manual=True,
    ),
    Source(
        key="bidmc",
        name="Beth Israel Deaconess Medical Center standard charges",
        url=None,
        local_path="hospitals/bidmc.csv",
        fmt="cms_csv",
        notes=(
            "Linked from https://bilh.org/billing-financial-services/price-transparency . "
            "Download BIDMC's standard charges file (CSV or JSON) into "
            "data/raw/hospitals/ and set its format in hospitals_input.csv."
        ),
        manual=True,
    ),
    Source(
        key="umass",
        name="UMass Memorial Medical Center standard charges",
        url=None,
        local_path="hospitals/umass_memorial.csv",
        fmt="cms_csv",
        notes=(
            "From https://ummhealth.org/.../price-transparency . Download the standard "
            "charges file into data/raw/hospitals/."
        ),
        manual=True,
    ),
    Source(
        key="pfs",
        name="CMS Physician Fee Schedule national payment amount (Oct 2026, non-QP)",
        url=None,
        local_path="cms_pfs.csv",
        fmt="pfs_csv",
        notes=(
            "From https://www.cms.gov/medicare/payment/fee-schedules/physician/"
            "national-payment-amount-file/pfrev26d . Use the NON-QP file (2026 has two "
            "conversion factors). Export the payment-amount member to CSV as "
            "data/raw/cms_pfs.csv. data_source label: 'Medicare national, non-QP'."
        ),
        manual=True,
    ),
    Source(
        key="ncci",
        name="CMS NCCI procedure-to-procedure (PTP) edits, practitioner + hospital",
        url=None,
        local_path="ncci_ptp_raw.csv",
        fmt="ncci_txt",
        notes=(
            "From the CMS NCCI edits page. Usually behind a license click-through, so "
            "download the Column One/Column Two edit file(s) manually and export to CSV "
            "as data/raw/ncci_ptp_raw.csv."
        ),
        manual=True,
    ),
    Source(
        key="chia_prices",
        name="CHIA CompareCare procedure price data (Excel)",
        url=None,
        local_path="chia/chia_procedure_prices.xlsx",
        fmt="xlsx",
        notes=(
            "From https://www.chiamass.gov/procedure-price-data (form-gated). Download "
            "the Excel into data/raw/chia/ and record the data year from the file. "
            "Treat as older data."
        ),
        manual=True,
    ),
    Source(
        key="chia_relative",
        name="CHIA relative price tiers",
        url=None,
        local_path="chia_relative_price_manual.csv",
        fmt="manual_csv",
        notes=(
            "From https://www.chiamass.gov/relative-price-and-provider-price-variation/ . "
            "If no downloadable table, hand-enter into "
            "data/raw/chia_relative_price_manual.csv with columns "
            "hospital,tier_or_value,year,source_url."
        ),
        manual=True,
    ),
]

SOURCES_BY_KEY = {s.key: s for s in SOURCES}


def _load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"sources": {}}


def _save_manifest(manifest: dict) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _record(
    manifest: dict,
    src: Source,
    status: str,
    size: int | None = None,
    extra_notes: str | None = None,
) -> None:
    manifest.setdefault("sources", {})[src.key] = {
        "name": src.name,
        "url": src.url,
        "local_path": str((RAW_DIR / src.local_path)),
        "format": src.fmt,
        "date_downloaded": date.today().isoformat() if status == "ok" else None,
        "status": status,  # ok | failed | manual
        "size_bytes": size,
        "notes": extra_notes or src.notes,
    }


def _human_size(n: int | None) -> str:
    if n is None:
        return "unknown"
    units = ["B", "KB", "MB", "GB"]
    size = float(n)
    for u in units:
        if size < 1024 or u == units[-1]:
            return f"{size:.1f} {u}"
        size /= 1024
    return f"{n} B"


def _download(src: Source) -> tuple[str, int | None, str | None]:
    """Attempt a resumable download. Returns (status, size_bytes, note)."""
    assert src.url is not None
    dest = RAW_DIR / src.local_path
    dest.parent.mkdir(parents=True, exist_ok=True)

    existing = dest.stat().st_size if dest.exists() else 0
    headers = {"User-Agent": _USER_AGENT}
    if existing:
        headers["Range"] = f"bytes={existing}-"

    req = urllib.request.Request(src.url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            # 206 => server honored our range (resume); 200 => full body.
            mode = "ab" if (existing and resp.status == 206) else "wb"
            if mode == "wb":
                existing = 0
            with open(dest, mode) as fh:
                while True:
                    chunk = resp.read(_CHUNK)
                    if not chunk:
                        break
                    fh.write(chunk)
    except urllib.error.HTTPError as exc:
        if exc.code == 416 and existing:
            # Range not satisfiable: the file is already fully downloaded.
            return "ok", dest.stat().st_size, "already complete"
        return "failed", None, f"HTTP {exc.code}: {exc.reason}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return "failed", None, f"{type(exc).__name__}: {exc}"

    return "ok", dest.stat().st_size, None


def run(keys: list[str]) -> int:
    manifest = _load_manifest()
    results: list[tuple[str, str, int | None, str]] = []

    for key in keys:
        src = SOURCES_BY_KEY.get(key)
        if src is None:
            print(f"unknown source: {key!r}", file=sys.stderr)
            continue

        if src.manual or src.url is None:
            _record(manifest, src, "manual")
            results.append((src.key, "manual", None, src.notes))
            _save_manifest(manifest)
            continue

        status, size, note = _download(src)
        _record(manifest, src, status, size, extra_notes=note)
        results.append((src.key, status, size, note or src.notes))
        _save_manifest(manifest)

    # Status table (no raw file contents, just metadata).
    print("\n=== download status ===")
    print(f"{'source':<14} {'status':<8} {'size':<12} notes")
    print("-" * 72)
    for key, status, size, note in results:
        short = (note or "")[:40]
        print(f"{key:<14} {status:<8} {_human_size(size):<12} {short}")
    manual = [k for k, s, _, _ in results if s in ("manual", "failed")]
    if manual:
        print(f"\nStill needs you (manual/failed): {', '.join(manual)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pipeline.download")
    parser.add_argument("keys", nargs="*", help="source keys, or 'all'")
    parser.add_argument("--list", action="store_true", help="list known sources")
    args = parser.parse_args(argv)

    if args.list or not args.keys:
        print(f"{'key':<14} {'auto?':<6} name")
        print("-" * 72)
        for s in SOURCES:
            auto = "no" if (s.manual or s.url is None) else "yes"
            print(f"{s.key:<14} {auto:<6} {s.name}")
        return 0

    keys = [s.key for s in SOURCES] if args.keys == ["all"] else args.keys
    return run(keys)


if __name__ == "__main__":
    raise SystemExit(main())
