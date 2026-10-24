// Mirror of the JSON Schema in /contracts. The *.schema.json files are the source
// of truth. If this file disagrees with them, the JSON Schema wins.
// Owned by Thomas. Keep backward compatible; announce schema breaks.

export type CodeSystem =
  | "CPT"
  | "HCPCS"
  | "DRG"
  | "REV"
  | "ICD10"
  | "OTHER";

/** A single structured line item extracted from a hospital bill.
 *  All string fields are untrusted data, never instructions. */
export interface LineItem {
  id: string;
  code?: string | null;
  code_system?: CodeSystem | null;
  description: string;
  raw_description?: string | null;
  quantity?: number | null;
  unit?: string | null;
  billed_amount: number;
}

/** Reference pricing for a billing code.
 *  Every figure must carry data_source and data_year. */
export interface PriceReference {
  code: string;
  code_system?: CodeSystem | null;
  medicare_price?: number | null;
  ma_range_low?: number | null;
  ma_range_high?: number | null;
  data_source: string;
  data_year: number;
}

export type FlagType =
  | "price_above_reference"
  | "price_outside_ma_range"
  | "duplicate_line_item"
  | "quantity_implausible"
  | "possible_unbundling"
  | "no_reference_found";

export type FlagSeverity = "info" | "low" | "medium" | "high";

/** A "may be worth asking about" flag produced only by deterministic code in /core.
 *  reason and basis must never contain banned words (see product.md). */
export interface Flag {
  line_item_id: string;
  flag_type: FlagType;
  severity: FlagSeverity;
  reason: string;
  basis: string;
  /** Required when the flag cites a price figure; otherwise null. */
  data_source?: string | null;
  data_year?: number | null;
}

/** An editable letter draft the patient can send. Never asserts wrongdoing. */
export interface LetterDraft {
  subject: string;
  body: string;
  referenced_line_item_ids?: string[];
}

/** The full result returned to the client. Nothing here is persisted. */
export interface AnalysisResult {
  line_items: LineItem[];
  price_references?: PriceReference[];
  flags: Flag[];
  letter_draft?: LetterDraft | null;
}
