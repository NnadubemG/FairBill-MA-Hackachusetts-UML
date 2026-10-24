# Pipeline — Tasks

Small tasks, done one or two at a time. Contracts first. `validate.py` must pass before
committing processed outputs. Fixtures are tiny synthetic files only.

- [x] 1. Propose contract additions (PriceStat, ProcedureInfo)
  - Add `contracts/price-stat.schema.json` and `contracts/procedure-info.schema.json`
    (canonical JSON Schema), mirroring field lists in requirements.md.
  - Update `contracts/types.py` and `contracts/types.ts` mirrors; add `PayerGroup` enum.
  - Append a kiro-log line announcing the additive schemas to Thomas.
  - _Owner note: /contracts is Thomas's; additive only, backward compatible._
  - _Requirements: R7.2, R7.3; proposed contracts section_

- [x] 2. Pipeline scaffolding + config + jsonio
  - Create `/pipeline` package, `config.py` (paths, MA locality id, JSON format consts),
    `jsonio.py` (stable read/write: sort_keys, ensure_ascii=False, indent=2, trailing
    newline), `pipeline/tests/` with empty fixtures dir.
  - _Requirements: R10.2, JSON output conventions_

- [x] 3. Curated procedure list -> procedures.json
  - `procedure_list.py`: `load_procedures`, `curated_codes`.
  - `stages/procedures.py`: write `procedures.json` (ProcedureInfo list).
  - Fixtures + tests U1–U5.
  - _Requirements: R1.1–R1.4, R7.2_

- [x] 4. Payer grouping
  - `payer_groups.py`: `classify(raw_name) -> PayerGroup` (rule order from design).
  - Tests U6, U7; property test P1 (total, never raises).
  - _Requirements: R4.1, R4.2_

- [x] 5. Rate parsing (skip %/algorithm, never invent)
  - `rates.py`: `parse_rate -> Dollar | Skip | missing`.
  - `skiplog.py`: `log_skip` (no dollar values ever written).
  - Tests U8–U12; property test P2 (never invents from a % input).
  - _Requirements: R5.1, R5.2, R6.2_

- [x] 6. Aggregation
  - `aggregate.py`: `summarize(values) -> (min, median, max)`; empty -> all None.
  - Tests U13–U16; property tests P3 (min<=median<=max), P4 (order independence).
  - _Requirements: R4.3, R6.2_

- [x] 7. Parser protocol + registry
  - `parsers/base.py` (Parser protocol, RawPriceRow), `registry.py` (REGISTRY,
    get_parser). No concrete parser yet.
  - _Requirements: R3.1–R3.3_

- [x] 8. Parser: generic hospital CSV format
  - `parsers/hospital_generic_csv.py`, streaming, filters to curated codes while reading.
  - Register in `registry.py`.
  - Fixtures + tests U17, U19, U20; property test P5 (every yielded code is curated).
  - _Requirements: R2.1, R2.2, R3.1, R3.3_

- [x] 9. Parser: generic hospital JSON format
  - `parsers/hospital_generic_json.py`, incremental array read, filters while reading.
  - Register in `registry.py`.
  - Fixtures + test U18.
  - _Requirements: R2.1, R2.2, R3.1, R3.3_

- [x] 10. Hospitals stage -> hospitals.json
  - `stages/hospitals.py`: id/name/city/type (+ retain format_id for prices lookup).
  - Fixture + test U29.
  - _Requirements: R7.1, R3.2_

- [x] 11. Prices stage -> prices.json (integration)
  - `stages/prices.py`: for each hospital, pick parser by format_id, stream rows, filter
    to curated, classify payer, parse rate (skip %/algo -> skiplog), aggregate per
    (hospital, code, payer_group), attach data_source/data_year, write PriceStat list.
  - Fixtures + tests U21–U24; property test P6 (determinism).
  - _Requirements: R3.3, R4.3, R5.*, R6.*, R7.3, R10.2_

- [x] 12. Medicare stage -> medicare.json
  - `stages/medicare.py`: stream CMS PFS, filter to MA locality + curated codes, emit
    PriceReference records with provenance; missing locality row -> no record.
  - Fixtures + tests U25, U26.
  - _Requirements: R7.4, R6.1_

- [x] 13. NCCI stage -> ncci_pairs.json
  - `stages/ncci.py`: stream edit file, keep pairs where both codes are curated, retain
    modifier indicator; drop pairs touching non-curated codes.
  - Fixture + test U27.
  - _Requirements: R7.5, R2.2_

- [x] 14. CHIA stage -> chia_tiers.json
  - `stages/chia.py`: relative price tier per hospital where available, with provenance;
    hospital without a tier -> no record (absence, not placeholder).
  - Fixture + test U28.
  - _Requirements: R7.6, R6.1, R6.2_

- [x] 15. validate.py (R8 gate)
  - Checks: missing data_source/data_year; negative price; min>median or median>max;
    code not in procedures.json. Non-zero exit on failure.
  - Fixtures + tests U30–U34; property test P7 (fail-safe: never fabricates).
  - _Requirements: R8.1, R8.2_

- [x] 16. run.py CLI + caching
  - `run.py`: run one stage or all; `--force` bypasses cache; skip stage when output is
    up to date vs inputs.
  - Test U35.
  - _Requirements: R9.1, R9.2_
