# `/evals` — Eval harness

Measures how well the AI features work, on Thomas's synthetic bills (they carry ground truth).
One command runs everything and writes a markdown report.

```
python -m evals --fake                    # offline smoke test, no key, no network
python -m evals                           # real run (needs the key and 3 model names)
python -m evals --cache-only              # replay from the disk cache, never call a model
```

## What it measures
For each bill (one per scenario and layout, as PDFs; today 8 scenarios x 2 layouts = 16 bills):

| Stage | What is checked |
| --- | --- |
| Extraction | Lines matched to the true lines. Recall, precision, exact code / units / charge / date. Hallucinated codes (target 0). Extra lines on the `injection` bill (target 0). |
| Flags | `core.analyze` on the *extracted* lines. Catch rate per flag type, false positives, false-positive rate on clean bills. |
| `/core` self-check | `core.analyze` on the *true* lines must equal `expected_flags`. A mismatch points at `/core` or `/synthetic`, not at extraction. |
| Explain | How often the model's wording was accepted, and how often the fixed fallback was needed (judged on flags from the true lines). |
| Letter | The same for the letter's reason paragraph (a coding review of those flags). |
| Invariants | Hard failures: banned word, invented figure, invalid letter draft, unknown line id. |

Failures are listed with the **bill id and the layout** (`plain` or `messy`).

## Real run
```bash
python3 -m pip install -r backend/extract/requirements-dev.txt   # pinned versions
export ANTHROPIC_API_KEY=...        # secret: never commit it, never paste it into a file
export EXTRACT_MODEL_ID=...         # the model names come from the environment
export EXPLAIN_MODEL_ID=...
export LETTER_MODEL_ID=...
python -m evals --out evals/results/run-small.md
```
A full run is about 40 model calls today: one extract call per bill, plus one explain and one letter call per bill that has flags. `--max-calls` (default 60)
stops real calls after N; cache hits do not count. If anything is missing the command prints
the variable names and exits with code 2.

## Using a `.env` file
`python -m evals` reads a `.env` file in the repo root. You can use it instead of `export`.

1. Copy the example: `cp .env.example .env`
2. Open `.env` in your editor and type your values after the `=`. Do not paste the key anywhere else.
3. Run `python -m evals`.

Rules:
- `.env` is ignored by git. `.env.example` is tracked and has no values. Never put a real key in `.env.example`.
- A variable that is already set in your shell wins over the file. A blank value in the file is skipped.
- Format: `NAME=value` per line. `export NAME=value`, quotes and `#` comments also work.
- The loader (`backend/envfile.py`) uses only the standard library. It never prints, logs or stores a value.
- Only the real command (`python -m evals`) reads `.env`. The tests never do.
- A real run starts with one check line, for example `ANTHROPIC_API_KEY: length 40, ends with ...abcd`. It shows only the length and the last 4 characters. A key shorter than 12 characters shows the length only.

## The cache
Every model call goes through a disk cache in `evals/.cache/`. The key is a SHA-256 of the
task, the model name, the **SHA-256 of the bill file**, and the whole request (system prompt,
content, repair hint, `max_tokens`). So:

- a rerun costs nothing;
- editing a prompt, changing the model, or changing the bill gives a new key (a miss);
- failed calls and empty replies are never cached;
- the folder has its own `.gitignore` (`*`), so it is never committed. Deleting it is safe.

Cache files hold only the task, model name, file hash and reply (synthetic bills only).

## Picking the smallest model that passes
The report prints pass or fail against the thresholds in `evals/config.py` (rules of thumb:
for example code and units at least 95%, charge at least 98%, no hallucinated codes, no false
positives on clean bills, explain fallback at most 25%). To compare models, run the command
once per model set with its own report file:

```bash
EXTRACT_MODEL_ID=small ... python -m evals --out evals/results/run-small.md
EXTRACT_MODEL_ID=big   ... python -m evals --out evals/results/run-big.md
```
The model name is part of the cache key, so the two runs never mix. Choose the smallest model
whose report has no FAIL. Use `--strict` to make the exit code 1 when a threshold fails. A hard
failure (an invariant violation) always exits 1.

## Fake runs
`--fake` answers from the ground truth (the "oracle"). It tests the harness and the scoring, not
a model, and the report says so at the top. It writes to `evals/results/fake-run.md` (ignored by
git) so fake numbers can never overwrite a real report. In a fake run the row "Real model
calls" counts the oracle's answers.

## Options
```
--fake  --cache-only  --max-calls N  --strict
--scenarios a,b   --seeds 1,2   --styles plain,messy
--out PATH        --cache-dir PATH
```
Exit codes: 0 ok; 1 hard failure, or a failed threshold with `--strict`; 2 setup problem.

## Limits (read these before trusting a number)
- **Optimistic extraction.** The synthetic PDFs are clean text PDFs. A scan or a phone photo
  will do worse. The real redacted bill test at about hour 5 is still a manual step: keep that
  bill in `/private`, never commit it, delete it afterwards. This harness **refuses** any
  `--out` or `--cache-dir` inside `/private`, on purpose.
- **No uncoded lines in the corpus.** Every synthetic line has a code, so "confirmation recall"
  (uncoded lines marked for confirmation) shows `n/a`, and the rule "never guess a missing code"
  is only tested through the `unknown_code` bill. A scenario with uncoded, summary-style lines
  would close this gap. `/synthetic` is Thomas's folder.
- **One seed by default.** More bills: `--seeds 1,2,3` (more calls).
- **Line matching is a rule of thumb.** One wrong field still matches a line (and lowers that
  field's rate). Two wrong fields count as a missing line plus an extra line.
- Thresholds only decide pass or fail. They do not change any result.

## Privacy
Synthetic bills only. Nothing is written except the report and the cache. Output, the report
and the cache never contain the API key, bill text or model replies beyond the cached reply
files. Errors from a model call carry only the exception type.

## Files
```
config.py        settings, thresholds        corpus.py     bills from /synthetic, /private guard
cache.py         disk cache (file hash)      oracle.py     the fake model
align.py         line matching               score_extract.py / score_flags.py   the scoring
invariants.py    hard-failure checks         run.py        runs one bill / the corpus
report.py        markdown report             __main__.py   the command line
results/         reports                     .cache/       model replies (never committed)
```

## Tests
Fully offline: no network, no key, no `anthropic` install needed.
```bash
python3 -m pytest evals -q
python3 -m pytest evals backend -q      # with extract, explain and letter
```
The root `pytest.ini` lists only some test folders, so name `evals` explicitly.
See `.kiro/specs/evals/design.md` for the full test-case list.
