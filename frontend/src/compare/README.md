# Compare page component (`/frontend/src/compare`)

Dependency-free, accessible price-comparison chart for a procedure code. Vanilla ES
modules + SVG. No framework, no build step, no `package.json`. Designed to be mounted into
David's app later, or viewed standalone via `index.html`.

## Files
- `scale.mjs` — pure value→pixel linear scale (collapse + clamp).
- `viewmodel.mjs` — pure: compare API result + payer group → render-ready view model.
- `render.mjs` — pure: view model → accessible SVG string + data-table alternative.
- `compare.mjs` — component wiring: state, payer toggle, re-render. `mountCompare(el, result)`.
- `api.mjs` — `fetchProcedures` / `fetchCompare` against the compare API.
- `styles.css` — focus-visible outlines; shape/stroke cues so meaning isn't color-only.
- `index.html` — standalone harness: tries the live API, falls back to `sample.json`.
- `sample.json` — a sample compare response (matches the compare API output shape).

## View it
Static files, so serve the folder and open `index.html`:

```
# from repo root
python -m http.server 5500 --directory frontend/src/compare
# then open http://127.0.0.1:5500/index.html
```

For live data, also run the compare API in another terminal:

```
python -m backend.compare.server --port 8000 --data data/processed
```

If the API isn't reachable, the page falls back to `sample.json` so it always renders.

## Test
Pure modules are covered by Node's built-in runner (no npm):

```
node --test "frontend/src/compare/tests/*.test.mjs"
```

## Accessibility
- No color-only encoding: median = solid tick, medicare = dashed line, single value =
  diamond; every mark has a text value.
- SVG has `role="img"` + an `aria-label` summary; a parallel data table carries the same
  numbers for screen readers.
- Payer toggle is real focusable buttons; focus-visible outline.
- Figures come only from the API; a `null` renders as "no data", never `0`.
