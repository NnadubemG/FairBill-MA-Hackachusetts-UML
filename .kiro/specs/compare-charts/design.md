# Compare Charts — Design

## Goals and constraints

- Vanilla ES module + SVG. No framework, no build, no new dependency. Files only under
  `/frontend/src/compare`.
- Pure rendering logic (data -> view model -> SVG/DOM string) so it unit-tests with
  Node's built-in test runner (`node --test`), no browser and no npm install.
- Accessible by construction: text labels on every mark, data-table alternative, keyboard
  focus, aria-label; never color-only.
- Never fabricate: API `null` -> "no data". Unknown code -> friendly empty state.

## Directory layout

```
/frontend/src/compare
  scale.js         # pure: makeScale(domainMin,domainMax,rangeMin,rangeMax) -> x(value)
  viewmodel.js     # pure: toViewModel(compareResult, payerGroup) -> rows, medicare, summary
  render.js        # pure-ish: renderSVG(vm) + renderTable(vm) -> markup strings; renderInto(el,...)
  api.js           # fetchProcedures(), fetchCompare(code) against the compare API
  compare.js       # component wiring: state (code, payerGroup), events, re-render
  styles.css       # focus outlines, patterns (not color-only), layout
  index.html       # standalone harness: live API with sample-data fallback
  sample.json      # bundled sample compare result (for offline demo + tests)
  tests/
    *.test.mjs     # node --test, import the pure modules
  README.md        # how to view it
```

## Pure core (testable without a browser)

### scale.js
```
makeScale(domainMin, domainMax, rangeMin, rangeMax) -> (value) => x
```
- Linear map. When domainMin == domainMax, returns rangeMin (avoid divide-by-zero; a
  single-value bar collapses to a point). Clamps output to [rangeMin, rangeMax].

### viewmodel.js
`toViewModel(result, payerGroup)` returns a plain object the renderer consumes:
```
{
  found: bool,
  code, plainLabel,
  payerGroup,
  availableGroups: [...],            # groups present across hospitals (for the toggle)
  domain: {min, max},                # overall min..max across rows + medicare, for scaling
  rows: [
    { hospitalId, name,
      kind: "range" | "single" | "none",
      min, median, max,              # for range
      value,                         # for single (cash)
      text }                         # e.g. "$100–$200, median $150" or "no data"
  ],
  medicare: { price, label } | null,
  summary: "…plain language…",       # banned-word free
  framingNote,
  note                               # not-found / empty note, else null
}
```
Rules:
- `kind: "none"` when the hospital has no usable figure for the active group.
- `single` for cash (uses cash_price); `range` for negotiated groups (min/median/max).
- `domain.max` includes the medicare price so the reference line fits on scale.
- `summary` built from counts + min/max of the active group; if nothing, say so plainly.
- Unknown result (`found:false`) -> `rows: []`, `note` set, summary neutral.

### render.js
- `renderSVG(vm)` returns an `<svg role="img" aria-label="…">` string: one `<g>` per row
  with a `<rect>` bar, a median tick (different **shape**, not just color), a right-aligned
  value `<text>`, and the hospital name `<text>` label. Medicare drawn as a vertical
  `<line>` plus `<text>` "Medicare $X". "none" rows render a muted "no data" `<text>`.
- `renderTable(vm)` returns an HTML `<table>` with the same numbers (the screen-reader and
  no-color alternative). Columns: Hospital, Min, Median, Max / Cash, vs Medicare.
- Both are pure string builders. `renderInto(el, vm)` sets innerHTML + wires focus order.
- Patterns/shape encode the median marker and medicare line so meaning survives without
  color (R5.1).

## Component wiring (compare.js)
- State: `{ code, payerGroup }`. On mount: fetch procedures (for the picker) and the
  initial compare; build vm; render. Toggle/picker events update state and re-render only.
- Keyboard: toggle is a real `<button>` group (focusable, arrow/enter operable); rows are
  `tabindex=0` with `aria-label` summarizing the row.

## api.js + harness
- `api.js`: `fetchCompare(code, baseUrl)` / `fetchProcedures(baseUrl)` using `fetch`.
- `index.html`: tries `http://127.0.0.1:8000`; on failure (no server) loads `sample.json`
  so the page always renders. A small banner shows which source is in use.

## Accessibility specifics
- SVG: `role="img"`, `aria-label` = the summary; decorative sub-parts `aria-hidden`.
- Data table duplicates every value (R5.3) and is always in the DOM (can be visually
  styled compact but present for AT).
- Focus-visible outline in `styles.css`; median marker is a diamond/tick shape; medicare
  line is dashed — shape/stroke differences, not color alone.

## Test cases (before tasks) — `node --test`, importing pure modules
- **V9 scale**: `makeScale(0,100,0,200)(50)==100`; `makeScale(5,5,0,200)(5)==0` (collapse);
  clamps out-of-range; monotonic so min<=median<=max stays ordered.
- **V1 range bars**: vm from a 2-hospital commercial result -> 2 "range" rows with correct
  min/median/max; renderSVG contains 2 bars and 2 median ticks.
- **V2 medicare line**: medicare present -> vm.medicare set, renderSVG has the line + label;
  absent -> vm.medicare null, summary mentions no Medicare reference.
- **V3 payer toggle**: same result, payerGroup "cash" vs "commercial" -> different rows;
  availableGroups lists both.
- **V4 cash single value**: cash group -> row kind "single", renderSVG draws a point marker,
  no min–max bar.
- **V5 no data row**: hospital without the active group -> kind "none", text "no data",
  no `<rect>` width > 0 for it.
- **V6 summary text**: expected "range from $X to $Y across N …" text; assert no banned word.
- **V7 unknown code**: `found:false` -> vm.note set, rows empty, renderSVG/table render an
  empty state without throwing.
- **V8 accessibility hooks**: renderSVG has `role="img"` + non-empty `aria-label`;
  renderTable produces a `<table>` with a header row and one row per hospital.

## Notes carried into tasks
- Keep scale/viewmodel/render pure and import-only so tests need no DOM.
- Banned-word list mirrored from product.md in the summary test.
- No npm. Tests run with `node --test frontend/src/compare/tests`.
