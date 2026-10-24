"""Append structured lines to skipped.log.

A skip means we found no trustworthy dollar figure, so we never write a dollar value
here. Each line records just enough to locate the source row: hospital, code, the raw
payer label, and the reason. Tab-separated, one skip per line.
"""

from __future__ import annotations

from pathlib import Path

from . import config


def format_skip(hospital_id: str, code: str, raw_payer: str, reason: str) -> str:
    """Build one skip-log line. No dollar value is ever included."""
    # Collapse tabs/newlines in untrusted fields so one skip stays on one line.
    def clean(s: str) -> str:
        return (s or "").replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()

    return "\t".join(
        ["SKIP", clean(hospital_id), clean(code), clean(raw_payer), clean(reason)]
    )


def log_skip(
    hospital_id: str,
    code: str,
    raw_payer: str,
    reason: str,
    path: str | Path | None = None,
) -> None:
    """Append one skip line to the skip log."""
    path = Path(path) if path else config.SKIPPED_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    line = format_skip(hospital_id, code, raw_payer, reason)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(line + "\n")
