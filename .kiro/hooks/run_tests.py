"""Run the project's pytest suite. Script-based hook helper: stdlib only.

Prefers the repo's .venv interpreter (Windows or Unix) and falls back to the current one.
Team rule: /core changes need pytest to pass before merging.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CANDIDATES = (ROOT / ".venv" / "Scripts" / "python.exe", ROOT / ".venv" / "bin" / "python")


def main() -> int:
    python = next((str(c) for c in CANDIDATES if c.exists()), sys.executable)
    return subprocess.run([python, "-m", "pytest", "-q"], cwd=ROOT).returncode


if __name__ == "__main__":
    sys.exit(main())
