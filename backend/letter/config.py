"""Configuration for letter drafts.

The model name is never hardcoded; it comes from ``LETTER_MODEL_ID``. The API key comes
from ``ANTHROPIC_API_KEY`` (read by the shared client in ``/backend/extract``).

The tone word lists below are rules of thumb. They are strict on purpose: a paragraph that
trips one is replaced by the fixed fallback paragraph, which is always safe.
"""

from __future__ import annotations

from typing import Final

# The banned words come from explain's config, so there is one list for the whole lane.
# (A test checks it equals core.constants.BANNED_WORDS.)
from backend.explain.config import BANNED_WORDS, IMPLIED_FIGURE_WORDS  # noqa: F401

# Environment variable that holds the Anthropic model name used for the reason paragraph.
# Use a small, cheap model (see the "smallest model that passes the evals" rule).
ENV_MODEL_ID: Final[str] = "LETTER_MODEL_ID"

# At most this many flags are used in one letter. Extra flags are skipped.
MAX_FLAGS: Final[int] = 10

# Reason paragraph limits.
MAX_PARAGRAPH_WORDS: Final[int] = 90
MIN_SENTENCES: Final[int] = 2
MAX_SENTENCES: Final[int] = 4

# Cap on the model reply (one short paragraph).
MAX_TOKENS: Final[int] = 300

# Maximum length of each patient field after cleaning.
MAX_NAME: Final[int] = 80
MAX_ACCOUNT: Final[int] = 40
MAX_HOSPITAL: Final[int] = 120
MAX_DATE: Final[int] = 40
MAX_NOTES: Final[int] = 1000

# --- tone checks for the reason paragraph (regex, matched on lowercased text) ----------

ACCUSATION_PATTERNS: Final[tuple[str, ...]] = (
    r"\bwrong", r"\bmistake", r"\berror", r"\bover-?bill", r"\bover-?charg", r"\bscam",
    r"\bcheat", r"\bsteal", r"\bstole", r"\brip(?:ped)?[- ]?off", r"\bimproper",
    r"\bunfair", r"\bunlawful", r"\bdeceiv", r"\bdeceptive", r"\bmislead", r"\bdishonest",
    r"\bgoug", r"\bblame", r"\bnegligen", r"\bmisconduct", r"\bdouble[- ]?bill",
    r"\bexcessive", r"\binflated", r"\bat fault",
)

LEGAL_PATTERNS: Final[tuple[str, ...]] = (
    r"\blawsuit", r"\bsue\b", r"\bsuing\b", r"\battorney", r"\blawyer", r"\blegal",
    r"\blaws?\b", r"\blawful", r"\bcourt", r"\bviolat", r"\bregulat", r"\bcomplaint",
    r"\bauthorit(?:y|ies)\b", r"\bconsumer protection", r"\bsubpoena", r"\bliab",
)

MONEY_DEMAND_PATTERNS: Final[tuple[str, ...]] = (
    r"\brefund", r"\breimburs", r"\bcompensat", r"\bdemand", r"\byou owe\b", r"\bowed?\b",
    r"\bpenalt", r"\bdamages\b", r"\bmoney back\b", r"\bpay (?:me )?back\b",
)

DEADLINE_PATTERNS: Final[tuple[str, ...]] = (
    r"\bwithin\b", r"\bdeadline", r"\bimmediate", r"\bno later than\b", r"\burgent",
    r"\basap\b", r"\bat once\b", r"\bor else\b", r"\bright away\b",
    r"\bby (?:the )?(?:end|next|this|tomorrow|monday|tuesday|wednesday|thursday|friday)",
    r"\bbefore (?:the )?(?:end|next)",
)

# Words that belong to the fixed template (greeting and sign-off), not the paragraph.
LETTER_FRAME_WORDS: Final[tuple[str, ...]] = ("dear", "sincerely", "regards", "yours")

# First-person words. The paragraph must contain at least one.
FIRST_PERSON_WORDS: Final[tuple[str, ...]] = ("i", "my", "me", "i'd", "i'm", "i've", "i'll")
