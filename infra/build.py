"""Build the Lambda zip directory used by infra/template.yaml.

Copies only runtime code, processed public data, and static frontend assets. It
never copies /private, raw data, environment files, or test caches.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "infra" / "build"

IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", ".pytest_cache", ".hypothesis", "tests", "node_modules"
)


def copy_tree(relative: str, destination: str | None = None) -> None:
    source = ROOT / relative
    if not source.exists():
        raise FileNotFoundError(f"required runtime path missing: {relative}")
    shutil.copytree(source, BUILD / (destination or relative), ignore=IGNORE)


def main() -> int:
    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)

    for package in ("app_server", "backend", "contracts", "core", "pipeline"):
        copy_tree(package)
    copy_tree("data/processed", "data/processed")

    static = BUILD / "static"
    shutil.copytree(ROOT / "frontend", static, ignore=IGNORE)
    root_index = ROOT / "frontend" / "index.html"
    compare_index = ROOT / "frontend" / "src" / "compare" / "index.html"
    if root_index.exists():
        shutil.copy2(root_index, static / "index.html")
    elif compare_index.exists():
        shutil.copy2(compare_index, static / "index.html")
    else:
        raise FileNotFoundError("frontend has no index.html")

    pip_command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-compile",
        "--target",
        str(BUILD),
    ]
    # Lambda is Amazon Linux. A Windows developer build must resolve Linux wheels,
    # not silently package Windows-native pydantic/jiter/rpds binaries.
    if sys.platform == "win32":
        pip_command.extend(
            [
                "--platform",
                "manylinux2014_x86_64",
                "--implementation",
                "cp",
                "--python-version",
                "3.12",
                "--abi",
                "cp312",
                "--only-binary=:all:",
            ]
        )
    pip_command.extend(["-r", str(ROOT / "requirements.txt")])
    subprocess.run(pip_command, check=True)
    print(f"Lambda bundle ready: {BUILD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
