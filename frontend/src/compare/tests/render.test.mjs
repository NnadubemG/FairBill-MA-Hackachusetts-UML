// V1 (bars), V4 (single marker), V8 (aria + table). node --test.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { toViewModel } from "../viewmodel.mjs";
import { renderSVG, renderTable } from "../render.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const SAMPLE = JSON.parse(readFileSync(join(here, "..", "sample.json"), "utf-8"));

test("V1 renderSVG draws one range bar + median tick per hospital", () => {
  const svg = renderSVG(toViewModel(SAMPLE, "commercial"));
  const bars = (svg.match(/class="range-bar"/g) || []).length;
  const ticks = (svg.match(/class="median-tick"/g) || []).length;
  assert.equal(bars, 2);
  assert.equal(ticks, 2);
});

test("V2 renderSVG includes medicare line + label", () => {
  const svg = renderSVG(toViewModel(SAMPLE, "commercial"));
  assert.ok(svg.includes('class="medicare-line"'));
  assert.ok(svg.includes("Medicare"));
});

test("V4 cash renders a single-value marker, no range bar", () => {
  const svg = renderSVG(toViewModel(SAMPLE, "cash"));
  assert.ok(svg.includes('class="single-marker"'));
  assert.equal((svg.match(/class="range-bar"/g) || []).length, 0);
});

test("V8 accessibility: svg role=img + non-empty aria-label", () => {
  const svg = renderSVG(toViewModel(SAMPLE, "commercial"));
  assert.ok(svg.includes('role="img"'));
  const m = svg.match(/aria-label="([^"]+)"/);
  assert.ok(m && m[1].length > 0);
});

test("V8 data table alternative has header + one row per hospital", () => {
  const html = renderTable(toViewModel(SAMPLE, "commercial"));
  assert.ok(html.includes("<table"));
  assert.ok(html.includes("<caption>"));
  // 2 hospitals + medicare reference row + statewide MA gross range row = 4
  const rowHeaders = (html.match(/<th scope="row">/g) || []).length;
  assert.equal(rowHeaders, 4);
});

test("MA range band + label render in SVG and table", () => {
  const vm = toViewModel(SAMPLE, "commercial");
  const svg = renderSVG(vm);
  assert.ok(svg.includes('class="ma-band"'));
  assert.ok(svg.includes("MA gross"));
  assert.ok(svg.includes("maHatch")); // hatch pattern = non-color-only cue
  const html = renderTable(vm);
  assert.ok(html.includes("Statewide MA gross range"));
});

test("V7 unknown code renders empty SVG without throwing", () => {
  const vm = toViewModel(
    { code: "00000", found: false, hospitals: [], medicare: null,
      note: "Code not found.", framing_note: "" },
    "commercial"
  );
  const svg = renderSVG(vm);
  assert.ok(svg.includes("<svg"));
  assert.ok(svg.includes("Code not found."));
});
