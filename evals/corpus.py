"""Build the eval corpus from /synthetic, in memory.

Each bill is one synthetic bill in one layout (style), as PDF bytes plus its ground truth.
Nothing is written to disk. Only synthetic bills are used.

``ensure_not_private`` keeps the harness away from ``/private`` (the real redacted bill
lives there and must never be cached, logged or written about).
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from contracts.types import SyntheticBill
from synthetic import SCENARIOS, STYLES, generate_bill, render_pdf

from . import config


class PrivatePathError(ValueError):
    """Raised when a path points inside /private."""


def ensure_not_private(path: str | os.PathLike[str]) -> Path:
    """Return the resolved path, or raise ``PrivatePathError`` if it is inside /private.

    Works for paths that do not exist yet, for ``..`` tricks, for symlinks that exist, and
    on case-insensitive file systems.
    """
    resolved = Path(path).expanduser().resolve()
    private = config.PRIVATE_DIR.resolve()
    target = str(resolved).casefold()
    root = str(private).casefold()
    if target == root or target.startswith(root + os.sep):
        raise PrivatePathError("paths inside /private are not allowed")
    return resolved


@dataclass(frozen=True)
class Bill:
    """One synthetic bill in one layout."""

    bill_id: str  # for example "mixed-1"
    scenario: str
    style: str  # the layout: "plain" or "messy"
    pdf: bytes
    file_sha256: str  # SHA-256 of ``pdf``
    truth: SyntheticBill

    @property
    def key(self) -> str:
        """Unique label for reports: bill id and layout."""
        return f"{self.bill_id}/{self.style}"


def _choose(values: Iterable[str] | None, valid: Sequence[str], what: str) -> list[str]:
    """Validate a user choice against the valid values; keep order, drop repeats."""
    chosen = list(valid) if values is None else list(dict.fromkeys(values))
    unknown = [v for v in chosen if v not in valid]
    if unknown:
        raise ValueError(f"unknown {what}: {', '.join(map(str, unknown))}. Valid: {', '.join(valid)}")
    if not chosen:
        raise ValueError(f"no {what} selected")
    return chosen


def build_corpus(
    scenarios: Iterable[str] | None = None,
    seeds: Iterable[int] | None = None,
    styles: Iterable[str] | None = None,
) -> list[Bill]:
    """Build the bills for the chosen scenarios, seeds and styles.

    The same arguments always give the same bills (same bytes). The list is sorted by
    bill id, then style.
    """
    chosen_scenarios = _choose(scenarios, SCENARIOS, "scenario")
    chosen_styles = _choose(styles, STYLES, "style")
    seed_list = list(dict.fromkeys(config.DEFAULT_SEEDS if seeds is None else seeds))
    if not seed_list:
        raise ValueError("no seeds selected")
    for seed in seed_list:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("seeds must be whole numbers")

    bills: list[Bill] = []
    for scenario in chosen_scenarios:
        for seed in seed_list:
            truth = generate_bill(seed, scenario)
            for style in chosen_styles:
                pdf = render_pdf(truth, style)
                bills.append(
                    Bill(
                        bill_id=truth.bill_id,
                        scenario=scenario,
                        style=style,
                        pdf=pdf,
                        file_sha256=hashlib.sha256(pdf).hexdigest(),
                        truth=truth,
                    )
                )
    bills.sort(key=lambda b: (b.bill_id, b.style))
    return bills


__all__ = ["PrivatePathError", "ensure_not_private", "Bill", "build_corpus"]
