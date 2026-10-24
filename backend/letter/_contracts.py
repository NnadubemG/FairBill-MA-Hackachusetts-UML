"""Re-export of the shared `/contracts` types used by letter.

Imported from ``contracts.types`` (the same module ``/core`` uses), so these are the very
same classes. Nothing is redefined. Run from the repo root (pytest.ini sets
``pythonpath = .``).
"""

from __future__ import annotations

from contracts.types import Flag, LetterDraft, LineItem

__all__ = ["Flag", "LetterDraft", "LineItem"]
