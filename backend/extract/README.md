# `/backend/extract` — Bill extraction

Turns an uploaded hospital bill (PDF or image) into validated `LineItem` objects
(from `/contracts`) plus bill-level metadata (hospital name, statement date, total).

The model does **extraction only**. It never produces flags (that is `/core`) and
**never guesses billing codes** — an uncertain code becomes `code=null` with the line
marked for user confirmation. Every model output is validated against the canonical
`/contracts/line-item.schema.json`; lines that fail validation are dropped, never
returned.

## Design in one paragraph
An `LLMClient` (see `llm_client.py`) is injected into the handler. For dev and tests,
use `FakeLLMClient`, which is deterministic and offline. The real client
(`make_client()`) calls the Anthropic Messages API directly. It reads the API key and
the model name from environment variables, and imports the `anthropic` package lazily.
The bill is sent as a base64 image or document block, separate from our instructions,
so text inside a bill is data and never an instruction. Model output is validated (`validate.py`) against
the contract, retried once on failure, then post-processed (normalization, code and
confidence rules). Confidence and `needs_confirmation` are carried in an extraction
wrapper (`ExtractionResult`), **not** added to the shared `LineItem` contract.

## Environment variables
| Variable | Required | Purpose |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | Yes (real client only) | Anthropic API key. Secret: never hardcode, commit, or log it. `make_client()` raises `ConfigError` if unset. |
| `EXTRACT_MODEL_ID` | Yes (real client only) | Anthropic model name. Never hardcoded. `make_client()` raises `ConfigError` if unset. |

The fake client needs neither. No other configuration. Thresholds live in `config.py`.

## Privacy
Bill bytes, request bodies, responses, and extracted line content are **never** logged
or written to disk. The API key is never logged. Validation and error messages
reference field names and rule names only, never the offending values. A failed model
call raises an error that carries only the exception type.

## Running tests
Tests run fully offline with the fake client. They need no network, no API key, and no
`anthropic` package (the real client is tested with a stand-in module).

```bash
# from the repo root
python3 -m pip install -r backend/extract/requirements-dev.txt
python3 -m pytest backend/extract/tests -q
```

`requirements-dev.txt` pins `anthropic` for the real client. You only need it to make
real calls, not to run the tests.

Property-based tests use Hypothesis (e.g. "every returned line validates against the
contract"). See `.kiro/specs/backend-extract/design.md` for the full test-case list.

## Status
Work in progress. See `.kiro/specs/backend-extract/tasks.md` for the task checklist.
