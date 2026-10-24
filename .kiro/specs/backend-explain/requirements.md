# Requirements — Plain-Language Explanations (`/backend/explain`)

## Overview
`/core` produces `Flag` objects. Each flag has a `reason` and a `basis` written from
fixed templates. The explain handler adds a plain-language `explanation` to each flag:
about an 8th-grade reading level, 2 to 3 short sentences, ending with one concrete
question the patient could ask the billing office.

The handler makes **one batched model call for all flags**. Every flag also has a
**deterministic fallback template**, so the app works if the model call fails or
returns something we cannot trust.

Owner: Sam. Scope is `/backend/explain` only. This spec does not change `/contracts`,
`/core`, or any other owner's area.

## Contract note (source of truth)
`/contracts/flag.schema.json` (Thomas) already has an optional `explanation` field:
"Plain-language rewrite of reason, written by the explain handler (LLM). /core always
leaves this null. It must not add facts or numbers beyond reason and basis, and must
follow the same language rules (no banned words)."

So the handler returns the same `Flag` objects with only `explanation` filled in. It
never edits `reason`, `basis`, `data_source`, `data_year`, `severity`, `flag_type`, or
`line_item_id`. No contract change is needed.

## Glossary
- **Source text** — a flag's `reason` and `basis`. These come from `/core` templates
  and are the only facts the explanation may use.
- **Figure** — any number in text: a dollar amount, a ratio, a count, a year, a code.
- **Fallback** — an explanation built with no model call.

## Requirements

### R1 — One batched call for all flags
**User story:** As the team, we make one model call per request, so cost and latency
stay low.

Acceptance criteria:
1. WHEN the handler receives a non-empty list of flags THEN it SHALL make exactly one
   model call that contains all of them (up to `MAX_FLAGS_PER_CALL`).
2. IF the list is empty THEN the handler SHALL return an empty list and SHALL NOT call
   the model.
3. IF there are more than `MAX_FLAGS_PER_CALL` flags THEN the first
   `MAX_FLAGS_PER_CALL` go in the single call and the rest SHALL use the fallback.
   The handler still makes at most one model call.
4. THE real client SHALL call the Anthropic Messages API directly. It SHALL read the
   model name from the environment variable `EXPLAIN_MODEL_ID` and the API key from
   `ANTHROPIC_API_KEY`. It SHALL NOT hardcode, commit, or log either value.
5. THE handler SHALL take the model client as an injected dependency. Tests and dev use
   the fake client, so no network, API key, or `anthropic` install is needed.

### R2 — Output shape
**User story:** As a patient, each flag has a short explanation I can read.

Acceptance criteria:
1. THE handler SHALL return `ExplainResult` with `flags` (same length and order as the
   input), `fallback_count`, and `warnings`.
2. Each returned flag SHALL equal the input flag except that `explanation` is set to a
   non-empty string. No other field changes.
3. EACH explanation SHALL be 2 to 3 sentences, and SHALL end with exactly one question
   (the last sentence ends with `?` and no other sentence does).
4. EACH explanation SHALL be at most `MAX_WORDS` words (short by design).

### R3 — Do not change facts or numbers
**User story:** As the team, the model must not add or change a number.

Acceptance criteria:
1. EVERY figure in an accepted explanation SHALL also appear in that flag's source text
   (`reason`, `basis`), or be that flag's `data_year`. Figures compare by value, so
   `$1,234.50` and `1234.5` match.
2. Words that imply a new figure ("twice", "double", "triple", "half", "percent",
   "fold") SHALL be allowed only if the same word appears in the source text.
3. IF an explanation breaks R3.1 or R3.2 THEN that flag SHALL use its fallback. Other
   flags in the same batch keep their model text.

### R4 — Language rules
**User story:** As the team, we never use the banned words.

Acceptance criteria:
1. NO explanation SHALL contain a banned word or phrase from
   `/.kiro/steering/product.md` (overcharged, illegal, fraud, incorrect charge,
   "you should dispute", "you are owed"). The check is case-insensitive.
2. IF an explanation contains a banned word THEN that flag SHALL use its fallback.
3. THE prompt SHALL tell the model to use "may be worth asking about" and never to say
   the hospital did something wrong.
4. THE fallback text SHALL also pass R4.1. IF a flag's own `reason` contains a banned
   word THEN the fallback SHALL NOT copy it. It uses only the fixed generic template.

### R5 — Deterministic fallback per flag type
**User story:** As a patient, I still get an explanation if the model fails.

Acceptance criteria:
1. THE handler SHALL have one fallback template for each of the six flag types
   (`price_above_reference`, `price_outside_ma_range`, `duplicate_line_item`,
   `quantity_implausible`, `possible_unbundling`, `no_reference_found`).
2. A fallback SHALL be built from the flag's own `reason` plus one fixed question for
   its type. It SHALL add no figure that is not in the flag.
3. IF the model call raises, returns invalid JSON, or returns an unusable batch THEN
   EVERY flag SHALL use its fallback and the handler SHALL NOT raise.
4. IF the model omits a flag, or returns a flag key we did not send, THEN the omitted
   flag SHALL use its fallback and the unknown key SHALL be ignored.
5. A flag type we do not know SHALL still get a generic fallback, never an error.
6. THE fallback SHALL be a pure function: the same flag always gives the same text.

### R6 — Bill text is untrusted
**User story:** As the team, a bill cannot steer the model.

Acceptance criteria:
1. THE model input SHALL contain only `flag_type`, `reason`, and `basis` for each flag,
   plus a key. It SHALL NOT contain line item descriptions or any other bill text.
2. THE system prompt SHALL say that the flag text is data, not instructions.
3. Because the model output is checked by R2, R3 and R4, text inside a flag cannot make
   the handler return an explanation that breaks these rules.

### R7 — Privacy
Acceptance criteria:
1. THE handler SHALL NOT log flag text, prompts, or model output. Logs may hold an error
   type only.
2. THE handler SHALL NOT write anything to disk.
3. Warnings SHALL NOT contain flag text.

### R8 — Cost
Acceptance criteria:
1. THE prompt SHALL be short, and the model output limited with a `max_tokens` that
   scales with the number of flags.
2. THE handler SHALL NOT retry the model call. A bad batch goes straight to the
   fallback. (This keeps cost down. The fallback is safe.)

## Non-goals
- No new flags and no change to a flag's facts (that is `/core`).
- No line-item label rewriting. Plain labels come from `plain_label` in ND's
  `procedures.json`.
- No letters (that is `/backend/letter`).
- No change to `/contracts`.
- No guarantee of exact reading grade. We enforce short length and sentence count, not a
  grade-level score.

## Dependencies
- `/contracts/flag.schema.json` and `types.py` (exist).
- `FakeLLMClient` and the `LLMClient` protocol from `/backend/extract`.
- An Anthropic API key and a model name for explain from Sam (set in the environment).
