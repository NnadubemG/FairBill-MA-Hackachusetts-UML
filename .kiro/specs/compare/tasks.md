# Compare API — Tasks

Small tasks. stdlib only. Pure service functions tested without a server. Reuses
`pipeline.jsonio` and `pipeline.aggregate.summarize`.

- [x] 1. Package scaffolding + framing note
  - Create `/backend/compare` package, `framing.py` (FRAMING_NOTE, banned-word-free),
    tests dir + fixtures dir.
  - Test: FRAMING_NOTE contains no banned word (C5 part).
  - _Requirements: R5_

- [x] 2. Store (load + index processed JSON)
  - `store.py`: `Store` with indexes; `Store.load(processed_dir)` and
    `Store.from_dicts(...)`; missing file -> empty index.
  - Fixtures: tiny processed JSON (2 hospitals, 2 codes) + medicare + chia.
  - Tests: C9 (load from disk, missing file tolerated).
  - _Requirements: R6.1, R6.3_

- [x] 3. list_procedures service
  - `service.py`: `list_procedures(store)` -> procedures in code order + framing_note.
  - Tests: order stable; framing_note present (C5 part).
  - _Requirements: R1, R5_

- [x] 4. compare service — core
  - `compare(store, code)`: normalize code, known-code path (per-hospital grouping,
    medicare, chia), framing_note. Hospitals sorted; payer groups fixed order.
  - Tests: C1 (known code), C6 (no medicare).
  - _Requirements: R2.1, R4.1, R4.3, R6.2_

- [x] 5. compare service — statewide + missing notes + unknown code
  - Add statewide via `aggregate.summarize` over commercial medians; `missing_note` for
    partial hospitals; unknown-code not-found shape (D2).
  - Tests: C2 (unknown), C3 (partial), C4 (cash-only), C8 (statewide), C7 (determinism).
  - _Requirements: R2.2, R3, R4.2, R5_

- [x] 6. server.py (thin stdlib adapter)
  - `http.server` handler: GET /procedures, GET /compare?code=…; missing code -> 400;
    unknown route -> 404. Loads Store once. No request logging. CLI entry point.
  - Test: C10 (in-process smoke: 200s, 400, 404).
  - _Requirements: R2, R7.1_

- [x] 7. Local run + sample output
  - Ran the service against the fixtures and captured a sample /compare response
    confirming the data shape (per-hospital payer grouping, medicare, chia, statewide,
    framing note). No real /data/processed needed.
  - _Makes the work viewable today._
