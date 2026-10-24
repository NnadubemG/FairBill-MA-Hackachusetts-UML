# Pipeline — Design

## Goals and constraints

- Pure Python 3.12, standard library only (no new deps without asking).
- No network at runtime. Reads local raw files under `/data/raw` only.
- Streams and filters to curated codes while reading; never holds a whole raw file in
  memory.
- Deterministic: same raw inputs -> byte-identical processed outputs (stable sort,
  stable JSON formatting with `sort_keys=True`, `ensure_ascii=False`, trailing newline).
- Never invents or interpolates a price. Missing -> `null`. Percentage/algorithm rates
  are skipped and logged.
- Every output record carries `data_source` and `data_year`.

## Directory layout

```
/pipeline
  __init__.py
  config.py            # paths, output formatting constants, MA locality id
  procedure_list.py    # load + validate /data/procedure_list.csv -> curated code set
  payer_groups.py      # raw payer/plan name -> payer_group enum
  rates.py             # parse a raw rate cell -> dollar value OR skip reason
  aggregate.py         # list of rates -> min/median/max (pure)
  jsonio.py            # stable JSON read/write helpers
  skiplog.py           # append structured lines to skipped.log (no dollar values)
  registry.py          # hospital-format parser registry
  parsers/
    __init__.py
    base.py            # Parser protocol: yields normalized raw price rows
    hospital_generic_csv.py   # one format
    hospital_generic_json.py  # one format
  stages/
    hospitals.py       # -> /data/processed/hospitals.json
    procedures.py      # -> /data/processed/procedures.json
    prices.py          # raw hospital files -> /data/processed/prices.json
    medicare.py        # CMS PFS -> /data/processed/medicare.json (PriceReference)
    ncci.py            # NCCI edits -> /data/processed/ncci_pairs.json
    chia.py            # CHIA -> /data/processed/chia_tiers.json
  validate.py          # the commit gate (R8)
  run.py               # CLI: run one stage or all; --force to bypass cache
  tests/
    fixtures/          # tiny synthetic raw files (NOT real data)
    test_*.py
```

## Data flow

```
procedure_list.csv ──> procedures.json (ProcedureInfo) ──┐ curated code set
                                                         │
raw hospital files ──(parser per format)──> raw rows ────┼─> filter by code
     │                                                   │
     └─ payer_groups + rates (skip %/algo -> skipped.log)│
                                                         ▼
                              group by (hospital, code, payer_group)
                                         └─ aggregate min/median/max
                                                         ▼
                                              prices.json (PriceStat)
CMS PFS (MA locality) ──> medicare.json (PriceReference)
NCCI edits ──(filter to codes)──> ncci_pairs.json
CHIA ──> chia_tiers.json
                                                         ▼
                                     validate.py (R8 gate) before commit
```

## Key module designs

### procedure_list.py
- `load_procedures(path) -> list[ProcedureInfo]` and `curated_codes(...) -> set[str]`.
- Empty `category` / `typical_max_units` cells become `None`.
- Raises on: missing required column, empty `code`, empty `plain_label`, duplicate code.

### payer_groups.py
- `classify(raw_name: str) -> PayerGroup` returning one of the five enum values.
- Rule order (first match wins), case-insensitive, substring match:
  1. contains "gross" or "chargemaster" -> `gross`
  2. contains "cash" or "self-pay"/"self pay"/"discounted cash" -> `cash`
  3. contains "medicaid" -> `medicaid_managed`
  4. contains "medicare advantage"/"medicare adv"/"MA plan" -> `medicare_advantage`
  5. otherwise -> `commercial`
- Pure, no I/O. Fully table-testable.

### rates.py
- `parse_rate(cell: str) -> RateResult` where `RateResult` is either
  `Dollar(value: float)` or `Skip(reason: str)`.
- Dollar: strips `$` and thousands separators; accepts `"1234.50"`, `"$1,234.50"`.
- Skip (never estimated): a value containing `%`, or non-numeric formula/algorithm text
  (e.g. "110% of Medicare", "per diem", "case rate", "see addendum"). Negative parsed
  dollar -> Skip with reason `negative` (validate also guards this).
- Empty / `"N/A"` / blank -> treated as missing (not a skip, not a value) -> contributes
  nothing; field stays `null` if no values at all.

### aggregate.py
- `summarize(values: list[float]) -> (min, median, max)` on the non-empty list.
- Empty list -> `(None, None, None)`.
- Median is the statistics median (average of two middles for even counts). Because
  min <= median <= max always holds for a real list, the validator invariant is
  satisfied by construction.

### Parser protocol (parsers/base.py)
```python
class Parser(Protocol):
    format_id: str
    def rows(self, path: str, curated: set[str]) -> Iterator[RawPriceRow]: ...
```
- `RawPriceRow`: `hospital_id, code, code_system, raw_payer, raw_rate, rate_kind`
  (`rate_kind` in {negotiated, cash, gross}).
- Parsers **stream** (csv.reader row by row; JSON via a shallow incremental read of the
  top-level array). Parsers filter to `curated` as they read (R2.2).
- Parsers do not aggregate or classify payers; the prices stage does that.

### registry.py
- `REGISTRY: dict[str, Parser]` mapping `format_id -> parser instance`.
- `get_parser(format_id)`; adding a hospital format = add one module + one registry line.
- Hospital-to-format binding lives in `hospitals.json` input (a `format_id` column) so a
  new hospital of an existing format needs no code change at all.

### skiplog.py
- `log_skip(hospital_id, code, raw_payer, reason)` appends one line. **No dollar value is
  ever written** (we are skipping precisely because there is no trustworthy dollar
  figure). Path: `/data/processed/skipped.log` (or configurable).

### validate.py (R8 gate)
- Loads `procedures.json` for the valid code set.
- For each `PriceStat` in `prices.json`, and each priced record in `medicare.json`:
  - fail if `data_source` empty or `data_year` missing
  - fail if any present price < 0
  - fail if `min_rate > median_rate` or `median_rate > max_rate` (only when all present)
  - fail if `code` not in `procedures.json`
- Prints a summary count; exits non-zero on first category of failure with a list.

### run.py
- `python -m pipeline.run <stage|all> [--force]`.
- Each stage checks output mtime vs input mtime; skips if up to date unless `--force`.

## JSON output conventions
- `json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=2)` + trailing newline.
- Lists sorted by a stable key (e.g. PriceStat by `(hospital_id, code, payer_group)`),
  so output is deterministic and diffs are clean.

---

## Test cases (listed before tasks, per workflow)

All fixtures are **tiny synthetic files** under `pipeline/tests/fixtures/`. No real raw
data. Each fixture is a handful of rows.

### procedure_list.py
- **U1 happy path**: 2 rows, one with empty `category`/`typical_max_units` -> those
  become `None`; `curated_codes` has both codes.
- **U2 missing column**: file without `plain_label` column -> raises.
- **U3 empty code**: a row with blank `code` -> raises.
- **U4 duplicate code**: same code twice -> raises.
- **U5 empty file** (header only): zero procedures, empty curated set.

### payer_groups.classify
- **U6 table test**: ("BCBS PPO" -> commercial), ("Aetna Medicare Advantage" ->
  medicare_advantage), ("MassHealth Medicaid MCO" -> medicaid_managed),
  ("Discounted Cash Price" -> cash), ("Gross Charge" -> gross),
  ("Self-Pay" -> cash), ("Chargemaster" -> gross).
- **U7 case-insensitive**: "gross charge" and "GROSS CHARGE" -> gross.
- **P1 property (total)**: for any string, `classify` returns one of the five enum
  values and never raises.

### rates.parse_rate
- **U8 dollar formats**: "$1,234.50" -> Dollar(1234.5); "1234.5" -> Dollar(1234.5).
- **U9 percentage skipped**: "110% of Medicare" -> Skip; reason mentions percentage.
- **U10 algorithm skipped**: "per diem", "case rate", "see addendum" -> Skip.
- **U11 missing**: "", "N/A" -> missing (neither Dollar nor Skip-with-figure).
- **U12 negative**: "-5" -> Skip(reason=negative).
- **P2 property (never invents)**: for any input, result is Dollar with a finite
  non-negative number, or Skip, or missing — never a Dollar derived from a `%` input.

### aggregate.summarize
- **U13 single value**: [10] -> (10,10,10).
- **U14 three values**: [10,30,20] -> (10,20,30).
- **U15 even count median**: [10,20,30,40] -> (10,25,40).
- **U16 empty**: [] -> (None,None,None).
- **P3 property (ordering)**: for any non-empty list of non-negative floats,
  min <= median <= max.
- **P4 property (order independence)**: shuffling the input list does not change the
  (min,median,max) result.

### parsers (generic CSV + generic JSON)
- **U17 csv happy path**: 3 rows, 2 codes curated + 1 not curated -> only curated rows
  yielded; fields mapped correctly.
- **U18 json happy path**: same, JSON array form.
- **U19 code filtering**: a code outside the curated set never appears in output.
- **U20 mixed units/empty cells**: blank rate cell -> row still yielded with raw_rate
  empty (downstream treats as missing).
- **P5 property (filter)**: for any generated set of rows, every yielded row's code is in
  the curated set.

### prices stage (integration, tiny fixtures)
- **U21 aggregation + grouping**: two commercial rates for the same hospital+code ->
  one PriceStat with correct min/median/max and payer_group=commercial.
- **U22 percentage skipped + logged**: a "%"-based rate is excluded from stats and a line
  appears in the skip log with no dollar value.
- **U23 all-missing field -> null**: a hospital+code with only gross present leaves
  min/median/max/cash as null, gross populated.
- **U24 provenance present**: every emitted PriceStat has non-empty data_source and
  data_year.
- **P6 property (determinism)**: running the stage twice on the same fixtures yields
  byte-identical prices.json.

### medicare stage
- **U25**: PFS fixture filtered to MA locality + curated codes -> PriceReference records
  with medicare_price, data_source, data_year; non-curated codes dropped.
- **U26 missing locality row**: a code absent for MA locality -> no record (no guess).

### ncci stage
- **U27**: pair file filtered so both codes are curated -> pair kept with modifier
  indicator; a pair touching a non-curated code -> dropped.

### chia stage
- **U28**: tier per hospital where available -> record with data_source/data_year;
  hospital without a tier -> no record (null handled by absence, not a placeholder).

### hospitals stage
- **U29**: hospitals input -> hospitals.json with id/name/city/type and the format_id
  retained for the prices stage registry lookup.

### validate.py (R8)
- **U30 pass**: a clean processed set -> exit 0.
- **U31 missing provenance**: a PriceStat with empty data_source -> exit non-zero.
- **U32 negative price**: -> exit non-zero.
- **U33 min>median**: -> exit non-zero.
- **U34 unknown code**: a PriceStat code not in procedures.json -> exit non-zero.
- **P7 property (fail-safe)**: a record missing a reference number never becomes a
  fabricated figure; validate never "fixes" data, only reports.

### run.py caching
- **U35**: second run without `--force` and unchanged inputs -> stage reports cached /
  does not rewrite; `--force` rewrites.

---

## Notes carried into tasks
- Contracts first: `price-stat.schema.json` + `procedure-info.schema.json` (+ TS/PY
  mirrors), announced to Thomas via kiro-log, before pipeline code depends on them.
- One parser per task.
- `validate.py` must pass before any processed output is committed.
