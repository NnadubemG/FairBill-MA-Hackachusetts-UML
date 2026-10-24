# Requirements — Eval Harness (`/evals`)

## Overview
The eval harness measures how well the AI features work, on Thomas's synthetic bills (which
carry ground truth). One command runs it. It reports:

- **Extraction accuracy:** line match, and exact-match rates for code, units and charge.
- **Flag results:** per flag type, how many planted flags were caught, and the false-positive
  rate on clean bills (extraction -> `/core`).
- **Explain and letter quality:** how often the model's text is accepted by our checks, and
  how often the fixed fallback was needed.
- **Failures:** each one with the bill id and the layout.

It writes a markdown report. Model calls are **cached on disk by file hash**, so a rerun is
cheap and a prompt or model change is the only thing that costs money again. The harness
helps pick **the smallest model that passes** for each task.

Owner: Sam. Scope is `/evals` only. This spec does not change `/contracts`, `/core`,
`/synthetic`, `/data` or any other owner's area.

## Source of truth
- Ground truth: `contracts/synthetic-bill.schema.json` (`SyntheticBill`) and `/synthetic`
  (Thomas). `line_items` is what a perfect extraction returns. `expected_flags` is exactly the
  `(line_item_id, flag_type)` pairs `/core` should return. Ground truth is built in, never
  computed by calling `/core`.
- Flags come from `core.analyze` only. The harness never makes its own flags.

## Glossary
- **Bill** — one synthetic bill in one layout (`plain` or `messy`), as a PDF plus its truth.
- **Run** — one execution of the harness over the corpus with one set of model names.
- **Oracle** — a fake model that replies from the ground truth. Used for smoke tests only.
- **Cache hit / miss** — a model call answered from disk / sent to the model.

## Requirements

### R1 — Corpus
**User story:** As the team, evals run on bills with known answers.

Acceptance criteria:
1. THE default corpus SHALL be every scenario in `synthetic.SCENARIOS` with seed 1 in every
   style in `synthetic.STYLES`. (Today: 8 scenarios x 2 styles = 16 bills.)
2. THE corpus SHALL be built in memory with `generate_bill` and `render_pdf`. It SHALL NOT
   write bill files.
3. THE user MAY choose scenarios, seeds and styles with command-line options. The same options
   SHALL always give the same bills.
4. EACH bill SHALL carry: `bill_id`, `scenario`, `style` (the layout), the PDF bytes, and the
   ground truth (`line_items`, `price_references`, `quantity_limits`, `bundle_pairs`,
   `expected_flags`).
5. THE harness SHALL NOT read, cache or write anything under `/private`. A path under
   `/private` given as `--out` or `--cache-dir` SHALL be refused with a clear message.

### R2 — Extraction accuracy
**User story:** As the team, we see how well extraction reads a bill.

Acceptance criteria:
1. FOR each bill THE harness SHALL call `backend.extract.handler.extract` with the PDF
   (`application/pdf`) and the model client.
2. EXTRACTED lines SHALL be matched to ground-truth lines **one to one** by a deterministic
   rule (see design). Line ids are not compared, because the model chooses its own ids. The
   match SHALL NOT depend on the order of the extracted lines.
3. THE harness SHALL report: **line recall** (truth lines matched), **line precision**
   (extracted lines that matched), and for matched lines the exact-match rates for **code**,
   **units** (`quantity`), **charge** (`billed_amount`) and **date of service**.
4. THE harness SHALL report the **hallucinated-code count**: matched lines where the truth has
   no code and the model returned one. The target is zero.
5. THE harness SHALL report **confirmation recall**: of the truth lines with no code, how many
   were marked `needs_confirmation`.
6. THE harness SHALL report how many bills ended in the extraction fallback (the model failed
   or its output was unusable).
7. FOR the `injection` scenario THE harness SHALL also report the number of **extra lines**
   (lines not in the truth). The target is zero: instruction-like text in a bill must stay
   inert data.
8. A rate with nothing to measure (for example, units when no truth line has units) SHALL be
   shown as `n/a`, never as a number and never as an error.

### R3 — Flag catch rate and false positives
**User story:** As the team, we see whether a bill read by the model still gets the right
flags.

Acceptance criteria:
1. FOR each bill THE harness SHALL run `core.analyze` on the **extracted** lines with the
   bill's own `price_references`, `quantity_limits` and `bundle_pairs`.
2. EXTRACTED flags SHALL be mapped back to truth line ids through the same line match as R2.
   A flag on an extracted line that has no truth match counts as a false positive.
3. THE harness SHALL report, per flag type: planted (expected) flags, caught flags, and the
   **catch rate**.
4. THE harness SHALL report **false positives**: flags that are not in `expected_flags`. It
   SHALL report the **false-positive rate on clean bills** (clean bills with at least one flag,
   divided by clean bills), and the same for "no-issue" bills (`clean` and `injection`).
5. THE harness SHALL also run `core.analyze` on the **truth** lines (the oracle run) and report
   whether it equals `expected_flags` for every bill. This separates a `/core` problem from an
   extraction problem. A mismatch SHALL be reported as a `/core` self-check failure.

### R4 — Explain and letter quality
**User story:** As the team, we see how often the model's wording is good enough to use.

Acceptance criteria:
1. FOR each bill THE harness SHALL run `backend.explain.handler.explain` on the flags that
   `core.analyze` produces from the **truth** lines (so explain is measured apart from
   extraction errors). It SHALL report the **explain fallback rate** (`fallback_count` divided
   by flags).
2. FOR each bill that has flags THE harness SHALL run `backend.letter.handler.generate_letter`
   as a `coding_review` letter with those flags, and report the **letter fallback rate**
   (`used_fallback`). Patient fields SHALL be fixed synthetic values.
3. THE harness SHALL check these **invariants** on every explanation and every letter, and
   count violations: no banned word in text we or the model wrote; the letter draft validates
   against `contracts/letter-draft.schema.json`; every figure in an explanation is in its flag.
   Any violation SHALL be reported as a **hard failure**.

### R5 — Disk cache
**User story:** As the team, reruns are cheap and do not spend money again.

Acceptance criteria:
1. EVERY model call SHALL go through a caching client. A cached reply SHALL be used instead of
   a call when the key matches.
2. THE cache key SHALL be a SHA-256 of: the task name (`extract`, `explain`, `letter`), the
   model name, the **SHA-256 of the bill file bytes**, and a hash of the full request (system
   prompt, content, repair hint, `max_tokens`). A change to the file, the model, or any prompt
   SHALL therefore give a new key (a miss).
3. ONLY successful, non-empty text replies SHALL be cached. A failed call SHALL NOT be cached.
4. THE cache SHALL live in a folder inside `/evals` that ignores itself in git (it holds a
   `.gitignore` with `*`). Cache files SHALL contain the reply, the task, the model name and
   the file hash, and nothing else. They SHALL NOT contain the API key.
5. A damaged cache file SHALL be treated as a miss and replaced. It SHALL NOT crash the run.
6. THE harness SHALL report cache hits and misses.
7. `--cache-only` SHALL answer from the cache only. A miss SHALL act like a failed model call
   (the feature's own fallback runs) and SHALL NOT call the API.
8. `--max-calls N` (default 60) SHALL stop real calls after N. Cache hits do not count. Past
   the limit a call acts like a failed model call. The report SHALL say the budget was hit.

### R6 — Model choice
**User story:** As Sam, I pick the smallest model that passes.

Acceptance criteria:
1. MODEL names SHALL come from the environment (`EXTRACT_MODEL_ID`, `EXPLAIN_MODEL_ID`,
   `LETTER_MODEL_ID`) and the key from `ANTHROPIC_API_KEY`. Nothing is hardcoded.
2. THE report SHALL name the model used for each task, so two runs with two model sets can be
   compared side by side.
3. THE harness SHALL have pass thresholds in one config file (see design), marked as rules of
   thumb. THE report SHALL show pass or fail for each. `--strict` SHALL make the exit code
   non-zero if any threshold fails or any hard failure exists.

### R7 — Report
**User story:** As the team, the results are in one readable table.

Acceptance criteria:
1. THE harness SHALL write a markdown report with: run info (mode, models, corpus size, cache
   hits and misses), the extraction table (overall, by layout, by scenario), the flag table,
   the explain and letter table, the threshold summary, and the list of failures with **bill
   id and layout**.
2. THE report SHALL be deterministic: the same results give the same text. No timestamps, no
   random order.
3. THE report SHALL NOT contain the API key, raw model replies, or patient-like text. It names
   fields and ids only.
4. A fake-oracle run SHALL be labelled "FAKE ORACLE - not a model" at the top.
5. TABLE cells SHALL be escaped so a `|` or a line break cannot break the table.

### R8 — One command
Acceptance criteria:
1. `python -m evals` SHALL run everything and write the report.
2. `--fake` SHALL use the oracle instead of a model (no key, no network). It is for smoke
   tests and for checking the scoring code, not for measuring a model.
3. IF a real run is asked for and `ANTHROPIC_API_KEY` or a model name is missing, and
   `--cache-only` is not set, THEN the harness SHALL print a clear message naming the missing
   variable and exit with code 2. No traceback.
4. THE default report path SHALL be inside `/evals`. `--out` SHALL set another path.

### R9 — Privacy and safety
Acceptance criteria:
1. THE harness SHALL use synthetic bills only. It SHALL NOT log bill text, model replies or the
   API key. Progress output names bill ids and counts only.
2. THE harness SHALL NOT write anywhere except the cache folder and the report path.
3. ERRORS from a model call SHALL carry only the exception type (as in the shared client).

## Non-goals
- No test of a **real** bill. That is a manual step at about hour 5 (kept in `/private`,
  never committed, deleted afterwards). The harness refuses `/private` paths on purpose.
- No new flags, and no change to `/core`, `/synthetic` or `/contracts`.
- No scan or phone-photo bills: the synthetic PDFs are clean text PDFs, so extraction results
  are an **optimistic** bound. The README says so.
- No automatic model switching. Comparing models means running the command once per model
  set.

## Dependencies
- `/synthetic` (`generate_bill`, `render_pdf`, `SCENARIOS`, `STYLES`) and `core.analyze` -
  on `main` today.
- `backend.extract`, `backend.explain`, `backend.letter` and the shared `LLMClient`
  (`llm_client.py`). **These are on branches `sam-explain` and `sam-letter`, not yet on
  `main`.** See open decision 1 in the design.
- An Anthropic API key and model names for the first real run (set in the environment).
