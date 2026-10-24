# Reference Stage — Design

## Approach

A new stage `pipeline/stages/reference.py` reads three already-produced processed files
(`procedures.json`, `medicare.json`, `prices.json`) and writes `reference.json`: one
`PriceReference` per curated code that has a Medicare price and/or an MA gross range.

It is a pure transform over loaded JSON (no raw files, no network), consistent with the
other stages. Reuses `pipeline.jsonio` and the `PriceReference` contract.

## Inputs
- `procedures.json` — source of truth for `code_system` per code (ProcedureInfo).
- `medicare.json` — `PriceReference` records with `medicare_price` + data_source/year.
- `prices.json` — `PriceStat` records; we use the **gross** payer group's `gross_charge`
  per hospital for a code to derive the MA range.

## Logic (build_reference)
For each curated code (from procedures.json):
1. `medicare` = medicare_by_code.get(code) (a PriceReference dict) or None.
2. `gross_charges` = [ps.gross_charge for ps in prices where ps.code==code and
   ps.payer_group=="gross" and ps.gross_charge is not None].
3. `ma_range_low` = min(gross_charges) if any else None;
   `ma_range_high` = max(gross_charges) if any else None.
4. `medicare_price` = medicare.medicare_price if medicare else None.
5. If medicare_price is None AND both range ends are None -> emit NO record (R1.4).
6. `code_system`: procedures[code].code_system, else medicare.code_system, else the
   code_system on any contributing gross PriceStat. If still None -> raise
   ReferenceError (R2, D1): /core needs a known system; a null would break it.
7. Provenance (R3.2): collect the contributing source years —
   medicare.data_year (if medicare_price used) and the gross PriceStats' data_year
   (if range used). `data_year` = min(years). `data_source`:
   - both present and years differ -> "<med_src> <med_yr>; MA gross charges <gross_yr> (older year shown)"
   - both present, same year -> "<med_src>; MA gross charges"
   - medicare only -> med_src
   - range only -> "MA gross charges" (+ the gross data_source if uniform)
   data_source must be non-empty.
8. Build PriceReference(code, code_system, medicare_price, ma_range_low, ma_range_high,
   data_source, data_year).

Sort by code. Write with jsonio (deterministic). No duplicate (code, code_system) by
construction (one record per code).

## validate.py extension
Add `_check_reference(reference_path, valid_codes, problems)`:
- duplicate (code, code_system) across records -> fail
- missing/empty code_system -> fail
- missing data_source/data_year -> fail (reuse _check_provenance)
- ma_range_low > ma_range_high (both present) -> fail
- negative medicare_price / ma_range_low / ma_range_high -> fail (reuse _check_nonnegative)
- code not in procedures.json -> fail (reuse _check_code_known)
`validate()` gains an optional `reference_path` (default config) and runs the new checks
only if the file exists (so partial pipelines still validate).

## config
Add `REFERENCE_JSON = PROCESSED_DIR / "reference.json"`.

## Test cases (before tasks)
Fixtures are tiny in-memory lists passed to build_reference (no disk needed), plus a
validate test writing small JSON to tmp_path.

- **RF1** combine (medicare 92.47 + gross [400, 600] across 2 hospitals) ->
  medicare_price 92.47, ma_range_low 400, ma_range_high 600, code_system from procedures.
- **RF2** medicare only -> ma_range_* null.
- **RF3** range only -> medicare_price null.
- **RF4** neither -> no record for that code.
- **RF5** years differ (med 2025, gross 2024) -> data_year 2024, data_source says "older
  year shown".
- **RF6** code_system never null (from procedures).
- **RF6b** code_system missing everywhere -> ReferenceError raised.
- **RF7** validate: duplicate (code, code_system) -> fail.
- **RF8** validate: ma_range_low > ma_range_high -> fail.
- **RF9** validate: negative value -> fail.
- **RF10** determinism: two builds identical, sorted by code.

## Notes carried into tasks
- Do not edit the PriceReference schema or PriceStat/ProcedureInfo.
- gross_charge is already per-unit as produced by the prices stage (cash/gross store a
  single representative figure); use it directly.
- Keep build_reference pure over loaded dicts so RF1-RF6 need no disk.
