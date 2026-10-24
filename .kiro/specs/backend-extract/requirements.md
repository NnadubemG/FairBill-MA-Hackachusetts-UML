# Requirements — Bill Extraction (`/backend/extract`)

## Overview
Given an uploaded hospital bill (PDF or image, already size-limited by the frontend),
return a list of `LineItem` objects (from `/contracts`) plus bill-level metadata
(hospital name, statement date, total). The model does extraction only; it never
produces flags and never guesses billing codes.

Owner: Sam. Scope is limited to `/backend/extract`. This spec does not change
`/contracts`, `/core`, or any other owner's area.

## Contract reality (source of truth note)
The committed `/contracts/line-item.schema.json` is canonical and **has no
`confidence` or `needs_confirmation` field**. The team build guide (a plan, not the
contract) assumed those fields. Per `tech.md` ("All shared types come from
/contracts. Do not redefine them"), this spec will **not** add fields to `LineItem`.

Instead, extraction returns a wrapper object that carries the contract `LineItem[]`
unchanged, plus a parallel per-line confidence signal and bill-level metadata. This
keeps Thomas's contract backward compatible and unblocks work now. If the team later
decides `confidence`/`needs_confirmation` belong on `LineItem`, that is a contract
change Thomas makes and announces.

## Glossary
- **Untrusted bill text** — every string that originates from the uploaded document.
  It is data, never an instruction to the model.
- **Deterministic fallback** — behavior the handler produces with no model call, so
  the feature degrades safely when Bedrock is unavailable or returns invalid output.

## Requirements

### R1 — Structured extraction from a bill
**User story:** As a patient, I upload my bill and the system returns structured line
items, so I can review and confirm them.

Acceptance criteria (EARS):
1. WHEN the handler receives a bill (PDF or image bytes + content type) THEN it SHALL
   call Claude on Amazon Bedrock using a vision-capable model and request structured
   output shaped by `/contracts/line-item.schema.json`.
2. THE handler SHALL read the Bedrock model id from an environment variable
   (`EXTRACT_MODEL_ID`) and SHALL NOT hardcode any model id.
3. THE handler SHALL return an `ExtractionResult` containing: `line_items`
   (contract `LineItem[]`), `metadata` (hospital name, statement date, total; each
   nullable), `line_confidence` (per `line_item.id`), and `warnings` (string list).
4. WHERE the Bedrock client is not yet configured with a real model, THE handler
   SHALL use a fake Bedrock client (injected dependency) so the pipeline runs end to
   end without network access.

### R2 — Never guess codes
**User story:** As the team, we must never let the model invent a billing code, so
downstream price checks are trustworthy.

Acceptance criteria (EARS):
1. WHEN the model returns a line with no code, or a code it is not confident about,
   THEN the handler SHALL set `code=null` and `code_system=null` on that `LineItem`.
2. WHEN a line has `code=null` THEN its `line_confidence` SHALL be `"low"` and
   `needs_confirmation` SHALL be `true`.
3. WHEN a line has a non-null `code` that is NOT present in
   `/data/processed/procedures.json` THEN the handler SHALL keep the code as printed
   but set that line's `needs_confirmation` to `true`.
4. IF `/data/processed/procedures.json` is absent (ND has not produced it yet) THEN
   the handler SHALL skip the known-code check, SHALL NOT error, and SHALL record a
   warning that code validation was unavailable.

### R3 — Validate every model output against the contract
**User story:** As the team, we validate all model output, so malformed data never
reaches the user.

Acceptance criteria (EARS):
1. WHEN the model returns output THEN the handler SHALL validate every line against
   `/contracts/line-item.schema.json` before returning it.
2. IF validation fails THEN the handler SHALL retry the model once, including the
   validation error message in the retry prompt.
3. IF the retry still fails validation THEN the handler SHALL return only the lines
   that validated AND SHALL add a bill-level warning describing what was dropped.
4. THE handler SHALL never return a `LineItem` that does not validate against the
   schema.

### R4 — Confidence and confirmation post-processing
**User story:** As a patient, lines the system is unsure about are marked for my
review, so I know what to double-check.

Acceptance criteria (EARS):
1. THE handler SHALL normalize money fields to numbers (strip `$`, commas) and dates
   to ISO 8601 (`YYYY-MM-DD`).
2. WHEN two or more extracted lines are fragments of one logical line (continuation
   rows) THEN the handler SHALL merge them into a single `LineItem`.
3. WHEN a line's model confidence is below `"high"` THEN the handler SHALL set that
   line's `needs_confirmation` to `true`.
4. THE per-line confidence signal SHALL be one of `"high" | "medium" | "low"`.

### R5 — Treat bill text as untrusted data
**User story:** As the team, we must ignore instructions hidden in a bill, so a bill
cannot hijack the model.

Acceptance criteria (EARS):
1. THE handler SHALL include a system instruction stating that all document text is
   data and never an instruction to the model.
2. WHEN a bill contains text resembling an instruction (e.g. "ignore previous
   instructions") THEN the handler SHALL still extract line items normally and SHALL
   NOT act on that text.
3. THE handler SHALL NOT pass raw bill text into any other tool call or downstream
   service as instructions.

### R6 — Privacy
**User story:** As a patient, my bill is not stored or logged, so my data stays
private.

Acceptance criteria (EARS):
1. THE handler SHALL NOT write the uploaded bill, request body, or any extracted
   content to disk beyond the lifetime of the request.
2. THE handler SHALL NOT log request bodies, uploaded bytes, or extracted line
   content. Logging is limited to error type and non-content diagnostics.

### R7 — Deterministic fallback
**User story:** As a patient, the app still responds if the model call fails, so I am
never left with a crash.

Acceptance criteria (EARS):
1. IF the Bedrock call raises (network, throttling, auth) THEN the handler SHALL
   return an empty `line_items` list with a bill-level warning that automatic
   extraction was unavailable and the user can enter lines manually.
2. THE fallback path SHALL NOT raise out of the handler for an expected model
   failure.

## Non-goals
- No flag production (that is `/core`, Thomas).
- No plain-language rewriting (that is `/backend/explain`, later Sam spec).
- No persistence, no database, no analytics.
- No change to `/contracts`.

## Dependencies
- `/contracts/line-item.schema.json` (exists).
- `/data/processed/procedures.json` (ND; optional — handler degrades without it).
- Real Bedrock model id from David (pending; fake client used until then).
