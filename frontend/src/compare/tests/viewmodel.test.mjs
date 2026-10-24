// V1-V7 at the view-model level. node --test.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { toViewModel, availableGroups } from "../viewmodel.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const SAMPLE = JSON.parse(readFileSync(join(here, "..", "sample.json"), "utf-8"));

const BANNED = ["overcharged", "illegal", "fraud", "incorrect charge",
  "you should dispute", "you are owed"];

test("V1 range rows for commercial", () => {
  const vm = toViewModel(SAMPLE, "commercial");
  assert.equal(vm.rows.length, 2);
  const mgh = vm.rows.find((r) => r.hospitalId === "mgh");
  assert.equal(mgh.kind, "range");
  assert.equal(mgh.min, 100);
  assert.equal(mgh.median, 150);
  assert.equal(mgh.max, 200);
});

test("V2 medicare present -> vm.medicare set; domain includes it", () => {
  const vm = toViewModel(SAMPLE, "commercial");
  assert.ok(vm.medicare);
  assert.equal(vm.medicare.price, 92.47);
  assert.ok(vm.summary.includes("Medicare"));
  assert.ok(vm.domain.max >= 240); // spans the hospital max
});

test("V2 medicare absent -> null and summary notes it", () => {
  const noMed = { ...SAMPLE, medicare: null };
  const vm = toViewModel(noMed, "commercial");
  assert.equal(vm.medicare, null);
  assert.ok(vm.summary.toLowerCase().includes("no medicare"));
});

test("V3 payer toggle changes rows; availableGroups lists both", () => {
  assert.deepEqual(availableGroups(SAMPLE), ["commercial", "cash"]);
  const cash = toViewModel(SAMPLE, "cash");
  // Only mgh has cash; bmc has none for cash.
  const mgh = cash.rows.find((r) => r.hospitalId === "mgh");
  const bmc = cash.rows.find((r) => r.hospitalId === "bmc");
  assert.equal(mgh.kind, "single");
  assert.equal(bmc.kind, "none");
});

test("V4 cash single value", () => {
  const vm = toViewModel(SAMPLE, "cash");
  const mgh = vm.rows.find((r) => r.hospitalId === "mgh");
  assert.equal(mgh.kind, "single");
  assert.equal(mgh.value, 95);
});

test("V5 no-data row has kind none and no numeric bar", () => {
  const vm = toViewModel(SAMPLE, "cash");
  const bmc = vm.rows.find((r) => r.hospitalId === "bmc");
  assert.equal(bmc.kind, "none");
  assert.equal(bmc.min, undefined);
});

test("V6 summary text + no banned words", () => {
  const vm = toViewModel(SAMPLE, "commercial");
  assert.ok(/range from \$100 to \$240 across 2/.test(vm.summary));
  const low = vm.summary.toLowerCase();
  for (const w of BANNED) assert.ok(!low.includes(w), `summary contains banned: ${w}`);
});

test("V7 unknown code -> empty state, no throw", () => {
  const notFound = { code: "00000", found: false, hospitals: [], medicare: null,
    statewide: { min: null, median: null, max: null }, data_years: [],
    note: "Code not found in the curated list.",
    framing_note: SAMPLE.framing_note };
  const vm = toViewModel(notFound, "commercial");
  assert.equal(vm.found, false);
  assert.equal(vm.rows.length, 0);
  assert.ok(vm.note);
});

test("fabrication guard: null figure never becomes 0", () => {
  const vm = toViewModel(SAMPLE, "cash");
  const bmc = vm.rows.find((r) => r.hospitalId === "bmc");
  assert.notEqual(bmc.value, 0);
  assert.equal(bmc.kind, "none");
});

test("MA range surfaced from statewide; domain includes it; summary mentions it", () => {
  const vm = toViewModel(SAMPLE, "commercial");
  assert.ok(vm.maRange);
  assert.equal(vm.maRange.low, 420);
  assert.equal(vm.maRange.high, 980);
  assert.ok(vm.domain.max >= 980); // band fits on scale
  assert.ok(vm.summary.includes("Statewide MA gross charges span"));
});

test("MA range falls back to reference when statewide lacks it", () => {
  const r = JSON.parse(JSON.stringify(SAMPLE));
  delete r.statewide.ma_range_low;
  delete r.statewide.ma_range_high;
  const vm = toViewModel(r, "commercial");
  assert.equal(vm.maRange.low, 420); // from reference record
});

test("no MA range anywhere -> maRange null, never fabricated", () => {
  const r = JSON.parse(JSON.stringify(SAMPLE));
  r.reference = null;
  r.statewide = { min: null, median: null, max: null, ma_range_low: null, ma_range_high: null };
  const vm = toViewModel(r, "commercial");
  assert.equal(vm.maRange, null);
});
