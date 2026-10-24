# Tasks — Eval Harness (`/evals`)

Small tasks. Do one or two at a time. Each lists the requirements it covers and the tests that
prove it. Stay inside `/evals`. Start only after open decision 1 is settled (the extract,
explain and letter code must be available on this branch).

- [x] 1. Scaffold, config, corpus, private-path guard
  - `__init__.py`, `config.py` (env var names, defaults, thresholds, limits), `corpus.py`
    (`Bill`, `build_corpus`, `ensure_not_private`), `results/` and `tests/` folders.
  - Tests S1, S2, S3, S4; thresholds sane.
  - _Requirements: R1, R6.3, R9.2_

- [ ] 2. Disk cache
  - `cache.py`: `CachingClient`, `CacheStats`, `CacheMiss`, `BudgetExceeded`, hashing,
    atomic write, self-ignoring folder.
  - Tests C1 to C13; properties PE6, PE7.
  - _Requirements: R5, R9.1, R9.3_

- [ ] 3. Line matching and extraction scoring
  - `align.py`, `score_extract.py` (metrics, failure records, `n/a` handling).
  - Tests A1 to A12; properties PE1, PE2, PE3, PE4, PE9.
  - _Requirements: R2_

- [ ] 4. Flag scoring
  - `score_flags.py`: map flags through the alignment, per-type catch rate, false positives,
    clean-bill rate, `/core` self-check.
  - Tests F1 to F7.
  - _Requirements: R3_

- [ ] 5. Oracle (fake model) and invariants
  - `oracle.py` (extract, explain, letter replies from the truth), `invariants.py`.
  - Tests X3, oracle replies pass the real handlers; property PE5.
  - _Requirements: R4.3, R8.2_

- [ ] 6. Runner
  - `run.py`: corpus -> extract -> match -> flags -> explain -> letter -> invariants ->
    `RunResult`. Works with `CachingClient` or the oracle.
  - Tests X1, X2, X4, X5, K6 (noisy oracle end to end).
  - _Requirements: R2, R3, R4, R5.7, R5.8_

- [ ] 7. Report
  - `report.py`: tables, threshold summary, failures, escaping, determinism, fake label.
  - Tests R1 to R6; property PE8.
  - _Requirements: R6.2, R6.3, R7_

- [ ] 8. CLI
  - `__main__.py`: options, env checks, exit codes, progress lines, default paths.
  - Tests K1, K2, K3, K4, K5, K7; privacy PR1.
  - _Requirements: R8, R9_

- [ ] 9. README and full suite
  - `README.md`: how to run, env vars, cache, comparing models, limits (optimistic extraction,
    no real-bill step), how to read the report.
  - Run `pytest evals` and `pytest backend`. Print one fake-run report and read it.
  - _Requirements: all_
