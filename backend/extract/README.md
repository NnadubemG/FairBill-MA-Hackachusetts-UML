# `/backend/extract` — Bill extraction

Turns an uploaded hospital bill (PDF or image) into validated `LineItem` objects
(from `/contracts`) plus bill-level metadata (hospital name, statement date, total).

The model does **extraction only**. It never produces flags (that is `/core`) and
**never guesses billing codes** — an uncertain code becomes `code=null` with the line
marked for user confirmation. Every model output is validated against the canonical
`/contracts/line-item.schema.json`; lines that fail validation are dropped, never
returned.

## Design in one paragraph
A `BedrockClient` (see `bedrock_client.py`) is injected into the handler. Until real
model ids arrive, use `FakeBedrockClient`, which is deterministic and offline. The
real client (`make_client()`) reads the model id from an environment variable and is
built with boto3 (lazy-imported). Model output is validated (`validate.py`) against
the contract, retried once on failure, then post-processed (normalization, code and
confidence rules). Confidence and `needs_confirmation` are carried in an extraction
wrapper (`ExtractionResult`), **not** added to the shared `LineItem` contract.

## Environment variables
| Variable | Required | Purpose |
| --- | --- | --- |
| `EXTRACT_MODEL_ID` | Yes (real client only) | Bedrock model id. Never hardcoded. `make_client()` raises `ConfigError` if unset. The fake client needs none. |
| `AWS_REGION` | No | AWS region for the Bedrock runtime client. Defaults to `us-east-1`. |

No other configuration. Thresholds live in `config.py` and are labeled there.

## Privacy
Bill bytes, request bodies, and extracted line content are **never** logged or written
to disk. Validation and error messages reference field names and rule names only,
never the offending values.

## Running tests
Tests run fully offline with the fake client — no network, no AWS credentials, no
`boto3` needed.

```bash
# from the repo root
python3 -m pip install -r backend/extract/requirements-dev.txt
python3 -m pytest backend/extract/tests -q
```

Property-based tests use Hypothesis (e.g. "every returned line validates against the
contract"). See `.kiro/specs/backend-extract/design.md` for the full test-case list.

## Status
Work in progress. See `.kiro/specs/backend-extract/tasks.md` for the task checklist.
