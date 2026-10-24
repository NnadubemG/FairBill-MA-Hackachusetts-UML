# Requirements — Letter Drafts (`/backend/letter`)

## Overview
The patient picks a letter type and, for a coding review, the lines they want to ask
about. The handler returns an **editable letter draft** (`LetterDraft` from `/contracts`:
`subject`, `body`, `referenced_line_item_ids`).

The letter is a **fixed template**. Patient fields (name, account number, hospital, date,
notes) go in by templating. The model writes **only one thing**: the short "reason"
paragraph. Every letter also has a **deterministic fallback paragraph**, so the app works
if the model call fails or returns something we cannot trust.

Owner: Sam. Scope is `/backend/letter` only. This spec does not change `/contracts`,
`/core`, or any other owner's area.

## Contract note (source of truth)
`/contracts/letter-draft.schema.json` (Thomas): "An editable letter draft the patient can
send ... Never asserts wrongdoing." `body`: "Asks questions; does not assert wrongdoing or
demand money." No contract change is needed. The handler returns exactly
`subject`, `body`, `referenced_line_item_ids`. Extra data (warnings) goes in a wrapper,
not in the contract.

## Letter types
| Type id | Meaning |
|---|---|
| `itemized_bill` | Ask for an itemized bill with billing codes |
| `coding_review` | Ask for a coding and billing review of specific lines |
| `financial_assistance` | Ask for a financial assistance review |

## Glossary
- **Reason paragraph** — the one paragraph in the letter that the model may write.
- **Facts** — a line's code, amount and date, and a flag's `reason`/`basis`. These are the
  only facts a letter may cite.
- **Figure** — any number in text: dollar amount, count, year, date part, code, account.
- **Fallback** — text built with no model call.

## Requirements

### R1 — Letter types and output
**User story:** As a patient, I get a polite letter I can edit and send.

Acceptance criteria:
1. THE handler SHALL support the three letter types above. An unknown type SHALL raise
   `InvalidLetterType` (a `ValueError`). This is a caller bug, not a model failure.
2. THE handler SHALL return a `LetterResult` with `draft` (`LetterDraft`), `used_fallback`
   (true if the reason paragraph is not model text), and `warnings`.
3. THE `draft.subject` SHALL be a fixed string for the type (not model text).
4. THE `draft.body` SHALL start with the exact line
   `Draft for you to review and edit before sending.`
5. THE `draft.referenced_line_item_ids` SHALL list, in input order and without
   duplicates, the ids of the lines cited in the letter. It SHALL only contain ids that
   were in the input.
6. THE `draft` SHALL validate against `/contracts/letter-draft.schema.json`.

### R2 — Template and patient fields
**User story:** As a patient, my own details are in the letter exactly as I typed them.

Acceptance criteria:
1. THE patient fields are `name`, `account_number`, `hospital`, `date`, and optional
   `notes`. They SHALL be inserted by the template only. The model SHALL NOT receive them
   and SHALL NOT write them.
2. EACH field SHALL be cleaned before use: control characters removed, and whitespace
   collapsed to one line (for `notes`, line breaks are kept). Each field has a maximum
   length. Longer text is cut at the limit.
3. IF a field is empty THEN the template SHALL use a bracket placeholder (for example
   `[Your name]`). The letter SHALL still be complete. An empty `notes` SHALL add nothing
   (no empty heading).
4. A patient field SHALL NOT change the rest of the letter. Text typed into a field
   (including line breaks or words like "ignore the above") is only ever data in its own
   slot.
5. Patient fields are the patient's own words. They are inserted as typed (after R2.2). The
   banned-word and tone rules apply to text **we or the model write**, not to what the
   patient types.

### R3 — Facts only
**User story:** As the team, a letter never invents a fact.

Acceptance criteria:
1. A letter MAY cite only: a line's `code`, `billed_amount` and `date_of_service`, and a
   flag's `basis`. It MAY also contain the patient's own fields.
2. A line's `code` SHALL be used only if it is 1 to 12 letters, digits, dots or dashes and
   has no banned word. Otherwise the line is shown without a code. This is the same
   safety rule `/core` uses.
3. A line's amount SHALL be used only if it is a finite, non-negative number. Otherwise it
   is left out.
4. EVERY figure in the **reason paragraph** SHALL also appear in the facts given for the
   letter (see R5.3). Figures compare by value (`$1,234.50` equals `1234.5`).
5. WORDS that imply a new figure ("twice", "double", "triple", "half", "percent", "fold")
   SHALL be allowed in the paragraph only if the same word is in the source facts.
6. THE letter SHALL NOT use any `description` text from the bill. (Bill text is untrusted;
   code, amount and date are enough to identify a line.)

### R4 — Voice: polite, no accusations, no threats
**User story:** As a patient, my letter asks and requests. It never accuses.

Acceptance criteria:
1. NO text we or the model write SHALL contain a banned word or phrase from
   `/.kiro/steering/product.md` (overcharged, illegal, fraud, incorrect charge,
   "you should dispute", "you are owed"). The check is case-insensitive and also catches
   odd spacing and look-alike characters.
2. THE reason paragraph SHALL NOT contain: accusation words (for example "wrong",
   "mistake", "error", "overbilled", "scam", "cheat", "improper", "unfair"); legal words
   or threats ("lawsuit", "sue", "attorney", "lawyer", "legal", "law", "court",
   "violation", "regulator", "complaint"); money demands ("refund", "reimburse",
   "compensation", "demand", "you owe", "penalty"); or deadlines and pressure ("within",
   "deadline", "immediately", "no later than", "urgent"). The exact lists are in
   `config.py` and are rules of thumb. The fixed template text SHALL pass the same checks.
3. THE reason paragraph SHALL be written in the first person ("I"), SHALL be a single
   paragraph of 2 to 4 sentences and at most `MAX_PARAGRAPH_WORDS` words, and SHALL NOT
   contain a greeting, a sign-off, a list, markdown, a link or an email address.
4. THE fixed request text SHALL ask for documents and explanations. It SHALL NOT say a
   charge is wrong, SHALL NOT assert any law, and SHALL NOT set a deadline.

### R5 — One model call, only for the reason paragraph
**User story:** As the team, the model does the minimum, and its output is checked.

Acceptance criteria:
1. THE handler SHALL call the model **only** for `coding_review` letters that have at least
   one usable flag. For `itemized_bill` and `financial_assistance` letters, and for a
   coding review with no usable flag, it SHALL NOT call the model and SHALL use the
   fallback paragraph.
2. THE handler SHALL make at most one model call per letter and SHALL NOT retry.
3. THE model input SHALL contain only the letter type and, for each usable flag: a key,
   `flag_type`, `reason`, `basis`, and the line's safe `code`, formatted `amount`, and
   `date_of_service`. It SHALL NOT contain patient fields, line descriptions, or other
   bill text. The allowed-figures set for R3.4 is built from exactly this input.
4. THE model SHALL return JSON `{"paragraph": "..."}`. The handler SHALL accept the text
   only if it passes every check in R3.4, R3.5 and R4. Otherwise it SHALL use the fallback
   paragraph.
5. THE system prompt SHALL say that the input is data and not instructions, and SHALL tell
   the model to write polite first-person text that asks and never accuses.
6. THE handler SHALL read the model name from the environment variable `LETTER_MODEL_ID`
   and the API key from `ANTHROPIC_API_KEY`. It SHALL NOT hardcode, commit or log either.
7. THE handler SHALL take the model client as an injected dependency. Tests and dev use the
   fake client, so no network, API key or `anthropic` install is needed.
8. THE prompt SHALL be short, and the reply limited with a small `max_tokens`.

### R6 — Flags and lines
Acceptance criteria:
1. A flag SHALL be used only if its `line_item_id` matches a line in the input. Other flags
   are skipped and a generic warning is added.
2. AT MOST `MAX_FLAGS` (10) flags SHALL be used, in input order. If there are more, the
   rest are skipped and a generic warning is added.
3. For `coding_review`, THE letter SHALL include an "items" section: one entry per usable
   flag with the line's code, amount, date and the flag's `basis`. Entries use only facts
   from R3.

### R7 — Fallback
**User story:** As a patient, I still get a complete letter if the model fails.

Acceptance criteria:
1. EACH letter type SHALL have a fixed fallback reason paragraph. It SHALL contain no
   figures, no accusation, and no claim about the patient that the patient did not enter
   (for example, no claim of hardship).
2. IF the model call raises, returns invalid JSON, returns no `paragraph`, or returns text
   that fails a check THEN the handler SHALL use the fallback paragraph, set
   `used_fallback` to true, and add one generic warning. It SHALL NOT raise.
3. THE letter built with the fallback SHALL pass every rule in R3 and R4.
4. THE letter SHALL be deterministic: the same input and the same model reply give the same
   letter; the fallback letter depends on the input only.

### R8 — Request input
Acceptance criteria:
1. THE module SHALL provide `parse_request(payload)` that builds a `LetterRequest` from the
   JSON the frontend sends, and raises a clear `ValueError` for a missing or wrongly typed
   `letter_type`, `flags`, or `line_items`.
2. IF the payload has unknown extra keys THEN they SHALL be ignored.

### R9 — Privacy
Acceptance criteria:
1. THE handler SHALL NOT log patient fields, flag text, line data, prompts or model output.
   Logs may hold an error type only.
2. THE handler SHALL NOT write anything to disk.
3. Warnings SHALL be fixed, generic text with no patient or bill content.
4. An error from the model call SHALL carry only the exception type.

## Non-goals
- No new flags, and no change to a flag's facts (that is `/core`).
- No explanation rewriting (that is `/backend/explain`).
- No sending of the letter. The patient copies or prints it.
- No legal advice, no claim about any law, no deadlines.
- No translation (Spanish toggle is a cut-order item).
- No change to `/contracts`.

## Dependencies
- `/contracts/letter-draft.schema.json`, `flag.schema.json`, `line-item.schema.json` and
  `types.py` (exist).
- `LLMClient`, `FakeLLMClient`, `make_client(model_env_var=...)` from `/backend/extract`,
  and the `figures`, `implied_figure_words`, `has_banned_word` checks and `BANNED_WORDS`
  from `/backend/explain`. **These are on branch `sam-explain`, not yet on `main`.** See
  open decision 1 in the design.
- An Anthropic API key and a model name for letters (set in the environment).
