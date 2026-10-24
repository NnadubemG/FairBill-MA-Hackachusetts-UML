# Pipeline — Requirements

## Overview

`/pipeline` is a set of pure Python 3.12 scripts that turn large, messy, public raw
data (hospital price transparency files, CMS Physician Fee Schedule, NCCI edits, CHIA
relative price data) into small, committed JSON bundles under `/data/processed` that the
backend serves to the app.

Raw inputs live in `/data/raw` (gitignored, large). The pipeline **streams and filters
to our curated procedure codes while reading** so it never holds a whole raw file in
memory. Processed outputs are small and committed.

This spec covers only the data pipeline. The compare/lookup endpoint and the charts are
separate specs for later sessions.

## Proposed contract additions (pending Thomas sign-off)

The pipeline's outputs need two types that do not exist in `/contracts` yet. `/contracts`
is owned by Thomas and JSON Schema is the source of truth, so these are proposed as
**additive** schemas (no change to existing schemas) and must be announced to Thomas
before merge. They are written as the first implementation task.

### PriceStat
One statistics record for a given hospital + procedure code + payer group.

| Field | Type | Notes |
| --- | --- | --- |
| `hospital_id` | string | FK to `hospitals.json`. Required. |
| `code` | string | Procedure code. Required. Must be in `procedures.json`. |
| `code_system` | enum/null | `CPT` \| `HCPCS` \| `DRG` \| `REV` \| `ICD10` \| `OTHER` \| null |
| `payer_group` | enum | `commercial` \| `medicare_advantage` \| `medicaid_managed` \| `cash` \| `gross`. Required. |
| `min_rate` | number/null | Min negotiated rate in USD, or null. |
| `median_rate` | number/null | Median negotiated rate in USD, or null. |
| `max_rate` | number/null | Max negotiated rate in USD, or null. |
| `cash_price` | number/null | Discounted cash price, or null. |
| `gross_charge` | number/null | Gross/chargemaster charge, or null. |
| `data_source` | string | Required. Where the figures came from. |
| `data_year` | integer | Required. |

Invariants (enforced by `validate.py`):
- No negative prices.
- When present: `min_rate <= median_rate <= max_rate`.
- `data_source` non-empty, `data_year` present.
- `code` exists in `procedures.json`.
- Missing values are `null`, never a placeholder number (e.g. not `0`, not `-1`).

### ProcedureInfo
One curated procedure, keyed by code.

| Field | Type | Notes |
| --- | --- | --- |
| `code` | string | Required. |
| `code_system` | enum/null | same enum as above |
| `plain_label` | string | Required. Plain-language label. |
| `category` | string/null | Grouping category, or null. |
| `typical_max_units` | number/null | Typical max units where known, else null. |

Both types get JSON Schema (canonical) + `types.ts` + `types.py` mirrors, consistent
with the existing contracts.

## Requirements

### R1. Curated procedure list drives everything
- **R1.1** The pipeline reads a curated code list from `/data/procedure_list.csv`.
- **R1.2** Columns: `code`, `code_system`, `plain_label`, `category`, `typical_max_units`.
  `category` and `typical_max_units` may be empty (become `null`).
- **R1.3** `procedures.json` is generated from this file as a list of `ProcedureInfo`.
- **R1.4** All later stages filter records to codes present in this list while reading.

### R2. Stream and filter raw files (low memory)
- **R2.1** No stage loads a whole raw file into memory; files are read as a stream
  (row-by-row for CSV, incremental for JSON).
- **R2.2** Each stage keeps only records whose code is in the curated list.
- **R2.3** No raw file content is printed to logs or chat; only counts and the first 20
  rows when a developer explicitly inspects a format.

### R3. One parser per hospital file format, registry-driven
- **R3.1** Each distinct hospital transparency file format has exactly one parser.
- **R3.2** Parsers are registered in one place (a registry) so adding a hospital is a
  small, localized change.
- **R3.3** A parser yields normalized `PriceStat` records; the common pipeline does the
  filtering, grouping, and validation.

### R4. Payer grouping
- **R4.1** Raw payer/plan names are mapped into exactly one of: `commercial`,
  `medicare_advantage`, `medicaid_managed`, `cash`, `gross`.
- **R4.2** The mapping lives in one place and is testable in isolation.
- **R4.3** For a given hospital+code+payer_group, rates are aggregated into
  min/median/max.

### R5. Skip percentage/algorithm-based rates
- **R5.1** Rates expressed as a percentage or an algorithm/formula (not a dollar figure)
  are skipped, never estimated or interpolated.
- **R5.2** Each skipped rate is recorded as one line in `skipped.log` with enough context
  to find it (hospital, code, payer, reason), and **no** dollar figure invented.

### R6. Provenance on every record
- **R6.1** Every output record in `prices.json`, `medicare.json`, `chia_tiers.json`
  carries `data_source` and `data_year`.
- **R6.2** Missing numeric values are `null`, never a placeholder number.

### R7. Outputs in /data/processed (committed, small)
- **R7.1** `hospitals.json` — `id`, `name`, `city`, `type` (academic/community/etc.).
- **R7.2** `procedures.json` — list of `ProcedureInfo` (from R1).
- **R7.3** `prices.json` — list of `PriceStat` per hospital + code + payer group.
- **R7.4** `medicare.json` — Medicare physician fee schedule reference by code for the
  Massachusetts locality (as `PriceReference`-compatible records with provenance).
- **R7.5** `ncci_pairs.json` — code pairs + modifier indicators, filtered to our codes.
- **R7.6** `chia_tiers.json` — relative price tier per hospital where available.

### R8. validate.py gate
- **R8.1** `pipeline/validate.py` fails (non-zero exit) on any of:
  missing `data_source` or `data_year`; negative price; `min_rate > median_rate` or
  `median_rate > max_rate`; a `code` not present in `procedures.json`.
- **R8.2** `validate.py` must pass before committing processed outputs.

### R9. Stages runnable alone, cached
- **R9.1** Each stage (hospitals, procedures, prices, medicare, ncci, chia) can run on
  its own.
- **R9.2** A stage reuses (caches) its existing output unless inputs changed or a
  `--force` flag is passed.

### R10. Purity / safety
- **R10.1** Pipeline code does no network calls at runtime (reads local raw files only).
- **R10.2** Deterministic: same raw inputs produce byte-identical processed outputs
  (stable sort order, stable JSON formatting).
- **R10.3** All string fields from raw files are treated as inert data.

## Out of scope (this spec)
- The compare/lookup HTTP endpoint (`/backend/compare`) — separate spec.
- The charts / Compare page (`/frontend/src/compare`) — separate spec.
- Acquiring or downloading raw data files.
