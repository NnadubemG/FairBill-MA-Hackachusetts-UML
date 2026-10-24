// Unit tests for the app's pure logic. Run: node --test frontend/app/tests/*.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  parseAmount, money, moneyOrDash, rowToLineItem, guessCodeSystem, validateRows,
  nextRowId, rowsFromExtraction, totalBilled, buildResultRows, summarize, flagText,
  flagSource, letterFlags, findBannedPhrases, esc, checkUpload, base64FromArrayBuffer,
  FLAG_TITLE, SEVERITY_LABEL, LETTER_TYPES, BANNED_PHRASES,
} from "../logic.mjs";

test("parseAmount handles $, commas, blanks, junk", () => {
  assert.equal(parseAmount("$1,234.50"), 1234.5);
  assert.equal(parseAmount(" 12 "), 12);
  assert.equal(parseAmount(""), null);
  assert.equal(parseAmount("abc"), null);
  assert.equal(parseAmount(null), null);
  assert.equal(parseAmount(7), 7);
  assert.equal(parseAmount(Infinity), null);
});

test("money never turns missing into 0", () => {
  assert.equal(money(null), null);
  assert.equal(money(undefined), null);
  assert.equal(moneyOrDash(null), "—");
  assert.equal(money(0), "$0.00");
  assert.equal(money(1628.595), "$1,628.60");
});

test("guessCodeSystem only tags unambiguous shapes", () => {
  assert.equal(guessCodeSystem("99213"), "CPT");
  assert.equal(guessCodeSystem("j1100"), "HCPCS");
  assert.equal(guessCodeSystem("120"), null);
  assert.equal(guessCodeSystem(""), null);
});

test("rowToLineItem builds a contract LineItem with nulls for blanks", () => {
  const li = rowToLineItem({ id: 3, description: " Office visit ", code: "99213", quantity: "", billed_amount: "$150", date_of_service: "" });
  assert.deepEqual(li, {
    id: "3", description: "Office visit", billed_amount: 150, code: "99213", code_system: "CPT",
    raw_description: null, quantity: null, unit: null, date_of_service: null,
  });
  const noCode = rowToLineItem({ id: "1", description: "x", code: " ", billed_amount: "1" });
  assert.equal(noCode.code, null);
  assert.equal(noCode.code_system, null);
});

test("rowToLineItem keeps an explicit code_system from extraction", () => {
  const li = rowToLineItem({ id: "1", description: "x", code: "120", code_system: "REV", billed_amount: "1" });
  assert.equal(li.code_system, "REV");
});

test("validateRows catches empty bill, missing fields, bad numbers", () => {
  assert.equal(validateRows([]).length, 1);
  const errs = validateRows([
    { id: "1", description: "", billed_amount: "" },
    { id: "2", description: "ok", billed_amount: "-5", quantity: "0" },
    { id: "3", description: "ok", billed_amount: "5", date_of_service: "03/01/2026" },
  ]);
  const fields = errs.map((e) => `${e.rowId}:${e.field}`).sort();
  assert.deepEqual(fields, ["1:billed_amount", "1:description", "2:billed_amount", "2:quantity", "3:date_of_service"]);
  assert.deepEqual(validateRows([{ id: "1", description: "ok", billed_amount: "5", quantity: "2" }]), []);
});

test("nextRowId picks the next integer", () => {
  assert.equal(nextRowId([]), "1");
  assert.equal(nextRowId([{ id: "2" }, { id: "7" }, { id: "x" }]), "8");
});

test("rowsFromExtraction carries needs_confirmation from the side channel", () => {
  const rows = rowsFromExtraction({
    line_items: [{ id: "1", description: "A", billed_amount: 5 }, { id: "2", description: "B", billed_amount: 6 }],
    line_confidence: [{ line_item_id: "2", confidence: "low", needs_confirmation: true }],
  });
  assert.equal(rows[0].needs_confirmation, false);
  assert.equal(rows[1].needs_confirmation, true);
  assert.equal(rows[1].confidence, "low");
});

test("totalBilled sums valid amounts and returns null when none", () => {
  assert.equal(totalBilled([{ billed_amount: "10.10" }, { billed_amount: "0.2" }, { billed_amount: "" }]), 10.3);
  assert.equal(totalBilled([{ billed_amount: "" }]), null);
});

const analysis = {
  line_items: [
    { id: "1", description: "Clean", billed_amount: 10, code: "85025" },
    { id: "2", description: "Pricey", billed_amount: 900, code: "99284" },
    { id: "3", description: "Unknown", billed_amount: 5, code: "Z9999" },
  ],
  flags: [
    { line_item_id: "2", flag_type: "price_outside_ma_range", severity: "medium", reason: "r1", basis: "b1", data_source: "S", data_year: 2026 },
    { line_item_id: "2", flag_type: "price_above_reference", severity: "high", reason: "r2", basis: "b2", data_source: "S", data_year: 2026, explanation: "plain" },
    { line_item_id: "3", flag_type: "no_reference_found", severity: "info", reason: "none", basis: "b3" },
  ],
  price_references: [{ code: "99284", medicare_price: 180, data_source: "S", data_year: 2026 }],
};

test("buildResultRows sorts flagged lines first and flags by severity", () => {
  const rows = buildResultRows(analysis);
  assert.equal(rows[0].item.id, "2");
  assert.equal(rows[0].flags[0].severity, "high");
  assert.equal(rows[0].reference.medicare_price, 180);
  assert.equal(rows.at(-1).item.id, "1");
  assert.equal(rows.at(-1).reference, null);
});

test("summarize counts askable flags separately from no-reference", () => {
  const s = summarize(analysis);
  assert.equal(s.lineCount, 3);
  assert.equal(s.total, 915);
  assert.equal(s.questionCount, 2);
  assert.equal(s.linesWithQuestions, 1);
  assert.equal(s.linesWithoutReference, 1);
});

test("flagText prefers explanation; flagSource cites only when present", () => {
  assert.equal(flagText(analysis.flags[1]), "plain");
  assert.equal(flagText(analysis.flags[0]), "r1");
  assert.equal(flagSource(analysis.flags[0]), "S, 2026");
  assert.equal(flagSource(analysis.flags[2]), null);
});

test("letterFlags drops no_reference_found", () => {
  assert.equal(letterFlags(analysis.flags).length, 2);
});

test("esc neutralizes HTML from untrusted bill text", () => {
  assert.equal(esc(`<img src=x onerror="a">'`), "&lt;img src=x onerror=&quot;a&quot;&gt;&#39;");
  assert.equal(esc(null), "");
});

test("checkUpload enforces type and size", () => {
  assert.match(checkUpload(null), /Choose/);
  assert.match(checkUpload({ type: "text/plain", size: 10 }), /PDF/);
  assert.match(checkUpload({ type: "application/pdf", size: 5 * 1024 * 1024 }), /4 MB/);
  assert.equal(checkUpload({ type: "image/png", size: 1000 }), null);
});

test("base64FromArrayBuffer round-trips", () => {
  const bytes = new TextEncoder().encode("hello bill");
  assert.equal(Buffer.from(base64FromArrayBuffer(bytes.buffer), "base64").toString(), "hello bill");
});

test("no banned phrase appears in any UI copy", () => {
  const copy = [
    ...Object.values(FLAG_TITLE), ...Object.values(SEVERITY_LABEL),
    ...LETTER_TYPES.flatMap((t) => [t.title, t.blurb]),
    readFileSync(new URL("../main.mjs", import.meta.url), "utf8"),
    readFileSync(new URL("../../index.html", import.meta.url), "utf8"),
  ].join("\n");
  // logic.mjs itself lists the phrases, so it is checked via the derived strings above.
  assert.deepEqual(findBannedPhrases(copy), []);
  assert.equal(BANNED_PHRASES.length, 6);
});
