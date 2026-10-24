// Pure helpers for the FairBill app. No DOM, no network, no storage, so they are
// unit-testable with `node --test`. Every price shown comes from the API; these
// functions only format or group what the API returned. They never invent a number.

// language-guard: allow  (this list exists so the UI can be tested against it)
export const BANNED_PHRASES = [
  "overcharged",
  "illegal",
  "fraud",
  "incorrect charge",
  "you should dispute",
  "you are owed",
];

export const SEVERITY_ORDER = { high: 0, medium: 1, low: 2, info: 3 };

export const SEVERITY_LABEL = {
  high: "Worth asking first",
  medium: "Worth asking",
  low: "Minor question",
  info: "For your information",
};

export const FLAG_TITLE = {
  price_above_reference: "Higher than the Medicare reference",
  price_outside_ma_range: "Outside the usual Massachusetts range",
  duplicate_line_item: "Appears more than once",
  quantity_implausible: "Unusual quantity",
  possible_unbundling: "Billed separately from a related service",
  no_reference_found: "No reference price available",
};

export const LETTER_TYPES = [
  {
    id: "itemized_bill",
    title: "Request an itemized bill",
    blurb: "Ask the hospital for a full, line-by-line bill with billing codes.",
  },
  {
    id: "coding_review",
    title: "Ask for a coding review",
    blurb: "Ask the billing office to look again at the items flagged below.",
  },
  {
    id: "financial_assistance",
    title: "Ask about financial assistance",
    blurb: "Ask whether you qualify for the hospital's financial assistance program.",
  },
];

export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

export function money(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return null;
  return "$" + Number(value).toLocaleString("en-US", {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  });
}

// "$1,234.00" or an em dash for missing values (never a 0 placeholder).
export function moneyOrDash(value) {
  return money(value) ?? "—";
}

// Parse a user-typed amount: "$1,234.50" -> 1234.5. Blank or invalid -> null.
export function parseAmount(text) {
  if (text === null || text === undefined) return null;
  if (typeof text === "number") return Number.isFinite(text) ? text : null;
  const cleaned = String(text).replace(/[$,\s]/g, "");
  if (cleaned === "") return null;
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
}

function blankToNull(v) {
  if (v === null || v === undefined) return null;
  const s = String(v).trim();
  return s === "" ? null : s;
}

// Turn an editable form row into a contract LineItem. Unknown/blank fields become null.
export function rowToLineItem(row) {
  const code = blankToNull(row.code);
  return {
    id: String(row.id),
    description: String(row.description ?? "").trim(),
    billed_amount: parseAmount(row.billed_amount),
    code: code ? code.toUpperCase() : null,
    code_system: code ? (blankToNull(row.code_system) ?? guessCodeSystem(code)) : null,
    raw_description: blankToNull(row.raw_description),
    quantity: parseAmount(row.quantity),
    unit: blankToNull(row.unit),
    date_of_service: blankToNull(row.date_of_service),
  };
}

// A label for the system only when the shape is unambiguous; otherwise null.
// This never changes a code, it only tags it. Five digits = CPT, letter + four digits =
// HCPCS Level II. Anything else stays unknown (null) rather than guessed.
export function guessCodeSystem(code) {
  const c = String(code || "").trim().toUpperCase();
  if (/^\d{5}$/.test(c)) return "CPT";
  if (/^[A-Z]\d{4}$/.test(c)) return "HCPCS";
  return null;
}

// Validate rows before analysis. Returns [{rowId, field, message}].
export function validateRows(rows) {
  const errors = [];
  if (!rows.length) {
    errors.push({ rowId: null, field: null, message: "Add at least one line from your bill." });
  }
  for (const row of rows) {
    const item = rowToLineItem(row);
    if (!item.description) {
      errors.push({ rowId: row.id, field: "description", message: "Add a description." });
    }
    if (item.billed_amount === null) {
      errors.push({ rowId: row.id, field: "billed_amount", message: "Enter the billed amount." });
    } else if (item.billed_amount < 0) {
      errors.push({ rowId: row.id, field: "billed_amount", message: "Amount can't be negative." });
    }
    if (row.quantity !== undefined && String(row.quantity ?? "").trim() !== "") {
      const q = parseAmount(row.quantity);
      if (q === null || q <= 0) {
        errors.push({ rowId: row.id, field: "quantity", message: "Quantity must be a positive number." });
      }
    }
    if (item.date_of_service && !/^\d{4}-\d{2}-\d{2}$/.test(item.date_of_service)) {
      errors.push({ rowId: row.id, field: "date_of_service", message: "Use the date picker (YYYY-MM-DD)." });
    }
  }
  return errors;
}

// Next free numeric-string id for a new row.
export function nextRowId(rows) {
  let max = 0;
  for (const r of rows) {
    const n = Number(r.id);
    if (Number.isInteger(n) && n > max) max = n;
  }
  return String(max + 1);
}

// Build editable rows from an extraction result (line items + confidence side channel).
export function rowsFromExtraction(extraction) {
  const conf = new Map(
    (extraction?.line_confidence || []).map((c) => [c.line_item_id, c]),
  );
  return (extraction?.line_items || []).map((li) => ({
    id: String(li.id),
    description: li.description ?? "",
    raw_description: li.raw_description ?? null,
    code: li.code ?? "",
    code_system: li.code_system ?? null,
    quantity: li.quantity ?? "",
    unit: li.unit ?? null,
    date_of_service: li.date_of_service ?? "",
    billed_amount: li.billed_amount ?? "",
    needs_confirmation: Boolean(conf.get(String(li.id))?.needs_confirmation),
    confidence: conf.get(String(li.id))?.confidence ?? null,
  }));
}

export function rowsFromLineItems(items) {
  return rowsFromExtraction({ line_items: items, line_confidence: [] });
}

export function totalBilled(items) {
  let sum = 0;
  let any = false;
  for (const it of items) {
    const v = parseAmount(it.billed_amount);
    if (v !== null) { sum += v; any = true; }
  }
  return any ? Math.round(sum * 100) / 100 : null;
}

function normCode(code) {
  return String(code || "").trim().toUpperCase();
}

export function referenceForCode(priceReferences, code) {
  const c = normCode(code);
  if (!c) return null;
  return (priceReferences || []).find((r) => normCode(r.code) === c) || null;
}

// Group flags under their line items, sorted by severity. Line items with flags come
// first (most important first), then clean lines in bill order.
export function buildResultRows(analysis) {
  const items = analysis?.line_items || [];
  const flags = analysis?.flags || [];
  const refs = analysis?.price_references || [];
  const byLine = new Map(items.map((it) => [String(it.id), []]));
  for (const f of flags) {
    const key = String(f.line_item_id);
    if (byLine.has(key)) byLine.get(key).push(f);
  }
  const rows = items.map((it, index) => {
    const lineFlags = [...byLine.get(String(it.id))].sort(
      (a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9),
    );
    const top = lineFlags.length ? SEVERITY_ORDER[lineFlags[0].severity] ?? 9 : 99;
    return { item: it, flags: lineFlags, reference: referenceForCode(refs, it.code), index, top };
  });
  rows.sort((a, b) => a.top - b.top || a.index - b.index);
  return rows;
}

// Headline numbers for the results page.
export function summarize(analysis) {
  const items = analysis?.line_items || [];
  const flags = analysis?.flags || [];
  const askable = flags.filter((f) => f.flag_type !== "no_reference_found");
  const linesWithQuestions = new Set(askable.map((f) => String(f.line_item_id)));
  const noRef = new Set(
    flags.filter((f) => f.flag_type === "no_reference_found").map((f) => String(f.line_item_id)),
  );
  const bySeverity = { high: 0, medium: 0, low: 0, info: 0 };
  for (const f of askable) if (f.severity in bySeverity) bySeverity[f.severity] += 1;
  return {
    lineCount: items.length,
    total: totalBilled(items),
    questionCount: askable.length,
    linesWithQuestions: linesWithQuestions.size,
    linesWithoutReference: noRef.size,
    bySeverity,
  };
}

// The text to show for a flag: the plain-language explanation when present, else reason.
export function flagText(flag) {
  const e = flag?.explanation;
  return e && String(e).trim() ? e : flag?.reason ?? "";
}

// Source line for a flag, or null when the flag cites no figure.
export function flagSource(flag) {
  if (!flag?.data_source) return null;
  return flag.data_year ? `${flag.data_source}, ${flag.data_year}` : flag.data_source;
}

// Flags worth putting in a coding-review letter (everything except "no reference").
export function letterFlags(flags) {
  return (flags || []).filter((f) => f.flag_type !== "no_reference_found");
}

export function findBannedPhrases(text) {
  const low = String(text || "").toLowerCase();
  return BANNED_PHRASES.filter((p) => low.includes(p));
}

// Read a File/Blob as base64 (without the data: prefix). DOM-free signature.
export function base64FromArrayBuffer(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

export const ACCEPTED_TYPES = ["application/pdf", "image/png", "image/jpeg", "image/webp", "image/gif", "text/plain"];
// 4 MB raw -> ~5.4 MB once base64-encoded, which stays under the 6 MB Lambda request cap.
export const MAX_UPLOAD_BYTES = 4 * 1024 * 1024;

export function checkUpload(file) {
  if (!file) return "Choose a file first.";
  const isTxt = /\.txt$/i.test(file.name || "");
  if (!ACCEPTED_TYPES.includes(file.type) && !isTxt) return "Please upload a PDF, an image (PNG, JPG, WEBP), or a .txt file.";
  if (file.size > MAX_UPLOAD_BYTES) return "That file is over 4 MB. Try a smaller scan or a photo.";
  return null;
}
