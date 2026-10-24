"""Assemble the deployable bundle in infra/.build (used by the SAM template).

    python infra/build.py            # copy code + data, install Linux wheels for Lambda
    python infra/build.py --no-deps  # copy only (fast; for checking the layout)

Copies only what the running app needs: the Python packages, the committed processed
data, the public frontend, and the sample bills. Raw data, tests, specs, and caches are
never included. Dependencies are installed as manylinux wheels for Python 3.12 so the
bundle built on Windows/macOS runs on Lambda.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "infra" / ".build"

PACKAGES = ["app_server", "backend", "core", "contracts", "pipeline"]
EXTRA = [
    "data/processed",
    "frontend/index.html",
    "frontend/app",
    "frontend/src/compare",
]
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "tests", "test_*.py", "*.md", ".pytest_cache")


def _copy(rel: str) -> None:
    src = REPO / rel
    dst = OUT / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, ignore=IGNORE, dirs_exist_ok=True)
    elif src.exists():
        shutil.copy2(src, dst)


def _clear(path: Path) -> None:
    """Remove a previous build. Synced folders (OneDrive) can briefly lock files, so
    retry a few times and fall back to building over whatever is left."""
    import stat
    import time

    def _unlock(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass

    for _ in range(3):
        if not path.exists():
            return
        shutil.rmtree(path, onexc=_unlock) if sys.version_info >= (3, 12) else shutil.rmtree(path, onerror=_unlock)
        time.sleep(0.5)


def build(install_deps: bool = True) -> Path:
    _clear(OUT)
    OUT.mkdir(parents=True, exist_ok=True)
    for pkg in PACKAGES + EXTRA:
        _copy(pkg)
    samples = OUT / "synthetic" / "samples"
    samples.mkdir(parents=True, exist_ok=True)
    for f in (REPO / "synthetic" / "samples").glob("bill-*.json"):
        shutil.copy2(f, samples / f.name)

    if install_deps:
        subprocess.run(
            [
                sys.executable, "-m", "pip", "install",
                "-r", str(REPO / "requirements.txt"),
                "--target", str(OUT),
                "--platform", "manylinux2014_x86_64",
                "--implementation", "cp",
                "--python-version", "3.12",
                "--only-binary=:all:",
                "--upgrade", "--quiet",
            ],
            check=True,
        )
    size = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    print(f"bundle ready: {OUT} ({size / 1_048_576:.1f} MB)")
    return OUT


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-deps", action="store_true")
    build(install_deps=not ap.parse_args().no_deps)
