// V9: pure scale function. Run with: node --test frontend/src/compare/tests
import test from "node:test";
import assert from "node:assert/strict";
import { makeScale } from "../scale.mjs";

test("V9 linear mapping", () => {
  const x = makeScale(0, 100, 0, 200);
  assert.equal(x(0), 0);
  assert.equal(x(50), 100);
  assert.equal(x(100), 200);
});

test("V9 collapse when domainMin == domainMax", () => {
  const x = makeScale(5, 5, 0, 200);
  assert.equal(x(5), 0); // point at rangeMin, no divide-by-zero
});

test("V9 clamps out-of-domain values", () => {
  const x = makeScale(0, 100, 0, 200);
  assert.equal(x(-50), 0);
  assert.equal(x(150), 200);
});

test("V9 monotonic keeps min<=median<=max ordered on screen", () => {
  const x = makeScale(100, 300, 40, 440);
  const lo = x(100), med = x(200), hi = x(300);
  assert.ok(lo <= med && med <= hi);
});
