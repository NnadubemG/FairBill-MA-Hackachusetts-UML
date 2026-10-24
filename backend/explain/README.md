# `/backend/explain` — Plain-language explanations

Takes the `Flag` objects from `/core` and fills `Flag.explanation` with a short rewrite
for the patient: 2 to 3 short sentences, about an 8th-grade reading level, ending with
one question the patient could ask the billing office.

Only `explanation` changes. `reason`, `basis`, `data_source`, `data_year`, `severity`,
`flag_type` and `line_item_id` stay exactly as `/core` made them.

## How it works
1. **One batched model call** covers all flags (up to 30; extra flags use the fallback).
   No retry.
2. The model sees only `flag_type`, `reason` and `basis` per flag, plus a key. It never
   sees line item descriptions or other bill text.
3. **Code checks every explanation** (`checks.py`). The model text is used for a flag
   only if it has:
   - no banned word,
   - no number that is not already in that flag's `reason`/`basis` (or its year),
   - no word that implies a new number ("twice", "half", "percent"...),
   - 2 to 3 sentences, with exactly one question, last.
4. A flag that fails a check (or has no model text) gets its **fallback**
   (`templates.py`): its own `reason` plus one fixed question for its flag type.
5. If the call fails or the reply is unusable, every flag uses the fallback. The handler
   does not raise.

```python
from backend.explain.handler import explain
from backend.explain.client import make_explain_client

result = explain(flags, client=make_explain_client())
result.flags            # same flags, with explanation set
result.fallback_count   # how many used the fallback
result.warnings         # generic text only
```

## Environment variables
| Variable | Required | Purpose |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | Yes (real client only) | Anthropic API key. Secret: never hardcode, commit, or log it. |
| `EXPLAIN_MODEL_ID` | Yes (real client only) | Anthropic model name for explain. Use the smallest model that passes the evals. |

The fake client (`FakeLLMClient` from `/backend/extract`) needs neither.

## Privacy
Flag text, prompts and model output are never logged and never written to disk.
Warnings are fixed, generic text. Errors from the model call carry only the exception
type.

## Running tests
Fully offline: no network, no API key, no `anthropic` install needed (the real client is
tested with a stand-in module).

```bash
# from the repo root
python3 -m pytest backend/explain -q
```

Property-based tests use Hypothesis. See `.kiro/specs/backend-explain/design.md` for the
full test-case list.

Note: the root `pytest.ini` lists only some test folders, so run
`python3 -m pytest backend -q` to include these tests.
