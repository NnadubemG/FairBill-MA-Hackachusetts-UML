"""Domain contracts — SINGLE SOURCE OF TRUTH (Python side).

Shared type definitions for the Massachusetts Medical-Bill Helper backend.
The server imports domain types from this module. Do NOT duplicate or redefine
these shapes elsewhere in the backend.

These are **Pydantic v2** models, so they double as runtime validation at the
API boundary (FastAPI uses them directly) — there is no second, hand-written
set of request/response models anywhere.

This mirrors the TypeScript definitions in `contracts/index.ts`. Keep the two
in sync: any change there must be reflected here (and vice versa).

Money is represented in whole US cents (int) to avoid floating-point rounding
on currency. `None` means "unknown / not available", distinct from 0.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Primitives / shared aliases
# ---------------------------------------------------------------------------

# Monetary amount in whole US cents. e.g. $12.34 -> 1234.
Cents = int
# A confidence score in the inclusive range [0, 1].
Confidence = float
# ISO-8601 timestamp string, e.g. "2026-10-24T14:30:00Z".
IsoTimestamp = str


class _Model(BaseModel):
    """Base for all contract models.

    `extra="forbid"` makes validation strict: unexpected fields are rejected,
    which keeps the client and server honest against this single source of
    truth.
    """

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Core domain types
# ---------------------------------------------------------------------------


class LineItem(_Model):
    """A single line extracted from a medical bill or EOB."""

    # Billing/procedure code (CPT/HCPCS/revenue code) if present, else None.
    code: Optional[str] = None
    # Human-readable description as it appears on the bill.
    description: str
    # Quantity/units billed. Defaults to 1 when the bill omits it.
    units: int = Field(default=1, ge=0)
    # Charged amount for this line, in cents. None if not legible/available.
    charge: Optional[Cents] = None
    # Model confidence that this line was extracted correctly, [0, 1].
    confidence: Confidence = Field(ge=0.0, le=1.0)
    # True when the value is uncertain and the user should confirm it.
    needs_confirmation: bool


# What a flag or reference is grounded in. Keeps explanations auditable.
FlagBasis = Literal[
    "medicare_reference",
    "ma_price_range",
    "duplicate_detection",
    "eob_mismatch",
    "arithmetic_check",
    "coding_heuristic",
    "other",
]


class Flag(_Model):
    """Something about a line worth the user's attention.

    Framed as information to consider, never as an accusation or a conclusion
    (see product.md banned words).
    """

    explanation: str
    basis: FlagBasis


class PriceRange(_Model):
    """A reference price range, in cents. Either bound may be None if unknown."""

    low: Optional[Cents] = None
    high: Optional[Cents] = None
    # Free-text note on the source/vintage of the range, if any.
    source: Optional[str] = None


class AnalysisResult(_Model):
    """Per-line analysis output. Correlated back to a LineItem by index."""

    # Index of the LineItem this analysis corresponds to (0-based).
    line_index: int = Field(ge=0)
    # A friendly, jargon-free label for the charge.
    plain_language_label: str
    # Medicare reference price for this code, in cents. None if unavailable.
    medicare_reference: Optional[Cents] = None
    # Typical Massachusetts price range for this service. None if unavailable.
    ma_price_range: Optional[PriceRange] = None
    # Zero or more flags worth the user's attention for this line.
    flags: List[Flag] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Letter types
# ---------------------------------------------------------------------------

# The kind of letter the user wants to draft.
LetterType = Literal[
    "itemized_bill_request",
    "billing_question",
    "charge_dispute",
    "insurance_appeal",
    "financial_assistance_request",
]

# Who the letter is addressed to.
LetterRecipient = Literal["provider", "insurer"]


class LetterDraft(_Model):
    """A generated letter draft for the user to review and send themselves.

    The app never sends on the user's behalf.
    """

    type: LetterType
    recipient: LetterRecipient
    subject: str
    # Full letter body, plain text, ready for the user to review/edit.
    body: str


# ---------------------------------------------------------------------------
# Shared error shape
# ---------------------------------------------------------------------------


class ApiError(_Model):
    """Standard error payload.

    Never contains request/response bodies or PII (see product.md + the
    privacy-preserving logging requirement).
    """

    error: str
    # Optional machine-readable code for the frontend to branch on.
    code: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoint request/response shapes
# ---------------------------------------------------------------------------


class ExtractRequest(_Model):
    """POST /api/extract — turn raw bill text into structured line items."""

    # Raw bill or EOB text pasted/OCR'd by the user.
    text: str
    # Optional hint about the document kind: "bill" | "eob" | "unknown".
    source_kind: Optional[Literal["bill", "eob", "unknown"]] = None


class ExtractResponse(_Model):
    line_items: List[LineItem] = Field(default_factory=list)
    # Overall confidence that extraction succeeded, [0, 1].
    overall_confidence: Confidence = Field(ge=0.0, le=1.0)


class AnalyzeRequest(_Model):
    """POST /api/analyze — analyze extracted line items."""

    line_items: List[LineItem]


class AnalyzeResponse(_Model):
    results: List[AnalysisResult] = Field(default_factory=list)


class ProceduresRequest(_Model):
    """GET /api/procedures — look up known procedures/codes for reference."""

    # Optional free-text search over descriptions/codes.
    query: Optional[str] = None
    # Optional explicit list of codes to resolve.
    codes: Optional[List[str]] = None


class ProcedureInfo(_Model):
    code: str
    plain_language_label: str
    description: str
    medicare_reference: Optional[Cents] = None
    ma_price_range: Optional[PriceRange] = None


class ProceduresResponse(_Model):
    procedures: List[ProcedureInfo] = Field(default_factory=list)


class CompareRequest(_Model):
    """GET /api/compare — compare a charge against reference pricing."""

    code: str
    # The amount the user was charged, in cents.
    charged: Cents
    units: Optional[int] = Field(default=None, ge=0)


class CompareResponse(_Model):
    code: str
    charged: Cents
    medicare_reference: Optional[Cents] = None
    ma_price_range: Optional[PriceRange] = None
    # charged / medicare_reference, when both are known; else None.
    ratio_to_medicare: Optional[float] = None
    flags: List[Flag] = Field(default_factory=list)


class LetterRequest(_Model):
    """POST /api/letter — draft a letter for the user to review and send."""

    type: LetterType
    recipient: LetterRecipient
    # Line items the letter concerns (optional, for context).
    line_items: Optional[List[LineItem]] = None
    # Free-text context the user provides (their question/situation).
    context: Optional[str] = None


class LetterResponse(_Model):
    letter: LetterDraft
