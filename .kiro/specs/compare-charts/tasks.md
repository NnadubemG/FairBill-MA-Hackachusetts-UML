# Compare Charts — Tasks

Vanilla ES modules, no build, no deps. Pure modules tested with `node --test`.
Files only under `/frontend/src/compare`.

- [x] 1. scale.mjs + test
  - Pure `makeScale(dMin,dMax,rMin,rMax)`; collapse when dMin==dMax; clamp; monotonic.
  - Test V9.
  - _Requirements: R5.4, R6.1_

- [x] 2. viewmodel.mjs + sample.json + tests
  - `toViewModel(result, payerGroup)` -> rows/medicare/summary/availableGroups/domain/note.
  - Bundled `sample.json` (matches compare API output: 2 hospitals, medicare, cash).
  - Tests V1, V2, V3, V4, V5, V6, V7 + fabrication guard.
  - _Requirements: R1, R2, R3, R4, R6_

- [x] 3. render.mjs + tests
  - `renderSVG(vm)` (role=img, aria-label, bars, median shape marker, medicare dashed line
    + label, "no data" text) and `renderTable(vm)` (data-table alternative).
  - Tests V1 (bars), V2 (medicare line), V4 (single marker), V7 (empty), V8 (aria + table).
  - _Requirements: R1, R2, R5_

- [x] 4. api.mjs + compare.mjs + styles.css
  - `fetchProcedures/fetchCompare`; `mountCompare(el, result)` with state + payer toggle +
    re-render; real focusable buttons; focus-visible styles; shape/stroke (not color-only).
  - _Requirements: R3.3, R5.2_

- [x] 5. index.html harness (live API + sample fallback) + README
  - Standalone page: try the API, fall back to sample.json, banner shows source.
  - _Requirements: D2; viewable today._

- [x] 6. Run tests + capture rendered output
  - `node --test "frontend/src/compare/tests/*.test.mjs"` -> 19 pass. Rendered sample to an
    SVG snapshot (reviewed) confirming bars, median ticks, medicare line, labels.
  - _Verification._
