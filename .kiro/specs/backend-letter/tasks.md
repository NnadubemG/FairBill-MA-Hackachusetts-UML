# Tasks — Letter Drafts (`/backend/letter`)

Small tasks. Do one or two at a time. Each lists the requirements it covers and the tests
that prove it. Stay inside `/backend/letter`. Start only after open decision 1 is settled
(the explain work must be available on this branch).

- [x] 1. Scaffold package, config, wrapper types, contract shim
  - `__init__.py`, `_contracts.py` (re-export `Flag`, `LineItem`, `LetterDraft` from
    `contracts.types`), `config.py` (`LETTER_MODEL_ID`, limits, tone-check word lists),
    `models.py` (`LetterType`, `PatientFields`, `LetterRequest`, `LetterResult`,
    `InvalidLetterType`).
  - Tests: types and limits; letter type ids; banned list equals the explain list.
  - _Requirements: R1.1, R1.2, R5.6_

- [x] 2. Patient field cleaning and `parse_request`
  - `request.py`: `clean_field`, `clean_notes`, `parse_request`.
  - Tests L15, L21; property PL8.
  - _Requirements: R2.2, R8.1, R8.2_

- [ ] 3. Facts: safe code, amount, date, and item builder
  - `facts.py`: `safe_code`, `format_amount`, `ItemFact`, `build_items` (skip unknown ids,
    cap at 10, warnings).
  - Tests L10 (build part), L11 (build part), L12.
  - _Requirements: R3.1, R3.2, R3.3, R3.6, R6.1, R6.2_

- [ ] 4. Paragraph checks
  - `checks.py`: tone terms, deadline patterns, figures vs source, implied words, shape,
    first person, `accept_paragraph`.
  - Tests L8 (all cases); property PL2 (on `accept_paragraph`).
  - _Requirements: R3.4, R3.5, R4.1, R4.2, R4.3_

- [ ] 5. Templates and `assemble_body` (no model yet)
  - `templates.py`: subjects, fixed sections, fallback paragraphs, items section, closing,
    placeholders, `assemble_body`.
  - Tests L1, L3 (text part), L4, L5 (template part), L6, L7 (fallback), L16, L18, L19, L22,
    L24;
    properties PL6, PL7.
  - _Requirements: R1.3, R1.4, R2.1, R2.3, R2.4, R2.5, R4.4, R6.3, R7.1, R7.3, R7.4_

- [ ] 6. Prompt builder and response parser
  - `prompts.py`: short system prompt, user content (letter type and per-flag facts only),
    `parse_response` (accepts a fenced reply, never raises).
  - Tests: request has no patient data or descriptions (L5 request part, L17); parser cases.
  - _Requirements: R5.3, R5.5, R5.8_

- [ ] 7. Handler with one model call and fallback
  - `handler.py`: `generate_letter`. Model only for `coding_review` with usable flags, no
    retry, per-paragraph accept or fallback, `referenced_line_item_ids`, contract validation.
  - Tests L2, L3 (no call), L9, L10, L11, L13, L14; properties PL1, PL3, PL4, PL5.
  - _Requirements: R1.1, R1.2, R1.5, R1.6, R5.1, R5.2, R5.4, R7.2_

- [ ] 8. Client wiring and privacy
  - `client.py`: `make_letter_client()` using `LETTER_MODEL_ID`.
  - Tests L20, L23; privacy PR1 (logs, output, warnings, no files).
  - _Requirements: R5.6, R5.7, R9.1, R9.2, R9.3, R9.4_

- [ ] 9. README and full suite
  - `README.md`: what it does, the three letter types, env vars, how to run the tests.
  - Run the whole backend suite offline.
  - _Requirements: all_
