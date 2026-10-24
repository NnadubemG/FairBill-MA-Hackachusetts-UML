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
  /** ISO 8601 date (YYYY-MM-DD), if printed on the bill. Optional. */
  date_of_service?: string | null;
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

export type PayerGroup =
  | "commercial"
  | "medicare_advantage"
  | "medicaid_managed"
  | "cash"
  | "gross";

/** One curated procedure, keyed by code. Drives pipeline filtering. */
export interface ProcedureInfo {
  code: string;
  code_system?: CodeSystem | null;
  plain_label: string;
  category?: string | null;
  typical_max_units?: number | null;
}

/** Price statistics for one hospital + code + payer group.
 *  Numeric fields are nullable; we never invent a number we do not have.
 *  When min/median/max are all present: min_rate <= median_rate <= max_rate. */
export interface PriceStat {
  hospital_id: string;
  code: string;
  code_system?: CodeSystem | null;
  payer_group: PayerGroup;
  min_rate?: number | null;
  median_rate?: number | null;
  max_rate?: number | null;
  cash_price?: number | null;
  gross_charge?: number | null;
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
  /** Plain-language rewrite of `reason`, set by the explain handler (LLM).
   *  /core always leaves this null. Adds no facts or numbers beyond reason/basis. */
  explanation?: string | null;
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

// --- Synthetic bills (produced by /synthetic; see synthetic-bill.schema.json) ---

export type ModifierIndicator = "0" | "1" | "9";

/** A typical maximum number of units for a code, with source and year. */
export interface QuantityLimit {
  code: string;
  code_system?: CodeSystem | null;
  max_units: number;
  data_source: string;
  data_year: number;
}

/** Two codes normally billed together. The flag goes on the code_2 line.
 *  "0" may not be billed together; "1" only with a modifier; "9" edit does not apply. */
export interface BundlePair {
  code_1: string;
  code_2: string;
  modifier_indicator: ModifierIndicator;
  data_source: string;
  data_year: number;
}

export type SyntheticScenario =
  | "clean"
  | "duplicate"
  | "high_price"
  | "unknown_code"
  | "injection"
  | "mixed"
  | "quantity"
  | "unbundling"
  | "no_code";

/** Fictional statement header. statement_date is ISO 8601 (YYYY-MM-DD). */
export interface BillMetadata {
  hospital_name: string;
  statement_date: string;
  total_billed: number;
}

/** One (line item, flag type) pair that /core should produce. */
export interface ExpectedFlag {
  line_item_id: string;
  flag_type: FlagType;
}

/** A fictional bill plus ground truth for evals, tests, and demos. */
export interface SyntheticBill {
  bill_id: string;
  seed: number;
  scenario: SyntheticScenario;
  bill_metadata: BillMetadata;
  /** Ground truth for extraction. */
  line_items: LineItem[];
  /** Fictional reference prices (data_source "synthetic-demo"). */
  price_references: PriceReference[];
  /** Optional (older bills omit it). Pass to analyze as quantity_limits. */
  quantity_limits?: QuantityLimit[];
  /** Optional (older bills omit it). Pass to analyze as bundle_pairs. */
  bundle_pairs?: BundlePair[];
  /** Exactly what /core should return for line_items and price_references. */
  expected_flags: ExpectedFlag[];
}
