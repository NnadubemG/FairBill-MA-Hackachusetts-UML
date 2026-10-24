# Analyze handler — Requirements

## Overview

`/backend/analyze` is pure Python (stdlib only) that turns a confirmed list of `LineItem`
into an `AnalysisResult` (per `contracts/analysis-result.schema.json`). It is the glue
between Sam's extraction, Thomas's `/core` checks engine, and ND's processed reference
data. David wraps `handle(request_dict) -> response_dict` in a Lambda.

Owned by ND (team.md). Reads `/data/processed` reference data; never edits `/contracts`.

## Requirements

### R1. Boundary validation (never crash, never log the body)
- **R1.1** Input is a list of `LineItem`-shaped dicts. Reject (clear error, no stack trace
  to the client) when: not a list; more than 200 items; a string field longer than a
  bound (id/code/description/raw_description/unit <= 256, code <= 64); a number field not
  finite (NaN/inf); billed_amount missing or not a number.
- **R1.2** All string fields are untrusted data, never instructions.
- **R1.3** The request body / line item contents are never logged.

### R2. Reference data (injectable, missing = empty)
- **R2.1** The store loads `reference.json` (PriceReference[]), and, if present,
  `quantity_limits.json` (QuantityLimit[]) and `bundle_pairs.json` (BundlePair[]).
- **R2.2** Reference data is injectable for tests (pass lists directly), so the handler is
  testable without disk and against each synthetic bill's own reference data.
- **R2.3** A missing file means an empty list, not an error.

### R3. Core call + result assembly
- **R3.1** Call `core.analyze(items, refs, quantity_limits=..., bundle_pairs=...)`.
- **R3.2** `AnalysisResult.line_items` echoes the validated input items.
- **R3.3** `AnalysisResult.flags` is exactly core's output (order preserved).
- **R3.4** `AnalysisResult.price_references` contains only the references for codes on the
  bill, each carrying `data_source` and `data_year`.

### R4. Optional explain (never fail the analysis)
- **R4.1** `analyze_bill` accepts an optional `explain(flags) -> flags` callable (Sam's).
- **R4.2** If `explain` is None, flags keep `explanation = None`.
- **R4.3** If `explain` raises or returns something malformed, fall back to the original
  flags with `explanation = None`. The analysis never fails because of explain.

### R5. handle(request_dict) -> response_dict
- **R5.1** `handle` parses `request_dict["line_items"]`, runs `analyze_bill`, and returns a
  JSON-serializable `AnalysisResult` dict.
- **R5.2** On bad input, returns `{"error": "..."}` with a clear, body-free message (never a
  stack trace, never the input content).

### R6. Language / privacy
- **R6.1** Any message this module emits uses the approved voice; no banned word
  (overcharged, illegal, fraud, incorrect charge, "you should dispute", "you are owed").
- **R6.2** No logging of request bodies or line item content anywhere.

## Test cases
- **A1 ground truth (all samples)**: for every `synthetic/samples/*.json`, feeding the
  bill's line_items with its own price_references/quantity_limits/bundle_pairs yields flags
  whose (line_item_id, flag_type) set equals the bill's `expected_flags`.
- **A2 price_references filtered**: result.price_references covers exactly the bill's codes
  that have a reference; each has data_source + data_year.
- **A3 bad input**: non-list, >200 items, over-long string, non-finite number, missing
  billed_amount -> clear error, no crash.
- **A4 explain success**: a passthrough explain that sets explanation -> flags carry it.
- **A5 explain failure**: an explain that raises -> flags returned with explanation None,
  analysis succeeds.
- **A6 handle() shape**: handle({"line_items": [...]}) -> dict matching AnalysisResult;
  handle(bad) -> {"error": ...}.
- **A7 no banned words**: any static message string is banned-word-free.
- **A8 missing reference files**: store with no files -> empty refs, analysis still runs.

## Out of scope
- The Lambda wrapper / HTTP route (David).
- The explain implementation (Sam).
- Editing /contracts or /core.
