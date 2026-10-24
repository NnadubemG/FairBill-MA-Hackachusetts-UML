# Tasks — Plain-Language Explanations (`/backend/explain`)

Small tasks. Do one or two at a time. Each lists the requirements it covers and the
tests that prove it. Stay inside `/backend/explain` (and, only if open decision 2 is B,
one small change in `/backend/extract/llm_client.py`).

- [x] 1. Scaffold package, config, result type, contract shim
  - `__init__.py`, `config.py` (`EXPLAIN_MODEL_ID`, `ANTHROPIC_API_KEY`, `MAX_FLAGS_PER_CALL`,
    `MAX_WORDS`, `BANNED_WORDS`), `models.py` (`ExplainResult`), `_contracts.py` (re-export
    `Flag`).
  - Test E21 (banned list matches core).
  - _Requirements: R1.4, R2.1, R4.1_

- [x] 2. Checks: banned words, figures, sentence shape, `accept`
  - `checks.py`, pure functions.
  - Tests E2, E3, E4, E5, E6, E7, E8; properties P1 and P5 (on `accept`).
  - _Requirements: R2.3, R2.4, R3.1, R3.2, R4.1_

- [x] 3. Fallback templates
  - `templates.py`: `fallback(flag)`, six types plus generic, banned-word guard.
  - Tests E17, E18, E22; properties P4, P6.
  - _Requirements: R4.4, R5.1, R5.2, R5.5, R5.6_

- [ ] 4. Prompt builder and response parser
  - `prompts.py`: short system prompt, batch user content (four fields per flag), parse
    `{"explanations":[...]}` into `key -> text`, ignore unknown keys.
  - Tests E12, E19.
  - _Requirements: R4.3, R6.1, R6.2, R8.1_

- [ ] 5. Handler with one batched call
  - `handler.py`: `explain(flags, *, client)`: cap, one call, per-flag accept or fallback.
  - Tests E1, E11, E13, E14, E15, E16; property P2.
  - _Requirements: R1.1, R1.2, R1.3, R1.5, R2.1, R2.2, R3.3, R5.4, R8.2_

- [ ] 6. Failure fallback and privacy
  - Catch every error in the model path. All flags use the fallback. No logging of content.
  - Tests E9, E10, E20; properties P3; privacy PR1.
  - _Requirements: R5.3, R6.3, R7.1, R7.2, R7.3_

- [ ] 7. Model id wiring and README
  - Per open decision 2: add the real client path for `EXPLAIN_MODEL_ID`.
  - `README.md` for `/backend/explain`: what it does, env vars, how to run the tests.
  - Run the whole suite offline.
  - _Requirements: R1.4_
