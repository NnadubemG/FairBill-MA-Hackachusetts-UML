# Reference Stage — Requirements

## Why

Thomas's `/core` checks engine takes `PriceReference[]` and needs **exactly one**
`PriceReference` per code. Today `medicare.json` holds the `medicare_price` and (if a
separate file also held `ma_range_*` for the same code+year) `/core` would see two
records for one code and treat them as ambiguous -> emit NO flags. So we merge the
Medicare price and the MA range into a single `PriceReference` per code in
`/data/processed/reference.json`.

Contract: `contracts/price-reference.schema.json` (owned by Thomas; we do NOT edit it).
Fields: `code`, `code_system`, `medicare_price`, `ma_range_low`, `ma_range_high`,
`data_source`, `data_year`.

Stay inside `/pipeline`, `/data/processed`, `/backend/compare`. Do not change `PriceStat`
or `ProcedureInfo`.

## Requirements

### R1. One PriceReference per curated code
- **R1.1** Add a pipeline stage "reference" writing `/data/processed/reference.json`:
  one `PriceReference` per curated code that has data.
- **R1.2** `medicare_price` = the per-unit Medicare price from the medicare stage
  (`medicare.json`) for that code.
- **R1.3** `ma_range_low` = lowest gross_charge, `ma_range_high` = highest gross_charge,
  across MA hospitals in `prices.json` for that code, **gross** payer group, per unit.
- **R1.4** If a code has neither a Medicare price nor a range, emit NO record.

### R2. code_system on every record (never null)
- **R2.1** Set `code_system` on EVERY emitted record (HCPCS/CPT/REV/DRG), taken from
  `procedures.json` (ProcedureInfo) for that code; if absent there, fall back to the
  value carried on the medicare/price records; if still unknown, the code is unusable
  for reference (skip, since /core needs a known system) — but this must be surfaced,
  not silently dropped a figure we have.
  Decision (D1): if `procedures.json` has no `code_system` and neither source carries one,
  treat it as a data error -> the stage raises, because emitting null would break /core.

### R3. Provenance required, combined years
- **R3.1** `data_source` and `data_year` are required and non-empty on every record.
- **R3.2** If the Medicare source year and the price (gross) source year differ, use the
  **older** year as `data_year` and say so in `data_source`
  (e.g. "CMS PFS 2025; MA gross charges 2024 (older year shown)").
- **R3.3** Never invent or interpolate. A field with no data stays `null`.

### R4. Deterministic, de-duplicated
- **R4.1** Output sorted by `code`, deterministic formatting.
- **R4.2** No duplicate `(code, code_system)` keys.

### R5. validate.py extended
- **R5.1** Extend `pipeline/validate.py` to validate `reference.json`, failing on:
  duplicate `(code, code_system)`; missing `code_system`; missing `data_source`/`data_year`;
  `ma_range_low > ma_range_high`; any negative value.
- **R5.2** Existing checks (prices, medicare) stay intact.

### R6. Compare endpoint (optional, low-risk)
- **R6.1** The compare store/service may read `reference.json` if present, but this spec
  does not require changing the compare response shape. (Deferred unless trivial.)

## Test cases (named; detailed in design)
- **RF1** combine: code with medicare_price + gross range across 2 hospitals -> one record,
  medicare_price set, ma_range_low/high = min/max gross, code_system from procedures.
- **RF2** medicare only: code with a medicare price but no gross -> record with
  ma_range_* null.
- **RF3** range only: code with gross but no medicare -> record with medicare_price null.
- **RF4** neither: code with no medicare and no gross -> no record.
- **RF5** differing years: medicare 2025, gross 2024 -> data_year 2024 and data_source
  notes the older year.
- **RF6** code_system from procedures: always set, never null.
- **RF7** validate duplicate-key: two records same (code, code_system) -> validate fails.
- **RF8** validate range order: ma_range_low > ma_range_high -> validate fails.
- **RF9** validate negative: negative medicare_price or range -> validate fails.
- **RF10** determinism: two builds byte-identical; sorted by code.

## Needs from Thomas
- Confirm `/core` indeed wants a SINGLE combined `PriceReference` per code from
  `reference.json` (not separate medicare + range files). This stage assumes yes.
- Confirm `/core` reads `reference.json` (not `medicare.json`) once this lands, so the
  two-records-per-code ambiguity is actually resolved on their side.
