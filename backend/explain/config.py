"""Configuration for explanations.

The model name is never hardcoded; it comes from ``EXPLAIN_MODEL_ID``. The API key
comes from ``ANTHROPIC_API_KEY`` (read by the shared client in ``/backend/extract``).
"""

from __future__ import annotations

from typing import Final

# Environment variable that holds the Anthropic model name used for explanations.
# Use a small, cheap model here (see the "smallest model that passes the evals" rule).
ENV_MODEL_ID: Final[str] = "EXPLAIN_MODEL_ID"

# At most this many flags go into the single model call. Extra flags use the fallback.
MAX_FLAGS_PER_CALL: Final[int] = 30

# An explanation longer than this many words is rejected (short by design).
MAX_WORDS: Final[int] = 60

# Words and phrases that must never appear in an explanation.
# Keep in sync with .kiro/steering/product.md. A test compares this tuple with
# core.constants.BANNED_WORDS so drift is caught.
BANNED_WORDS: Final[tuple[str, ...]] = (
    "overcharged",
    "illegal",
    "fraud",
    "incorrect charge",
    "you should dispute",
    "you are owed",
)

# Words that imply a new figure ("twice", "half", ...). Allowed only when the same word
# is already in the flag's reason or basis.
IMPLIED_FIGURE_WORDS: Final[tuple[str, ...]] = (
    "twice",
    "double",
    "triple",
    "half",
    "percent",
    "fold",
)

# Sentence limits for an explanation.
MIN_SENTENCES: Final[int] = 2
MAX_SENTENCES: Final[int] = 3
