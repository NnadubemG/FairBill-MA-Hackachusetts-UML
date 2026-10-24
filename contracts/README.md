# `/contracts` — Shared domain contracts (single source of truth)

These type definitions are the **single source of truth** for the domain. The
**frontend** and the **server** both import from here. Do **not** duplicate or
redefine these shapes anywhere else.

- **TypeScript:** `index.ts` — imported by the frontend and any TS server code.
  ```ts
  import type { LineItem, AnalyzeRequest } from '@hackachusetts/contracts';
  ```
- **Python:** `contracts.py` (re-exported via `__init__.py`) — **Pydantic v2**
  models, imported by the Python backend and used directly by FastAPI for
  request/response validation. Requires `pydantic>=2`.
  ```py
  from contracts import LineItem, AnalyzeRequest
  ```
  Because these are Pydantic models, there is **no** second set of request/
  response models in the server — FastAPI validates against these directly.

## Keep both sides in sync

`index.ts` and `contracts.py` describe the **same** shapes in two languages.
Any change to one **must** be mirrored in the other. Conventions:

- **Money** is whole US **cents** (`number` / `int`), never floats of dollars.
- **`null` / `None`** means *unknown / not available*, distinct from `0`.
- **Confidence** is a float in `[0, 1]` (enforced at runtime on the Python side).
- The Python models use `extra="forbid"`, so unexpected fields are rejected.
  Keep the TS interfaces matched to the same field set.

## What's defined here

Core domain: `LineItem`, `AnalysisResult`, `Flag` (+ `FlagBasis`),
`PriceRange`, `ProcedureInfo`, and the letter types (`LetterType`,
`LetterRecipient`, `LetterDraft`).

Endpoint request/response pairs:

| Endpoint          | Request            | Response            |
|-------------------|--------------------|---------------------|
| POST /api/extract | `ExtractRequest`   | `ExtractResponse`   |
| POST /api/analyze | `AnalyzeRequest`   | `AnalyzeResponse`   |
| GET  /api/procedures | `ProceduresRequest` | `ProceduresResponse` |
| GET  /api/compare | `CompareRequest`   | `CompareResponse`   |
| POST /api/letter  | `LetterRequest`    | `LetterResponse`    |

Plus the shared `ApiError` shape. Error payloads never contain request/response
bodies or PII (see `.kiro/steering/product.md`).
