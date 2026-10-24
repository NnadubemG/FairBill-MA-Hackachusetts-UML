# Implementation Plan: /core checks v2 (quantity and unbundling)

## Overview

Add the contracts, then the two checks, then extend the synthetic generator so ground truth covers them.
Each finished piece is merged into `main` after pulling `main` and running the full suite.

Requirements are in `requirements.md`. Test cases (TQ, TU, TE, TS-N) and properties (PQ) are in `design.md`.

## Tasks

- [x] 1. Contracts
  - Add `contracts/quantity-limit.schema.json` and `contracts/bundle-pair.schema.json`, mirrors in `types.ts` and `types.py`, README rows.
  - Extend `synthetic-bill.schema.json` and mirrors (optional `quantity_limits`, `bundle_pairs`; scenarios `quantity`, `unbundling`).
  - _Requirements: 5.1, 5.2_

- [x] 2. Quantity check
  - Move `has_provenance` to `core/reference.py`; let `ReferenceIndex` take any keyed record.
  - `core/checks/quantity.py`, templates in `language.py`, engine wiring.
  - Tests TQ1 to TQ9.
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

- [x] 3. Unbundling check
  - `core/dates.py` (moved from `duplicates.py`), `core/checks/unbundling.py`, templates, engine wiring.
  - Tests TU1 to TU9, TE1, TE2.
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

- [ ] 4. Properties
  - Hypothesis tests PQ1 to PQ7.
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [ ] 5. Synthetic ground truth
  - `unbundle_only` catalog entry (93005), quantity limits and a bundle pair, scenarios `quantity` and `unbundling`, bills carry limits and pairs, regenerate samples.
  - Tests TS-N1 to TS-N5 and PQ8.
  - _Requirements: 5.2, 5.3_

- [ ] 6. Wrap-up
  - Log lines in `docs/kiro-log.md`; confirm `/core` is still pure.

## Task Dependency Graph

Tasks 2 and 3 both edit `engine.py` and `language.py`, so they run in order.

```mermaid
graph LR
    T1[1. Contracts] --> T2[2. Quantity check]
    T2 --> T3[3. Unbundling check]
    T3 --> T4[4. Properties]
    T4 --> T5[5. Synthetic ground truth]
    T5 --> T6[6. Wrap-up]
```

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2"] },
    { "id": 2, "tasks": ["3"] },
    { "id": 3, "tasks": ["4"] },
    { "id": 4, "tasks": ["5"] },
    { "id": 5, "tasks": ["6"] }
  ]
}
```

## Notes

- `/core` stays pure. No new dependencies.
- New contract fields are optional and the new `analyze` arguments are keyword-only, so existing callers are unaffected.
- ND's pipeline must produce `QuantityLimit` and `BundlePair` data; until then `/core` runs with none, like v1.
- Merge each piece into `main` after fetching `origin/main`, and fix any conflicts first.
