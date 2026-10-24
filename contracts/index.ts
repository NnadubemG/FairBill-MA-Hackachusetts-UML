/**
 * Domain contracts — SINGLE SOURCE OF TRUTH.
 *
 * Shared type definitions for the Massachusetts Medical-Bill Helper.
 * The frontend and the server BOTH import domain types from this module.
 * Do NOT duplicate or redefine these shapes anywhere else.
 *
 * A matching Python module lives at `contracts/contracts.py`. Keep the two in
 * sync: any change here must be mirrored there (and vice versa).
 *
 * Money is represented in whole US cents (integer) to avoid floating-point
 * rounding on currency. `null` means "unknown / not available", distinct from 0.
 */

// ---------------------------------------------------------------------------
// Primitives / shared aliases
// ---------------------------------------------------------------------------

/** Monetary amount in whole US cents. e.g. $12.34 -> 1234. */
export type Cents = number;

/** A confidence score in the inclusive range [0, 1]. */
export type Confidence = number;

/** ISO-8601 timestamp string, e.g. "2026-10-24T14:30:00Z". */
export type IsoTimestamp = string;

// ---------------------------------------------------------------------------
// Core domain types
// ---------------------------------------------------------------------------

/**
 * A single line extracted from a medical bill or EOB.
 */
export interface LineItem {
  /** Billing/procedure code (CPT/HCPCS/revenue code) if present, else null. */
  code: string | null;
  /** Human-readable description as it appears on the bill. */
  description: string;
  /** Quantity/units billed. Defaults to 1 when the bill omits it. */
  units: number;
  /** Charged amount for this line, in cents. null if not legible/available. */
  charge: Cents | null;
  /** Model confidence that this line was extracted correctly, [0, 1]. */
  confidence: Confidence;
  /** True when the value is uncertain and the user should confirm it. */
  needs_confirmation: boolean;
}

/**
 * The basis/source category behind a flag or reference. Keeps explanations
 * grounded and auditable rather than asserted.
 */
export type FlagBasis =
  | 'medicare_reference'
  | 'ma_price_range'
  | 'duplicate_detection'
  | 'eob_mismatch'
  | 'arithmetic_check'
  | 'coding_heuristic'
  | 'other';

/**
 * Something about a line worth the user's attention. Framed as information to
 * consider, never as an accusation or a conclusion (see product.md banned words).
 */
export interface Flag {
  /** Plain-language explanation of what was noticed. */
  explanation: string;
  /** What the explanation is grounded in. */
  basis: FlagBasis;
}

/**
 * A reference price range, in cents. Either bound may be null if unknown.
 */
export interface PriceRange {
  low: Cents | null;
  high: Cents | null;
  /** Free-text note on the source/vintage of the range, if any. */
  source?: string | null;
}

/**
 * Per-line analysis output. Correlated back to a LineItem by index/id.
 */
export interface AnalysisResult {
  /** Index of the LineItem this analysis corresponds to (0-based). */
  line_index: number;
  /** A friendly, jargon-free label for the charge. */
  plain_language_label: string;
  /** Medicare reference price for this code, in cents. null if unavailable. */
  medicare_reference: Cents | null;
  /** Typical Massachusetts price range for this service. null if unavailable. */
  ma_price_range: PriceRange | null;
  /** Zero or more flags worth the user's attention for this line. */
  flags: Flag[];
}

// ---------------------------------------------------------------------------
// Letter types
// ---------------------------------------------------------------------------

/** The kind of letter the user wants to draft. */
export type LetterType =
  | 'itemized_bill_request'
  | 'billing_question'
  | 'charge_dispute'
  | 'insurance_appeal'
  | 'financial_assistance_request';

/** Who the letter is addressed to. */
export type LetterRecipient = 'provider' | 'insurer';

/**
 * A generated letter draft. Always a draft for the user to review and send
 * themselves — the app never sends on the user's behalf.
 */
export interface LetterDraft {
  type: LetterType;
  recipient: LetterRecipient;
  subject: string;
  /** Full letter body, plain text, ready for the user to review/edit. */
  body: string;
}

// ---------------------------------------------------------------------------
// Shared error shape
// ---------------------------------------------------------------------------

/**
 * Standard error payload. Never contains request/response bodies or PII
 * (see product.md + the privacy-preserving logging requirement).
 */
export interface ApiError {
  error: string;
  /** Optional machine-readable code for the frontend to branch on. */
  code?: string;
}

// ---------------------------------------------------------------------------
// Endpoint request/response shapes
// ---------------------------------------------------------------------------

/** POST /api/extract — turn raw bill text/image-OCR into structured line items. */
export interface ExtractRequest {
  /** Raw bill or EOB text pasted/OCR'd by the user. */
  text: string;
  /** Optional hint about the document kind. */
  source_kind?: 'bill' | 'eob' | 'unknown';
}
export interface ExtractResponse {
  line_items: LineItem[];
  /** Overall confidence that extraction succeeded, [0, 1]. */
  overall_confidence: Confidence;
}

/** POST /api/analyze — analyze extracted line items. */
export interface AnalyzeRequest {
  line_items: LineItem[];
}
export interface AnalyzeResponse {
  results: AnalysisResult[];
}

/** GET /api/procedures — look up known procedures/codes for reference. */
export interface ProceduresRequest {
  /** Optional free-text search over descriptions/codes. */
  query?: string;
  /** Optional explicit list of codes to resolve. */
  codes?: string[];
}
export interface ProcedureInfo {
  code: string;
  plain_language_label: string;
  description: string;
  medicare_reference: Cents | null;
  ma_price_range: PriceRange | null;
}
export interface ProceduresResponse {
  procedures: ProcedureInfo[];
}

/** GET /api/compare — compare a charge against reference pricing. */
export interface CompareRequest {
  code: string;
  /** The amount the user was charged, in cents. */
  charged: Cents;
  units?: number;
}
export interface CompareResponse {
  code: string;
  charged: Cents;
  medicare_reference: Cents | null;
  ma_price_range: PriceRange | null;
  /** charged / medicare_reference, when both are known; else null. */
  ratio_to_medicare: number | null;
  flags: Flag[];
}

/** POST /api/letter — draft a letter for the user to review and send. */
export interface LetterRequest {
  type: LetterType;
  recipient: LetterRecipient;
  /** Line items the letter concerns (optional, for context). */
  line_items?: LineItem[];
  /** Free-text context the user provides (their question/situation). */
  context?: string;
}
export interface LetterResponse {
  letter: LetterDraft;
}
