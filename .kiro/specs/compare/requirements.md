# Compare API — Requirements

## Overview

`/backend/compare` is a small, read-only lookup service over the processed JSON bundles
the pipeline produces in `/data/processed`. It powers the Compare page: for a procedure
code, it returns each hospital's price statistics by payer group, the Medicare reference,
the CHIA tier, and statewide min/median/max — with clear nulls where data is missing.

It reads the committed JSON only. No database. No writes. No network calls out. Responses
are small (a few KB). It never fabricates a missing value; it returns `null`.

This is the second of three ND deliverables (pipeline done; charts next). One spec this
session: the compare/lookup service. The charts are a separate spec.

## Ownership / boundaries

- Owned by ND (`/backend/compare`). Reads `/data/processed/*.json` (produced by the
  pipeline). The processed shapes are fixed by `/contracts` (`PriceStat`, `ProcedureInfo`,
  `PriceReference`) plus the internal `hospitals.json` / `chia_tiers.json` shapes.
- Does not edit `/contracts`. Does not read `/data/raw`. Does not persist anything.

## Endpoints

### R1. GET /procedures
- **R1.1** Returns the curated procedure list as an array of `ProcedureInfo`
  (`code`, `code_system`, `plain_label`, `category`, `typical_max_units`).
- **R1.2** Sourced directly from `procedures.json`. Order is stable (by `code`).
- **R1.3** Includes the `framing_note` (see R5) at the top level of the response object.

### R2. GET /compare?code=XXXXX
- **R2.1** For the given `code`, returns a `CompareResult` containing:
  - `code`, `code_system`, `plain_label` (from `procedures.json`)
  - `hospitals`: one entry per hospital that has any `PriceStat` for this code, each with:
    - `hospital_id`, `name`, `city`, `type` (from `hospitals.json`)
    - `price_stats`: the `PriceStat` records for this hospital+code, keyed/grouped by
      payer group (`commercial`, `medicare_advantage`, `medicaid_managed`, `cash`, `gross`)
    - `chia_tier`: the hospital's CHIA tier record, or `null` if none
    - `missing_note`: a short string when this hospital has partial data (see R4)
  - `medicare`: the `PriceReference` for this code, or `null` if none
  - `statewide`: `{min, median, max}` computed across hospitals' commercial `median_rate`
    values for this code (see R3), each nullable
  - `data_years`: the set of `data_year` values present in the response, for display
  - `framing_note` (see R5)
- **R2.2** Unknown code (not in `procedures.json`): return a well-formed `CompareResult`
  with empty `hospitals`, `null` medicare, null statewide, and a clear top-level note that
  the code was not found. HTTP 200 (not an error) so the UI can render a friendly state.
  (Open question Q1 below — confirm 200 vs 404.)

### R3. Statewide aggregation
- **R3.1** `statewide.min/median/max` are computed over the set of each hospital's
  **commercial** `median_rate` for this code (one representative value per hospital).
- **R3.2** If fewer than one hospital has a commercial median, statewide values are `null`
  (never guessed).
- **R3.3** Aggregation reuses the pipeline's `aggregate.summarize` so the min<=median<=max
  invariant holds and behavior matches the rest of the system.

### R4. Missing data is explicit
- **R4.1** Never fabricate a value. Any absent figure is `null`.
- **R4.2** When a hospital has some but not all payer groups (e.g. cash-only), set
  `missing_note` to a short, neutral string naming what is absent (e.g. "no commercial
  negotiated rates in the source files").
- **R4.3** When a hospital has no data for the code, it simply does not appear in
  `hospitals` (absence, not a placeholder row).

### R5. Framing note (hard requirement)
- **R5.1** Every response includes `framing_note`: a one-line reminder that prices come
  from public files and an individual's actual cost depends on their plan.
- **R5.2** The note uses the approved voice. It contains no banned word from `product.md`
  (overcharged, illegal, fraud, incorrect charge, "you should dispute", "you are owed").

### R6. Read-only, pure-ish, deterministic
- **R6.1** The service only reads `/data/processed` JSON bundled with the backend. No DB,
  no writes, no outbound network.
- **R6.2** For the same processed data, the same request yields the same response
  (stable ordering, stable aggregation).
- **R6.3** Data loading is separated from request handling so the lookup logic is unit
  testable without a running server (pure functions over loaded dicts).

### R7. Safety / privacy
- **R7.1** No request body or query value is logged. (Codes are low-risk, but we keep the
  no-logging posture from steering.)
- **R7.2** All strings served originate from processed files (themselves derived from
  public data); none are treated as instructions.

## Test cases (named here; fleshed out in design before tasks)
- **C1 known code**: a code present for multiple hospitals -> correct per-hospital
  grouping, medicare reference attached, statewide computed.
- **C2 unknown code**: not in procedures.json -> empty hospitals, null medicare/statewide,
  not-found note, well-formed result.
- **C3 hospital with partial data**: a hospital with only gross/cash -> appears with those
  fields populated, others null, `missing_note` set.
- **C4 cash-only data**: a hospital with only cash -> cash populated, commercial absent,
  statewide unaffected by that hospital.
- **C5 framing_note present**: on both endpoints, and contains no banned word.
- **C6 no medicare reference**: code with no medicare.json entry -> medicare null, rest ok.
- **C7 determinism**: same data, same request, byte-identical response.

## Decisions (resolved)
- **D1 framework.** Python stdlib only (`http.server`). No new dependency. The lookup is a
  set of pure handler functions over loaded JSON; a thin stdlib server exposes them for
  local viewing and drops into David's Lambda later unchanged.
- **D2 unknown-code status.** HTTP 200 with a well-formed empty result + a not-found note,
  so the UI renders a friendly state instead of handling an error.

## Out of scope (this spec)
- The Compare page UI / charts (`/frontend/src/compare`) — separate spec.
- Generating the processed data (pipeline — done).
- Auth, rate limiting, deployment (David's infra).
