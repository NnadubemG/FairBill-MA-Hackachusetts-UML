"""Re-export of the shared `/contracts` types used by explain.

We import from ``contracts.types`` (the same module ``/core`` uses) so the ``Flag``
class here is the very same class ``/core`` returns. Nothing is redefined.
Run from the repo root (pytest.ini sets ``pythonpath = .``).
"""

from __future__ import annotations

from contracts.types import Flag, FlagType

__all__ = ["Flag", "FlagType"]
