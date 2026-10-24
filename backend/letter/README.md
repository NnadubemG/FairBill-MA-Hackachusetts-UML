# `/backend/letter` — Letter drafts

Builds an editable letter the patient can review and send. The result is a `LetterDraft`
from `/contracts`: `subject`, `body`, `referenced_line_item_ids`.

The letter is a **fixed template**. The patient's own fields go in by the template. The
model may write **one thing only**: the short "reason" paragraph, and only for a coding
review. Code checks that paragraph. If it fails any check, or the model call fails, a fixed
fallback paragraph is used, so the app always returns a complete letter.

## Letter types
| `letter_type` | What it asks for | Model used? |
| --- | --- | --- |
| `itemized_bill` | An itemized bill with billing codes | No (fixed text) |
| `coding_review` | A coding and billing review of the selected lines | Yes, if at least one usable flag |
| `financial_assistance` | A financial assistance review | No (fixed text) |

An unknown type raises `InvalidLetterType` (a `ValueError`). The API layer should return a
400 for it. This is the only case that does not fall back.

## Use
```python
from backend.letter.client import make_letter_client
from backend.letter.handler import generate_letter
from backend.letter.request import parse_request

request = parse_request(payload)          # payload = the JSON from the frontend
result = generate_letter(request, client=make_letter_client())
result.draft          # LetterDraft: subject, body, referenced_line_item_ids
result.used_fallback  # True if the reason paragraph is the fixed fallback
result.warnings       # generic text only
```

Example payload:
```json
{
  "letter_type": "coding_review",
  "patient": {"name": "...", "account_number": "...", "hospital": "...", "date": "...", "notes": ""},
  "flags": [{"line_item_id": "1", "flag_type": "...", "reason": "...", "basis": "...",
             "severity": "info", "data_source": null, "data_year": null}],
  "line_items": [{"id": "1", "description": "...", "billed_amount": 100.0,
                  "code": "99213", "date_of_service": "2026-03-04"}]
}
```
`parse_request` raises a `ValueError` that names the bad field (never its value). Unknown
extra keys are ignored. Empty patient fields become placeholders such as `[Your name]`.

## What the letter may contain
- A fixed top line: "Draft for you to review and edit before sending."
- The patient's fields, cleaned (control and invisible characters removed, one line each,
  length limits) and inserted as typed. The model never sees them.
- For a coding review, one entry per used flag: the line's **code, amount and date**, and the
  flag's `basis`. Line descriptions from the bill are never used.
- Fixed requests that ask for documents and explanations.
- The reason paragraph: model text that passed every check, or the fixed fallback.

## The checks on the model paragraph
It is used only if it has:
- no banned word;
- no accusation, legal, money-demand or deadline wording (lists are in `config.py`);
- no number that is not in the facts given to the model (a date counts only as a whole);
- no word that implies a new number ("twice", "half", "percent"...);
- one paragraph of 2 to 4 short sentences, in the first person;
- no greeting, sign-off, list, markdown, link, email, placeholder or line break inside.

At most 10 flags are used in one letter. A flag whose line is not in the request is skipped.

## Environment variables
| Variable | Required | Purpose |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | Yes (real client only) | Anthropic API key. Secret: never hardcode, commit, or log it. |
| `LETTER_MODEL_ID` | Yes (real client only) | Anthropic model name for letters. Use the smallest model that passes the evals. |

The fake client (`FakeLLMClient` from `/backend/extract`) needs neither.

## Privacy
Patient fields, flag text, line data, prompts and model output are never logged and never
written to disk. Warnings are fixed, generic text. An error from the model call carries only
the exception type.

## Running tests
Fully offline: no network, no API key, no `anthropic` install needed (the real client is
tested with a stand-in module).

```bash
# from the repo root
python3 -m pytest backend/letter -q
```

Property-based tests use Hypothesis. See `.kiro/specs/backend-letter/design.md` for the full
test-case list. The root `pytest.ini` lists only some test folders, so run
`python3 -m pytest backend -q` to include extract, explain and letter.
