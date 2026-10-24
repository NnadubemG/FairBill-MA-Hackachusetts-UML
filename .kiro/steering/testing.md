---
inclusion: always
---

# Testing policy

Applies to `/core` and any other deterministic logic.

## Every check needs two kinds of tests
1. **Unit tests** — known input to known output. Cover the trigger case, the
   just-below-threshold case, and the empty case.
2. **Property-based tests (Hypothesis)** — invariants that must hold for *any* input.

## Required invariants for the checks engine
These must be asserted as property tests:

- **No banned words.** No flag's `reason` or `basis` contains any banned word from
  `product.md` (overcharged, illegal, fraud, incorrect charge, "you should dispute",
  "you are owed").
- **Numbers carry provenance.** Any flag whose `reason` or `basis` cites a price
  figure has non-empty `data_source` and `data_year`.
- **Empty bill, zero flags.** An empty list of line items produces zero flags.
- **Valid references.** Every flag's `line_item_id` refers to a real input line item.
- **Order independence.** Shuffling the input line items does not change the set of
  flags produced.
- **Determinism.** Running a check twice on the same input yields identical output.
- **Fail safe.** When reference data for a code is absent, no price-comparison flag is
  produced for that code (the engine never guesses a number).

## Running tests
- Python: `pytest` from the repo root.
- Keep tests pure: no network, no file writes, no clock/random dependence.
