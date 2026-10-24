# Compare API — Design

## Goals and constraints

- Python stdlib only (no new deps). Reads `/data/processed/*.json`; no DB, no writes, no
  outbound network.
- Lookup logic is pure functions over already-loaded data, so it unit-tests without a
  server. A thin `http.server` wrapper is the only I/O boundary.
- Never fabricate a value — absent figures are `null`. Every response carries `framing_note`.
- Deterministic: same data + same request -> byte-identical response (stable ordering,
  stable aggregation via the pipeline's `aggregate.summarize`).

## Directory layout

```
/backend/compare
  __init__.py
  store.py        # load processed JSON once into an in-memory Store (dicts/indexes)
  framing.py      # the approved framing_note string (banned-word-free)
  service.py      # pure functions: list_procedures(store), compare(store, code)
  server.py       # thin stdlib http.server: GET /procedures, GET /compare?code=...
  tests/
    fixtures/processed/   # tiny hand-made hospitals/procedures/prices/medicare/chia JSON
    test_*.py
```

Data loading (`store.py`) is separated from lookup (`service.py`) so handlers are pure and
testable. `server.py` is a trivial adapter: parse request -> call service -> JSON out.

## The Store (store.py)

Loads the five processed files once and builds indexes for O(1) lookup:

```
Store:
  procedures: dict[str, ProcedureInfo-as-dict]                  # by code
  procedures_order: list[str]                                   # stable (by code)
  hospitals: dict[str, {id,name,city,type}]                     # by hospital_id
  prices_by_code: dict[str, list[PriceStat-as-dict]]            # by code
  medicare_by_code: dict[str, PriceReference-as-dict]           # by code
  chia_by_hospital: dict[str, chia-record]                      # by hospital_id
```

- Built with `jsonio.read_json` (reuses the pipeline's reader).
- Missing file -> treated as empty index (the service still returns well-formed results).
- `Store.load(processed_dir)` classmethod; also `Store.from_dicts(...)` for tests (no disk).

## Service functions (service.py) — pure

### list_procedures(store) -> dict
```
{ "procedures": [ProcedureInfo...in code order], "framing_note": FRAMING_NOTE }
```

### compare(store, code) -> dict
1. Normalize `code` (strip; uppercase to match pipeline normalization).
2. If code not in `store.procedures`: return the not-found shape (D2):
   `{code, found: false, plain_label: null, code_system: null, hospitals: [], medicare: null,
     statewide: {min:null,median:null,max:null}, data_years: [], note: "Code not found in
     the curated list.", framing_note}`.
3. Otherwise gather `store.prices_by_code[code]`, group by `hospital_id`, and for each
   hospital that has at least one PriceStat:
   - attach hospital name/city/type from `store.hospitals`
   - `price_stats`: a dict keyed by payer_group -> the PriceStat dict (min/median/max/
     cash_price/gross_charge/data_source/data_year)
   - `chia_tier`: `store.chia_by_hospital.get(hospital_id)` or null
   - `missing_note`: set when commercial is absent but other groups exist (R4.2)
4. `medicare`: `store.medicare_by_code.get(code)` or null.
5. `statewide`: `summarize([each hospital's commercial median_rate that is not None])`;
   returns (None,None,None) when empty (R3.2).
6. `data_years`: sorted unique set of data_year across all PriceStats + medicare in the
   result (for display).
7. Attach `framing_note`. Hospitals sorted by `hospital_id`; payer groups serialized in a
   fixed order. Return.

## Framing note (framing.py)

```
FRAMING_NOTE = ("These figures come from public hospital and government price files and "
                "may be worth reviewing. What you actually pay depends on your plan and "
                "your specific care.")
```
- Contains none of the banned words. Asserted by a test (C5).

## server.py (thin stdlib adapter)

- `http.server.BaseHTTPRequestHandler`; routes:
  - `GET /procedures` -> `list_procedures(store)`
  - `GET /compare?code=XXXXX` -> `compare(store, code)`; missing `code` param -> 400 with a
    small JSON error.
  - anything else -> 404 JSON.
- Serializes with the pipeline's deterministic `jsonio.dumps`.
- Loads the Store once at startup. Does not log request bodies/queries (R7.1).
- CLI: `python -m backend.compare.server [--port 8000] [--data DIR]` for local viewing.

## Test cases (before tasks)

Fixtures: tiny processed JSON under `tests/fixtures/processed/` (2 hospitals, 2 codes),
hand-made so they're independent of a pipeline run. Also `Store.from_dicts` for inline data.

- **C1 known code (service)**: code `99213` present at hospital A (commercial 100/150/200,
  cash 95) and hospital B (gross 420) -> both hospitals present; A has commercial+cash, B
  has gross; medicare attached; statewide computed from commercial medians.
- **C2 unknown code (service)**: `00000` -> `found: false`, empty hospitals, null medicare,
  null statewide, not-found note, framing_note present.
- **C3 partial data**: hospital with only gross -> appears, gross populated, min/median/max/
  cash null, `missing_note` set.
- **C4 cash-only**: hospital with only cash -> cash populated, no commercial; statewide
  (which uses commercial medians) excludes it.
- **C5 framing_note**: present on both `list_procedures` and `compare`; contains no banned
  word (checked against product.md list).
- **C6 no medicare**: code with no medicare.json entry -> `medicare: null`, rest intact.
- **C7 determinism**: `jsonio.dumps(compare(...))` identical across two calls on same store.
- **C8 statewide aggregation**: three hospitals with commercial medians 100/200/300 ->
  statewide min=100 median=200 max=300 (uses `aggregate.summarize`).
- **C9 store loads from disk**: `Store.load(fixtures/processed)` indexes all five files;
  a missing file -> empty index, service still returns well-formed output.
- **C10 server smoke (optional/light)**: start handler in-process, GET /procedures and
  /compare return 200 + valid JSON; missing `code` -> 400; unknown route -> 404.

## Notes carried into tasks
- Reuse `pipeline.jsonio` (read/dumps) and `pipeline.aggregate.summarize` — no duplication,
  consistent determinism and the min<=median<=max invariant.
- Keep `service.py` pure (no I/O) so C1–C8 need no server.
- No new dependency.
