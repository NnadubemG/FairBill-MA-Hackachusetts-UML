# Design — Eval Harness (`/evals`)

## Goal
Run synthetic bills through extraction, `/core`, explain and letter, score the results against
the ground truth, and write one markdown report. Every model call goes through a disk cache
keyed by the file hash, so reruns are free and a prompt or model change is the only thing that
costs money.

## Module layout (all under `/evals`)
```
/evals/
  __init__.py
  __main__.py        # CLI: python -m evals
  config.py          # defaults, thresholds (rules of thumb), env var names, limits
  corpus.py          # build_corpus(): Bill objects from /synthetic, in memory; private-path guard
  cache.py           # CachingClient (disk cache), CacheStats, errors, file/request hashing
  oracle.py          # OracleClient: fake model that answers from the ground truth
  align.py           # deterministic one-to-one line matching
  score_extract.py   # extraction metrics from the matches
  score_flags.py     # flag catch / false-positive metrics
  invariants.py      # hard-failure checks on explanations and letters
  run.py             # orchestrate one run -> RunResult
  report.py          # RunResult -> markdown (deterministic)
  README.md
  results/           # default report location (committed if we choose)
  .cache/            # model-reply cache; has its own .gitignore ("*"); never committed
  tests/
```
Nothing here redefines a `/contracts` type. `Bill`, `RunResult` and the metric records are
wrapper types.

## Data flow (one run)
1. `build_corpus(scenarios, seeds, styles)` -> `list[Bill]` (sorted by `bill_id`, then style).
2. Build a **client factory**: `CachingClient` around the real client (real mode), or
   `OracleClient` (`--fake`). A factory has `scoped(task, file_sha256) -> LLMClient` and
   `stats`.
3. For each bill:
   a. **Extract:** `extract(pdf, "application/pdf", client=factory.scoped("extract", sha))`.
   b. **Align** extracted lines to truth lines (`align.match`).
   c. **Flags (pipeline):** `core.analyze(extracted_lines, refs, quantity_limits=...,
      bundle_pairs=...)`, map flags back through the alignment, compare to `expected_flags`.
   d. **Flags (oracle run):** `core.analyze(truth_lines, ...)` and compare to `expected_flags`
      (a `/core` self-check).
   e. **Explain:** `explain(oracle_flags, client=factory.scoped("explain", sha))`.
   f. **Letter:** `generate_letter(coding_review request with oracle_flags and truth lines,
      client=factory.scoped("letter", sha))` when there are flags.
   g. **Invariants** on the explanations and the letter.
4. Collect everything in `RunResult`. `report.render(RunResult)` -> markdown. Write it.
5. Exit code: 0 normally; 1 with `--strict` if a threshold fails, or always if there is a hard
   failure; 2 for a usage or config error.

## Corpus (`corpus.py`)
```python
@dataclass(frozen=True)
class Bill:
    bill_id: str          # e.g. "mixed-1"
    scenario: str
    style: str            # the layout: "plain" | "messy"
    pdf: bytes
    file_sha256: str      # SHA-256 of pdf
    truth: SyntheticBill  # from /synthetic
```
- `build_corpus(scenarios=SCENARIOS, seeds=(1,), styles=STYLES)` calls `generate_bill(seed,
  scenario)` and `render_pdf(bill, style)`. No files are written.
- `ensure_not_private(path)` resolves a path and raises `PrivatePathError` if it is inside
  `<repo>/private`. Used for `--out` and `--cache-dir`.
- Only PDFs are sent. The extraction prompt accepts images and PDFs, and `/synthetic` renders
  PDFs and text only.

## Disk cache (`cache.py`)
```python
class CachingClient:
    def __init__(self, inner: LLMClient | None, cache_dir: Path, model_label: str, *,
                 cache_only: bool = False, max_calls: int = 60): ...
    def scoped(self, task: str, file_sha256: str) -> LLMClient: ...
    stats: CacheStats   # hits, misses, real_calls, budget_hit, cache_only_misses
```
- **Key:** `sha256("evals-cache-v1" | task | model_label | file_sha256 | request_hash)`, where
  `request_hash` = SHA-256 of canonical JSON of `(system, content, repair_hint, max_tokens)`.
  The content holds the bill itself (base64), so a change to the file, the model, the task, or
  any prompt text gives a new key.
- **Entry file:** `<cache_dir>/<key>.json` with `{"task", "model", "file_sha256", "reply"}`.
  Nothing else. Written to a temporary file and renamed, so a crash cannot leave half a file.
- **Hit:** return `reply`. **Miss:** call `inner.invoke(...)`; if the result is a non-empty
  string, store it. A raised error is not cached and propagates (so the feature's own fallback
  runs).
- **Damaged file:** unreadable JSON, wrong shape, or non-string reply -> treated as a miss and
  overwritten.
- **Cache-only:** a miss raises `CacheMiss` (an `LLMError`); `inner` is never called.
- **Budget:** a real call past `max_calls` raises `BudgetExceeded` (an `LLMError`) and sets
  `stats.budget_hit`. Hits do not count.
- **Self-ignoring folder:** on first use the cache creates `<cache_dir>/.gitignore` with `*`.
- `model_label` is the model name for real mode and `fake-oracle` for the oracle.
- No time, no randomness: entries have no timestamps.

## Oracle (`oracle.py`)
`OracleClient(bills)` has the same `scoped(task, file_sha256)` shape. It answers from the truth
for the bill with that hash:
- `extract`: a JSON envelope with the truth `line_items` (contract fields only), `metadata`
  (hospital, statement date, total) and `confidence_hints` ("high" for coded lines).
- `explain`: for each flag in the request, `reason` plus a different closing question.
- `letter`: a fixed first-person paragraph with no figures (worded differently from the
  fallback so tests can tell them apart).
It exists to run the whole harness offline and to test the scoring. Its numbers say nothing
about a model, and the report says so.

## Line matching (`align.py`)
One-to-one, deterministic, independent of the order of the extracted lines.
- Normalise: code = stripped upper-case or `None`; amount = cents; quantity = float or `None`.
- Sort both lists by `(code or "", amount, quantity or 0, date or "", id, description)`.
- Match in stages. In each stage, group the still-unmatched lines by the stage key and pair them
  in sorted order (`min(len)` pairs per key):
  1. code, amount and quantity all equal
  2. code and amount equal
  3. amount equal (the code differs)
  4. code equal (the amount differs)
- Lines left over: truth lines are **missing**, extracted lines are **extra**.
- So one differing field still matches (and shows up in that field's error rate). Two differing
  fields count as a missing line plus an extra line. This is a rule of thumb, stated in the
  report.
- `match(truth_lines, extracted_lines) -> Alignment(pairs, missing, extra)`.

## Extraction metrics (`score_extract.py`)
Per bill, then summed (micro-average: add numerators and denominators, then divide).
- `line_recall = matched / truth_lines`, `line_precision = matched / extracted_lines`.
- `code_exact`, `charge_exact` over matched pairs. `units_exact` over matched pairs whose truth
  has a quantity. `date_exact` over matched pairs whose truth has a date of service.
- `hallucinated_codes`: matched pairs where the truth code is `None` and the extracted code is
  not.
- `confirmation_recall`: of matched pairs with no truth code, how many have
  `needs_confirmation` true (from `ExtractionResult.line_confidence`).
- `fallback_bills`: bills where extraction returned no lines with the "unavailable" warning.
- `injection_extra_lines`: extra lines on `injection` bills.
- A rate with a zero denominator is `None` (shown `n/a`).
- Failure records: `(bill_id, style, kind, line)` where `kind` is `missing_line`, `extra_line`,
  `code`, `units`, `charge`, `date`, `hallucinated_code`, `extraction_fallback`. Only field
  names and truth ids; no text.

## Flag metrics (`score_flags.py`)
- Map each flag from the extracted lines to a truth id with the alignment. A flag on an
  unmatched extracted line maps to `None` and counts as a false positive.
- `got = {(truth_id, flag_type)}`, `expected` from the truth. `caught = got ∩ expected`,
  `missed = expected − got`, `false_pos = got − expected`.
- Per flag type: planted, caught, `catch_rate`.
- `fp_rate_clean = clean bills with any false positive / clean bills` and the same for no-issue
  bills (`clean` + `injection`).
- Oracle run: `core.analyze(truth)` vs `expected_flags`, as sets. Any difference is a `/core`
  self-check failure.

## Explain and letter (`run.py`, `invariants.py`)
- Explain input flags come from `core.analyze` on the **truth** lines, so explain is measured on
  its own. `explain_fallback_rate = sum(fallback_count) / sum(flags)`.
- Letter: `coding_review`, all those flags (the handler caps at 10), fixed synthetic patient
  fields. `letter_fallback_rate = bills with used_fallback / bills with a letter`.
- Invariants (hard failures, counted): banned word in an explanation or in the letter;
  explanation figure not in its flag; letter draft not valid against `letter-draft.schema.json`;
  a referenced line id not in the bill.

## Thresholds (`config.py`, rules of thumb)
| Metric | Pass when |
|---|---|
| line recall, line precision | >= 0.95 |
| code exact, units exact | >= 0.95 |
| charge exact | >= 0.98 |
| hallucinated codes | = 0 |
| injection extra lines | = 0 |
| flag catch rate (each type that has planted flags) | >= 0.90 |
| false-positive rate on clean bills | = 0 |
| `/core` self-check mismatches | = 0 |
| explain fallback rate | <= 0.25 |
| letter fallback rate | <= 0.30 |
| invariant violations | = 0 (hard) |
The numbers are a starting point for the team to adjust. They live in one file and the report
prints them.

## Report (`report.py`)
Markdown, deterministic, no timestamps:
1. Title and run info: mode (real / `--cache-only` / `FAKE ORACLE - not a model`), models per
   task, corpus size, cache hits, misses, real calls, budget status.
2. Extraction table: overall, then by layout, then by scenario.
3. Flag table: per type (planted, caught, catch rate), false positives, clean-bill rate,
   `/core` self-check.
4. Explain and letter table.
5. Threshold summary: one line per threshold with value, limit, pass or fail.
6. Failures: bill id, layout, kind, field/line id. Hard failures first.
Cells are escaped (`|` -> `\|`, line breaks -> a space). The report holds ids, field names and
numbers only.

## CLI (`__main__.py`)
```
python -m evals [--fake] [--cache-only] [--max-calls N] [--strict]
                [--scenarios a,b] [--seeds 1,2] [--styles plain,messy]
                [--out PATH] [--cache-dir PATH]
```
- Real mode reads `ANTHROPIC_API_KEY`, `EXTRACT_MODEL_ID`, `EXPLAIN_MODEL_ID`,
  `LETTER_MODEL_ID` through the shared client (`make_client(model_env_var=...)`).
- Missing variable and not `--cache-only`: print the variable name, exit 2.
- `--cache-only` needs the model names (for the cache key) but not the key.
- Progress lines name bill ids and counts only.
- Default `--out`: `evals/results/eval-results.md`. Default `--cache-dir`: `evals/.cache`.

## Privacy
- Synthetic bills only. `/private` paths are refused for `--out` and `--cache-dir`.
- No logging of bill text, replies or the key. The cache holds replies to synthetic bills only.
- Writes only to the cache folder and the report path.

## Test cases (listed BEFORE tasks)

### Unit tests
**Corpus**
- **S1** default corpus has 16 bills (8 scenarios x 2 styles), unique ids, each with scenario,
  style, truth. Same arguments -> same bytes.
- **S2** every PDF starts with `%PDF` and its `file_sha256` matches.
- **S3** `--scenarios`, `--seeds`, `--styles` choose the bills; an unknown scenario or style
  gives a clear error.
- **S4** `ensure_not_private` refuses paths under `private/` (also through `..` and symlink-like
  relative paths) and allows others.

**Cache**
- **C1** miss then hit: the second identical call does not reach `inner`; the reply is equal;
  stats count 1 miss, 1 hit.
- **C2** a different model label is a miss.
- **C3** the key changes when any of these change: task, model, file hash, system prompt,
  content, repair hint, `max_tokens`.
- **C4** the key does not depend on dict order.
- **C5** the entry file holds only `task`, `model`, `file_sha256`, `reply`; no key, no time.
- **C6** the cache folder has a `.gitignore` containing `*`.
- **C7** a damaged file (bad JSON, wrong shape, non-string reply) is a miss and is replaced.
- **C8** if `inner` raises, nothing is cached and the error propagates.
- **C9** an empty-string reply is not cached.
- **C10** `cache_only`: a miss raises `CacheMiss` and `inner` is never called; a hit still works.
- **C11** budget: after `max_calls` real calls the next miss raises `BudgetExceeded`, hits still
  work, `budget_hit` is set.
- **C12** the API key never appears in any cache file.
- **C13** a cached reply replayed through `extract` gives the same `ExtractionResult` as the
  live reply did.

**Line matching and extraction scoring**
- **A1** perfect extraction -> recall and precision 1.0, all exact rates 1.0.
- **A2** a wrong charge -> `charge_exact` below 1; the line still matches.
- **A3** a missing line lowers recall; an extra line lowers precision.
- **A4** a hallucinated code (truth `None`, extracted a code) is counted.
- **A5** reordering the extracted lines gives the same result.
- **A6** two identical lines (duplicate scenario) match one to one, not both to the same line.
- **A7** empty extraction -> recall 0, precision `None`, no error.
- **A8** a wrong date lowers `date_exact`; a truth line with no date is ignored.
- **A9** code compare ignores case and spaces.
- **A10** `confirmation_recall` counts only lines with no truth code.
- **A11** two fields wrong on one line -> one missing plus one extra.
- **A12** rates sum across bills (micro-average), not average of averages.

**Flags**
- **F1** oracle run: for every scenario, `core.analyze(truth)` equals `expected_flags`.
- **F2** the extraction drops one duplicate copy -> the duplicate flag is missed -> catch rate
  below 1.
- **F3** an extra extracted line that gets flagged is a false positive.
- **F4** clean bill, perfect extraction -> no flags, false-positive rate 0.
- **F5** flags map through the alignment when extracted ids differ from truth ids.
- **F6** types with no planted flags show `n/a`.
- **F7** a flag on an unmatched extracted line is a false positive.

**Explain, letter, invariants**
- **X1** oracle explain: fallback rate 0, no invariant violation.
- **X2** oracle letter: `used_fallback` false for bills with flags; draft valid.
- **X3** the invariant checker flags a banned word, an invented figure, an invalid draft, an
  unknown referenced id.
- **X4** a bill with no flags produces no letter and is not counted in the letter rate.
- **X5** when the model fails (cache-only miss), explain and letter fall back, and the rates
  show it.

**Report and CLI**
- **R1** same results -> identical text.
- **R2** has all the tables, and each failure has a bill id and a layout.
- **R3** threshold lines show pass or fail; `--strict` exit code 1 on a fail, 0 on a pass.
- **R4** no API key, raw reply, or bill text in the report.
- **R5** fake run is labelled "FAKE ORACLE - not a model".
- **R6** `|` and line breaks in a cell cannot break the table.
- **K1** `python -m evals --fake` finishes offline, writes the report, exit 0, and the oracle
  scores 100% on extraction and flags.
- **K2** a real run with no `ANTHROPIC_API_KEY` or model name: clear message, exit 2, no
  traceback.
- **K3** `--cache-only` on an empty cache makes no API call and still writes a report.
- **K4** `--out` and `--cache-dir` under `private/` are refused (exit 2).
- **K5** `--max-calls` is passed to the cache.
- **K6** a noisy oracle (drops a line, changes a charge, adds a code) produces the expected
  lower scores and failure rows end to end.
- **K7** the run writes only the report and cache files.

### Property-based tests (Hypothesis)
- **PE1** scoring never raises for any extracted lines against any truth.
- **PE2** every rate is `None` or between 0 and 1; counts are never negative.
- **PE3** the matching is one to one: no line is used twice; `pairs <= min(len)`.
- **PE4** shuffling the extracted lines does not change the metrics or the mapped flags.
- **PE5** for any synthetic bill, a perfect extraction scores 1.0 everywhere.
- **PE6** the cache key is deterministic and differs whenever one input differs.
- **PE7** cache round trip: whatever non-empty text is stored is returned unchanged.
- **PE8** report escaping: a cell never contains a raw `|` or line break.
- **PE9** `matched + missing = truth lines` and `matched + extra = extracted lines`.

### Privacy
- **PR1:** progress output, report and cache files contain no API key and no raw model text
  beyond the cached reply files; nothing is written outside the report and cache folder.

## Open decisions (for Sam)
1. **The code is not on `main` yet.** Evals call extract, explain and letter and the shared
   `LLMClient`. Those are on `sam-explain` and `sam-letter`. `sam-evals` was made from the
   latest `main`. Before code starts, either (A) merge `sam-letter` (it contains `sam-explain`)
   into `main` first, then I merge `main` into `sam-evals`, or (B) I merge `sam-letter` into
   `sam-evals`. I recommend A.
2. **Report location.** The team guide wants the table in `/docs/eval-results.md`, but `/docs`
   is Thomas's folder. This design writes to `evals/results/eval-results.md` by default (my
   lane). For the final copy, either Thomas confirms I may write that one file with
   `--out docs/eval-results.md`, or you copy it. I will not write into `/docs` without a yes.
3. **Thresholds.** The numbers in the table above are my starting point. Please confirm or
   change them. They only decide pass or fail in the report.
4. **Cost limit.** Default `--max-calls 60`. One full run is at most 16 extract + 16 explain +
   16 letter calls = 48 per model set. Reruns are free from the cache. OK?
5. **Optimistic extraction.** Synthetic PDFs are clean text PDFs, so extraction scores will be
   better than on a phone photo or a scan. The real redacted bill test at about hour 5 stays a
   manual step. The README will say so.
6. **Comparing models.** One run uses one model per task. To compare, run the command again
   with other model names and another `--out`. The cache key includes the model, so nothing is
   mixed up.
7. **`analyze` and explain.** ND's `analyze_bill` takes an optional `explain` function
   (`list[Flag] -> list[Flag]`). The evals call `explain` directly. Wiring the real explain into
   `analyze` (a small adapter) is for ND or David, not this spec.
