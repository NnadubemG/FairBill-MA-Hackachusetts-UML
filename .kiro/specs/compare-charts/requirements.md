# Compare Charts — Requirements

## Overview

A Compare page component that visualizes, for a selected procedure code, each hospital's
price range by payer group, with the Medicare reference and a plain-language summary. It
calls the compare API (`GET /procedures`, `GET /compare?code=XXXXX`) built in the compare
spec and renders the response.

This is the third ND deliverable (pipeline + compare API done). Scoped to
`/frontend/src/compare` only.

## Decisions (resolved)

- **D1 stack.** No front-end framework exists in the repo and `team.md` makes the rest of
  `/frontend` David's. So: a dependency-free **vanilla ES module + SVG** in
  `/frontend/src/compare`. No `package.json`, no build step, no new dependencies. David can
  mount the same module in whatever framework he picks later.
- **D2 viewability.** A standalone `index.html` harness in `/frontend/src/compare` renders
  the component. It tries the live API first and falls back to a bundled sample JSON, so it
  always shows something in a demo even with no server running.
- **D3 charting.** Hand-drawn SVG (no chart library). Accessible by construction.

## Requirements

### R1. Range chart per hospital
- **R1.1** For the selected code, render one horizontal row per hospital that has data for
  the active payer group: a bar from that hospital's `min_rate` to `max_rate`, with a
  distinct marker at `median_rate`.
- **R1.2** Rows are labeled with the hospital name (text, not color).
- **R1.3** A hospital missing a value for the active payer group shows a clear "no data"
  state for that row, not a zero-length bar or a guessed value.

### R2. Medicare reference line
- **R2.1** When `medicare.medicare_price` is present, draw a vertical reference line across
  the chart at that value, with a visible text label (e.g. "Medicare $92").
- **R2.2** When absent, omit the line and note "no Medicare reference" in the summary.

### R3. Payer-group toggle
- **R3.1** A control lets the user switch the active payer group among those present
  (commercial, Medicare Advantage, Medicaid managed, cash). Gross is shown as context, not
  a default view.
- **R3.2** For `cash`, bars may be a single point (cash_price) rather than a min–max range;
  render a clear single-value marker.
- **R3.3** Switching the toggle re-renders the chart for that group without a full reload.

### R4. Plain-language summary line
- **R4.1** Above the chart, a one-line summary in the approved voice, e.g. "Commercial
  rates for this service range from $X to $Y across N Massachusetts hospitals in this data."
- **R4.2** No banned word (overcharged, illegal, fraud, incorrect charge, "you should
  dispute", "you are owed"). It describes, it does not accuse.
- **R4.3** The API's `framing_note` is displayed near the chart.

### R5. Accessibility (hard requirement)
- **R5.1** Do not rely on color alone: every bar/marker/line also has a text label or
  value, and differences are conveyed by position/shape/text.
- **R5.2** Keyboard: the payer toggle and each hospital row are focusable and operable by
  keyboard; visible focus outline.
- **R5.3** The chart has a text alternative: an `aria-label`/`role` on the SVG and an
  accompanying data table (or `aria` description) so a screen reader conveys the same values.
- **R5.4** Numbers shown always carry their meaning (min/median/max labeled), and every
  figure originates from the API (never computed/guessed in the UI).

### R6. Data handling
- **R6.1** Never fabricate a value. A `null` from the API renders as "no data", not `0`.
- **R6.2** Unknown code (`found: false`) renders a friendly empty state with the not-found
  note, not an error.
- **R6.3** The component is given data (dependency-injected) so its rendering is unit
  testable without a network call.

### R7. Boundaries
- **R7.1** Only files under `/frontend/src/compare`. Do not touch David's `/frontend`
  elsewhere, `/infra`, or `/contracts`.
- **R7.2** No new dependency. Vanilla JS + SVG + the stdlib compare API.

## Test cases (named; detailed in design before tasks)
- **V1 range bars**: given a compare result, the renderer produces one row per hospital for
  the active group with min/median/max positioned correctly (assert via computed geometry
  helper, pure).
- **V2 medicare line**: present -> line + label; absent -> no line, summary notes it.
- **V3 payer toggle**: switching group changes which hospitals/rows are produced.
- **V4 cash single value**: cash group renders a single-value marker, not a range.
- **V5 no data row**: hospital lacking the active group -> "no data" state, no zero bar.
- **V6 summary text**: correct range/count text; contains no banned word.
- **V7 unknown code**: `found:false` -> empty state with note, no throw.
- **V8 accessibility hooks**: output includes aria-label on the chart, a data-table
  alternative, and focusable controls (assert presence in generated DOM/markup string).
- **V9 scale/geometry**: pure scale function maps value->x within bounds; min<=median<=max
  stays ordered on screen; handles equal min==max.

## Out of scope
- A full app shell, routing, deployment (David). Only the Compare component + its harness.
- Changing the compare API or contracts.
