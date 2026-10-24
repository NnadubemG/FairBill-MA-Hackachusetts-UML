# Kiro log

One line per notable event: a bug a hook caught, a property-test failure, a spec
change. Newest at the bottom.

- 2026-10-24 — Bootstrapped base: steering (product/tech/structure/testing), /contracts (JSON Schema canonical + TS/Python mirrors), README, .gitignore, docs log. Source of truth is JSON Schema.
- 2026-10-24 — Sam: spec `backend-extract` (reqs/design/tasks, test cases listed before tasks). Caught contract mismatch: committed `LineItem` has no `confidence`/`needs_confirmation` (PDF plan assumed them). Chose extraction-wrapper (`ExtractionResult`) over a contract change — keeps `/contracts` backward compatible. Task 1 (scaffold + config + wrapper types) done; model id read from `EXTRACT_MODEL_ID`, never hardcoded.
- 2026-10-24 — Sam: extract task 2 done. `BedrockClient` Protocol + offline deterministic `FakeBedrockClient` (fingerprint/queue/default/raise modes) + `make_client()` real factory (boto3 lazy-imported, model id from `EXTRACT_MODEL_ID`). Added `requirements-dev.txt` (hypothesis/pytest/jsonschema pinned). 9 unit tests pass offline, incl. T12 (model id required).
- 2026-10-24 — Sam: extract task 3 done. `schema.py` loads canonical LineItem JSON Schema (cached) + builds the model output envelope; `validate.py` validates each line, drops invalid ones, reports field/rule only (no bill content). 10 tests incl. property P1 (every returned line is schema-valid). Added `backend/extract/README.md`. Full suite 19 passing offline.
