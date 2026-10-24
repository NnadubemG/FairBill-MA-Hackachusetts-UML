# Tasks: /core checks engine (v1)

Do one or two at a time. Each task ends with: two-sentence summary and what to test.

- [ ] 1. Scaffold and dev tooling
  - Create `core/` package with `constants.py` (MEDICARE_MULTIPLE, severities, BANNED_WORDS).
  - Add `requirements-dev.txt` (`pytest`, `hypothesis`) and `pytest.ini` (`pythonpath = .`).
  - Smoke test that `from core import analyze` works and `analyze([], [])` returns `[]`. (R1, R2, TC-E1)

- [ ] 2. Language and reference lookup
  - `language.py`: code sanitizer, money formatter, templates.
  - `reference.py`: index and lookup rules.
  - Unit tests TC-L1 to TC-L12. (R8, R9)

- [ ] 3. Price checks
  - `checks/price.py` with both flags and per-unit logic.
  - Unit tests TC-P1 to TC-P14. (R3, R4, R5)

- [ ] 4. Duplicates and no-reference
  - `checks/duplicates.py`, `checks/coverage.py`.
  - Unit tests TC-D1 to TC-D8, TC-N1 to TC-N4. (R6, R7)

- [ ] 5. Engine and property tests
  - `engine.py` runs the checks and sorts output.
  - Unit tests TC-E2, TC-E3. Hypothesis tests PR1 to PR11. (R10, R2)

- [ ] 6. Wrap-up
  - Append a line to `docs/kiro-log.md`. Confirm no file I/O or network imports in `core/`.
