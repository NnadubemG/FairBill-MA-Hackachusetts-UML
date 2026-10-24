# Reference Stage — Tasks

- [ ] 1. config + reference stage
  - Add `REFERENCE_JSON` to config. Create `pipeline/stages/reference.py` with pure
    `build_reference(procedures, medicare, prices, ...)` + a `write_reference(...)` that
    loads the processed files and writes reference.json.
  - _Requirements: R1, R2, R3, R4_

- [ ] 2. tests for the stage
  - RF1-RF6, RF6b, RF10 against in-memory inputs.
  - _Requirements: R1-R4_

- [ ] 3. extend validate.py + tests
  - `_check_reference`; wire into `validate()`; tests RF7, RF8, RF9 + a clean pass.
  - _Requirements: R5_

- [ ] 4. log + verify
  - kiro-log line; run full suite; confirm green.
