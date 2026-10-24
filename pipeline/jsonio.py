"""Stable JSON read/write helpers.

Writing goes through ``write_json`` so every processed output uses the same
deterministic formatting (sorted keys, 2-space indent, trailing newline). This keeps
diffs clean and makes the determinism property test meaningful.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from .config import JSON_DUMP_KWARGS


def _to_jsonable(obj: Any) -> Any:
    """Convert dataclass instances (contract types) to plain dicts recursively.

    Missing values stay as ``None`` (null); we never substitute a placeholder.
    """
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _to_jsonable(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    return obj


def dumps(obj: Any) -> str:
    """Serialize to a deterministic JSON string with a trailing newline."""
    return json.dumps(_to_jsonable(obj), **JSON_DUMP_KWARGS) + "\n"


def write_json(path: str | Path, obj: Any) -> None:
    """Write ``obj`` to ``path`` using deterministic formatting.

    Creates parent directories if needed. UTF-8, LF line endings.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(dumps(obj))


def read_json(path: str | Path) -> Any:
    """Read JSON from ``path`` (UTF-8)."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)
