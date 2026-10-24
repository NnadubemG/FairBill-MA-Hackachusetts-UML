# FairBill MA: how we built it with Kiro (draft)

> Draft built only from `docs/kiro-log.md` and the `.kiro/` folders (steering, specs, hooks).
> Anything those sources do not say is marked `[NEEDS INPUT from <name>]`. Nothing is guessed.

## 1. What we built

FairBill MA is a free, no-login web tool for adult patients in Massachusetts. A patient uploads a
hospital bill, confirms the extracted line items, and gets plain-language labels, Medicare reference
prices, Massachusetts hospital price ranges, and "may be worth asking about" flags, each with a reason
and a data basis. They can also generate an editable letter draft. Nothing is stored.
(Source: `.kiro/steering/product.md`.)

Rules we wrote into steering so every Kiro session followed them:
- The tool is guidance, not legal or medical advice.
- Flags never use words like "overcharged", "illegal", or "fraud". They say "may be worth asking about" and give the reason.
- Every price figure carries a `data_source` and `data_year`; numbers are never invented.
- Flags come from deterministic code. The LLM only extracts, rewrites in plain language, and drafts letters.
- Text inside an uploaded bill is untrusted data, never instructions. User data is never persisted or logged.

`[NEEDS INPUT from Thomas]` Hackathon name, track, and the one-sentence pitch to use in the submission.

## 2. How we used Kiro

**Steering (always-on project rules).** Five files in `.kiro/steering/`: `product.md`, `tech.md`,
`structure.md`, `testing.md`, and `team.md`. Four people each ran their own Kiro session, so steering
was the shared contract: who owns which folder, what the safety rules are, and what tests every check
needs. `team.md` records the ownership table, the interfaces between people, and the handoff times.

**Specs (requirements, design, tasks).** There are 8 specs in `.kiro/specs/`, 60 tasks in total, all
marked done:

| Spec | Owner | Tasks |
|---|---|---|
| `pipeline` | ND | 16 |
| `backend-extract` | Sam | 9 |
| `compare` | ND | 7 |
| `compare-charts` | ND | 6 |
| `reference` | ND | 4 |
| `core-checks` | Thomas | 6 |
| `core-checks-v2` | Thomas | 6 |
| `synthetic-bills` | Thomas | 6 |

Our workflow rule was to list the test cases in the design document before generating tasks, then
work one or two small tasks at a time. The log shows this was followed for the pipeline, extraction,
and core specs.

**Hooks (script-based, no model credits).** Two hooks in `.kiro/hooks/`, both plain Python scripts:
1. A `PreToolUse` guard that blocks a file write if it puts banned wording into product-facing code or
   copy, or if it adds `.kiro` to a `.gitignore`. It was checked against 14 manual cases.
2. A `PostTaskExec` hook that runs the full test suite after a spec task completes.

`tech.md` records why: prefer script-based hooks over model-based hooks to save credits.

**Property-based testing.** `testing.md` requires every check to have example tests plus Hypothesis
properties (no banned words, numbers carry provenance, empty bill gives no flags, order independence,
determinism, and fail-safe on missing data). The properties found real bugs (section 3).

`[NEEDS INPUT from Thomas]` Which Kiro features beyond steering, specs, and hooks were used (for example
vibe sessions, autopilot versus supervised mode, MCP), and how they helped. Not recorded in the log.

## 3. What the tests and specs caught

All of these are recorded in `docs/kiro-log.md`:

- **A contract mismatch, caught while writing a spec (Sam).** The PDF plan assumed `LineItem` had
  `confidence` fields that the committed contract did not. Sam kept `/contracts` backward compatible by
  adding an extraction wrapper instead of changing the contract.
- **A wording bug in a flag template (Thomas).** A test showed one template said "worth asking the
  hospital" instead of the approved "may be worth asking about". Fixed.
- **A banned word reaching a patient (Thomas).** A property test found that a bill code of `FRAUD` passed
  validation and was printed inside a flag. Codes containing a banned word are now treated as unusable.
- **A vacuous test (Thomas).** The first version of the quantity and unbundling properties passed, but a
  count showed the new flags appeared in 0 of 400 random runs. We added generators that usually match,
  plus tests that fail if the generators ever stop triggering the flags.
- **A crash the stronger test then found (Thomas).** `analyze` raised an error when two matching records
  existed and one had no `data_year`. It is meant to never raise. Fixed, with a regression test.
- **A path bug in our own hook (Thomas).** Testing the guard showed that stripping `./` removed the leading
  dot from `.kiro/` paths.
- **Line endings would corrupt the sample PDFs.** One machine rewrites line endings, so we added
  `.gitattributes` rules to keep the samples byte-identical.

## 4. Working as four people in parallel

- Each person owned separate folders (`team.md`): Thomas owns `/contracts`, `/core`, `/synthetic`,
  steering, hooks, and docs; Sam owns the AI features; ND owns the data pipeline, compare API, and charts;
  David owns AWS and the front end.
- `/contracts` is JSON Schema (canonical) with TypeScript and Python mirrors. Changes were additive and
  announced in the log (for example `date_of_service`, `Flag.explanation`, `SyntheticBill`,
  `QuantityLimit`, `BundlePair`).
- Process problems we hit and fixed: parallel git commands once committed to `main` instead of a feature
  branch; the shared log conflicted on almost every merge until we added `docs/kiro-log.md merge=union`
  to `.gitattributes`.

## 5. Results

- **Tests.** 329 tests pass in the default suite (`/core`, `/synthetic`, `/pipeline`, `/backend/compare`),
  plus 103 for `/backend/extract` and 23 Node tests for the charts (per ND's log).
- **Deterministic checks.** `/core` produces six kinds of flag: price above reference, price outside the
  Massachusetts range, duplicate line, quantity above a typical maximum, possible unbundling, and no
  reference price on file. It uses only the standard library and `/contracts`: no network, no file access,
  no randomness.
- **Synthetic bills with ground truth.** `/synthetic` generates fictional bills in 8 scenarios as JSON,
  text, and PDF. A property test runs `/core` on every generated bill (seeds 0 to 10,000) and it matches the
  expected flags exactly. A human opened sample PDFs in a viewer and confirmed they display correctly.
- **Cross-team check.** ND's reference stage fed into `/core` reproduced the generator's ground truth on 360
  bills with 0 mismatches. The input was fictional data, not real data.
- **Pipeline.** `python -m pipeline.run all` runs all 7 stages in order once real files are in `/data/raw`.

`[NEEDS INPUT from David]` Public URL, what runs on AWS, and whether the end-to-end flow works on the live URL.
`[NEEDS INPUT from Sam]` Explain and letter handlers, eval results, and which Bedrock model was used.
`[NEEDS INPUT from ND]` Which real hospital price files were processed, and how many procedures and hospitals.
`[NEEDS INPUT from Thomas]` Video link and a demo walkthrough script.

## 6. Limits we are upfront about

- Everything tested so far uses fictional data. Real processed files have not yet been run through `/core`.
- The multiple of the Medicare price that triggers a flag (`3.0`) is a placeholder, marked to tune once real
  data is seen.
- The Medicare locality code used by the pipeline (`10112`) is a placeholder to confirm against the real file.
- No independent PDF validator was available; PDF validity was checked by our own tests and by a person.
- The quantity and unbundling checks need data that the pipeline must supply (`QuantityLimit`,
  `BundlePair`); until it does, `/core` simply returns no such flags.
- `[NEEDS INPUT from Sam]` The log notes a real Bedrock model id was still pending from David.

## 7. What we would do next

`[NEEDS INPUT from Thomas]` The team's own list. The log suggests: tune thresholds on real data, wire the
quantity and unbundling data into the pipeline, and confirm the Medicare locality.
