"""Tiny ``.env`` loader. Standard library only.

``load_env(path)`` reads simple ``NAME=value`` lines and sets a variable ONLY when it is
not already set (a missing or blank variable counts as not set). Real environment
variables always win.

Safety:
* It returns the NAMES it set, never the values.
* It never prints or logs anything.
* A missing, unreadable or odd file is not an error: it sets nothing.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import MutableMapping

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_PATH = REPO_ROOT / ".env"

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MAX_BYTES = 64 * 1024


def _clean_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    if value[:1] in ("'", '"'):  # an opening quote with no closing quote: unusable
        return ""
    # Unquoted value: a " #" starts a comment.
    return re.split(r"\s+#", value, maxsplit=1)[0].strip()


def parse_env(text: str) -> dict[str, str]:
    """Parse ``.env`` text into a dict. Skips blank lines, comments and bad lines."""
    found: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip().lstrip("\ufeff")
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        name, sep, raw = line.partition("=")
        name = name.strip()
        if not sep or not _NAME.match(name):
            continue
        value = _clean_value(raw)
        if value and "\x00" not in value:
            found[name] = value
    return found


def load_env(
    path: Path | str = DEFAULT_ENV_PATH,
    *,
    environ: MutableMapping[str, str] | None = None,
) -> list[str]:
    """Set variables from ``path`` that are not already set. Return the names set."""
    env = os.environ if environ is None else environ
    try:
        file_path = Path(path)
        if not file_path.is_file() or file_path.stat().st_size > _MAX_BYTES:
            return []
        text = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    names: list[str] = []
    for name, value in parse_env(text).items():
        if not env.get(name, "").strip():
            env[name] = value
            names.append(name)
    return names
