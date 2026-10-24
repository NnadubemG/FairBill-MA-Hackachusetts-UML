"""Explain result type (a wrapper, not a contract)."""

from __future__ import annotations

from dataclasses import dataclass, field

from ._contracts import Flag


@dataclass(frozen=True)
class ExplainResult:
    """What the explain handler returns. Nothing here is persisted.

    - ``flags``: same length and order as the input. Each flag equals the input flag
      except that ``explanation`` is set.
    - ``fallback_count``: how many flags used the deterministic fallback.
    - ``warnings``: fixed, generic text only. Never contains flag content.
    """

    flags: list[Flag] = field(default_factory=list)
    fallback_count: int = 0
    warnings: list[str] = field(default_factory=list)


__all__ = ["ExplainResult"]
