# Tasks — Bill Extraction (`/backend/extract`)

Small tasks, one unit of work each. Do one or two at a time. Each lists the
requirements it covers and the tests that prove it.

- [x] 1. Scaffold package + config + wrapper types
  - Create `/backend/extract/` package (`__init__.py`).
  - `config.py`: read `EXTRACT_MODEL_ID`, `AWS_REGION`, outlier/confidence thresholds.
  - `models.py`: `LineConfidence`, `BillMetadata`, `ExtractionResult` (compose the
    contract `LineItem`; do not redefine it).
  - _Requirements: R1.2, R1.3_

- [x] 2. Fake + real Bedrock client behind a Protocol
  - `bedrock_client.py`: `BedrockClient` Protocol, `FakeBedrockClient` (scripted,
    offline, deterministic by input hash), `make_client()` reading `EXTRACT_MODEL_ID`.
  - Unit test T12 (env var required / clear error).
  - _Requirements: R1.1, R1.2, R1.4_

- [x] 3. Schema loader + contract validator
  - `schema.py`: load `/contracts/line-item.schema.json`, expose the model output
    shape.
  - `validate.py`: validate a line against the schema; return valid lines + errors.
  - Confirm `jsonschema` availability first; add stdlib fallback if we cannot add it.
  - Unit test P1 (only valid lines returned).
  - _Requirements: R3.1, R3.4_

- [x] 4. Prompt builders with untrusted-data framing
  - `prompts.py`: short system prompt (untrusted data, never guess codes) + user
    content builder (document block + required JSON schema).
  - Unit test T7 (injected instruction line is not acted on).
  - _Requirements: R5.1, R5.2, R5.3_

- [x] 5. Post-processing: normalization + merge
  - `postprocess.py`: money -> number, dates -> ISO, merge continuation rows.
  - Unit tests T10, T11.
  - _Requirements: R4.1, R4.2_

- [x] 6. Post-processing: code + confidence rules
  - Unknown code -> null + low + needs_confirmation; known-code check vs
    procedures.json; missing procedures.json -> skip + warning.
  - Unit tests T2, T3, T4; property tests P2.
  - _Requirements: R2.1, R2.2, R2.3, R2.4, R4.3, R4.4_

- [ ] 7. Handler orchestration + validation retry
  - `handler.py`: wire client -> validate -> retry once -> postprocess ->
    `ExtractionResult`.
  - Unit tests T1, T5, T6, T8.
  - _Requirements: R1.3, R3.2, R3.3_

- [ ] 8. Deterministic fallback + privacy
  - Catch expected model failures -> empty lines + warning, never raise.
  - No disk writes, no logging of bodies/content.
  - Unit test T9; property test P3; privacy assertion PR1.
  - _Requirements: R6.1, R6.2, R7.1, R7.2_

- [ ] 9. Wire test cases end to end + fixtures
  - Add remaining property tests (P4) and a small fixtures module of scripted model
    outputs (no real bill data).
  - Confirm the full suite runs offline with the fake client.
  - _Requirements: R1.4, all_
