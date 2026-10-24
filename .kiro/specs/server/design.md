# Design: Server (`/server`)

## Overview

A single **FastAPI (Python 3.12)** service is the whole backend. It:

- serves the built frontend (`/frontend/dist`) at `/` with SPA fallback,
- exposes the API under `/api/*`,
- holds the **Anthropic API key** server-side and calls Anthropic **only** from the `extract`
  and `letter` handlers,
- imports all request/response and domain types from the shared **`/contracts`** module, which
  are **Pydantic v2 models** FastAPI uses directly for validation (no duplication, no second
  model set),
- enforces CORS, low-burst rate limiting, error-only/no-body logging, and the `product.md`
  banned-words guardrail.

Frontend and API are served from the **same origin**, so there is one public URL and CORS is a
non-issue in the default deployment. The service deploys to **Render** as a single Docker web
service. This directly replaces the AWS CDK design in `.kiro/specs/infra` (now superseded).

---

## Architecture

```
                     ┌───────────────────────────────────────────────┐
  Browser  ──HTTPS──►│  FastAPI app (uvicorn, Python 3.12)            │
                     │                                                │
                     │  GET /            → StaticFiles(frontend/dist) │  (SPA fallback)
                     │  GET /api/health  → health handler             │
                     │  POST /api/extract→ extract handler  ─────────┐│
                     │  POST /api/analyze→ analyze handler           ││
                     │  GET  /api/procedures → procedures handler    ││
                     │  GET  /api/compare → compare handler          ││
                     │  POST /api/letter → letter handler   ─────────┤│
                     │                                               ││
                     │  middleware: CORS, rate-limit, error logging  ││
                     └───────────────────────────────────────────────┘│
                                                                       │ (key held here)
                                                             ┌─────────▼─────────┐
                                                             │  Anthropic API    │
                                                             │  (extract, letter)│
                                                             └───────────────────┘
```

### Project layout
```
/server
  ├─ app/
  │   ├─ main.py              # FastAPI app factory, mounts static + /api router, middleware
  │   ├─ config.py            # env-driven settings (pydantic BaseSettings)
  │   ├─ deps.py              # shared dependencies (rate limiter, anthropic client provider)
  │   ├─ logging_setup.py     # error-only logger; metadata-only access log formatter
  │   ├─ guardrails.py        # banned-words enforcement (reads product.md list)
  │   ├─ anthropic_client.py  # thin wrapper; only imported by extract/letter
  │   └─ routers/
  │       ├─ health.py        # GET /api/health          (no key)
  │       ├─ extract.py       # POST /api/extract        (Anthropic)
  │       ├─ analyze.py       # POST /api/analyze         (no key)
  │       ├─ procedures.py    # GET  /api/procedures      (no key)
  │       ├─ compare.py       # GET  /api/compare         (no key)
  │       └─ letter.py        # POST /api/letter          (Anthropic)
  ├─ tests/                   # pytest; TC-1..TC-7
  ├─ scripts/
  │   ├─ run.ps1 / run.sh     # local dev (uvicorn --reload)
  │   └─ deploy.ps1 / deploy.sh
  ├─ pyproject.toml           # deps: fastapi, uvicorn[standard], pydantic>=2, anthropic, slowapi
  ├─ Dockerfile               # python:3.12-slim; serves static + API (used by Render)
  ├─ render.yaml              # Render blueprint (service def + env var names)
  ├─ .env.example
  └─ README.md

/contracts/contracts.py       # single source of truth (imported, not duplicated)
/frontend/dist                # built static site served at /
```

### Importing the shared contracts
The server imports domain + request/response types from `/contracts`:
```py
from contracts import (
    ExtractRequest, ExtractResponse, AnalyzeRequest, AnalyzeResponse,
    ProceduresRequest, ProceduresResponse, CompareRequest, CompareResponse,
    LetterRequest, LetterResponse, LineItem, AnalysisResult, Flag, ApiError,
)
```
`/contracts` is placed on the path (installed as an editable local package or added to
`PYTHONPATH`). The contract types are **Pydantic v2 models**, so FastAPI uses them directly for
request/response validation (see "Validation" below). **No endpoint redefines a contract type.**

---

## Components and Interfaces

### 1. App factory (`main.py`)
- Builds the FastAPI app, includes the `/api` router, mounts `StaticFiles` at `/` for
  `frontend/dist` with `html=True` for SPA fallback.
- Registers middleware in order: CORS → rate limiter → error-logging.
- A catch-all for non-`/api` GETs returns `index.html`; `/api/*` 404s stay JSON 404s.

### 2. Config (`config.py`, pydantic `BaseSettings`)
```py
ANTHROPIC_API_KEY: SecretStr       # required; fail fast if missing
EXTRACT_MODEL_ID: str              # required for /api/extract
LETTER_MODEL_ID: str               # required for /api/letter
ALLOWED_ORIGINS: list[str] = []    # empty => same-origin only
RATE_LIMIT_PER_MIN: int = 30       # modest steady rate
RATE_LIMIT_BURST: int = 5          # low burst
MODEL_RATE_LIMIT_PER_MIN: int = 10 # stricter for extract/letter
```
`SecretStr` keeps the key from being accidentally printed/serialized. Startup validates
`ANTHROPIC_API_KEY` presence and fails fast (Req 2.3).

### 3. Anthropic client (`anthropic_client.py`)
- Thin wrapper over the official `anthropic` SDK, constructed with the key from config.
- **Only `extract.py` and `letter.py` import this module.** The other routers never do, which
  structurally enforces the least-privilege split (Req 2.4). A test asserts this (TC-3).

### 4. Routers (one per endpoint)
| Method | Path            | Handler       | Uses key | Notes |
|--------|-----------------|---------------|----------|-------|
| GET    | /api/health     | health        | no       | `{"status":"ok"}` 200 |
| POST   | /api/extract    | extract       | **yes**  | text → `ExtractResponse`; guardrail on labels |
| POST   | /api/analyze    | analyze       | no       | deterministic logic over line items |
| GET    | /api/procedures | procedures    | no       | lookup over reference data |
| GET    | /api/compare    | compare       | no       | charge vs reference; computes ratio + flags |
| POST   | /api/letter     | letter        | **yes**  | drafts `LetterDraft`; guardrail on body/subject |

### 5. Validation
The `/contracts` Python types are **Pydantic v2 models** (`pydantic>=2`), so FastAPI uses them
**directly** as request/response models — there is **no** second, server-side set of models and
nothing to keep in sync beyond the contracts themselves. This is the settled approach (the
earlier "derive vs reuse" decision is closed now that contracts are pydantic).

- Endpoints are typed straight off the imported contracts, e.g.
  ```py
  from contracts import ExtractRequest, ExtractResponse

  @router.post("/extract", response_model=ExtractResponse)
  async def extract(req: ExtractRequest) -> ExtractResponse: ...
  ```
- The contract base model sets `extra="forbid"`, so unexpected fields are rejected, and field
  constraints (e.g. `confidence` in `[0, 1]`, non-negative `units`/`line_index`) are enforced at
  the boundary automatically.
- Invalid payloads → FastAPI raises `RequestValidationError` (422); a handler normalizes it to
  the shared `ApiError` shape so clients see a consistent error contract.

### 6. CORS (`Req 5`)
- Default deployment is same-origin → CORS middleware added but with an empty/narrow allow
  list; no cross-origin traffic occurs.
- For split dev (frontend on another port), `ALLOWED_ORIGINS` lists the exact origin(s); never
  `*`. `CORSMiddleware(allow_origins=settings.ALLOWED_ORIGINS, allow_credentials=False, ...)`.

### 7. Rate limiting (`Req 6`)
- App-level limiter (e.g. `slowapi`, or a small in-process token-bucket dependency). Low burst
  (`RATE_LIMIT_BURST=5`) + modest steady rate. `extract`/`letter` get the stricter
  `MODEL_RATE_LIMIT_PER_MIN`.
- Over-limit → 429 with `ApiError`. Keyed by client IP (hackathon-appropriate; documented).

### 8. Logging (`Req 7` — privacy)
- `logging_setup.py` configures the root logger at **ERROR**. No handler logs the event body
  or the response. A helper `log_error(route, status, request_id, message)` accepts only
  non-body metadata.
- Uvicorn access logging either disabled or replaced with a metadata-only formatter (method,
  route, status, latency, request id) — **no bodies**.
- The Anthropic wrapper never logs prompt/response text. `SecretStr` prevents key leakage.

### 9. Guardrails (`guardrails.py`, `Req 8`)
- Loads the banned-words list (kept in sync with `product.md`; stored as a constant/JSON the
  module reads so the list lives in one place).
- `scrub(text) -> (clean_text, had_violation)` matches case-insensitively with common variants
  (plurals/tenses) and substitutes the neutral alternative.
- `extract` applies it to generated `plain_language_label`s; `letter` applies it to the draft
  `subject` and `body`. If violations remain after substitution, the handler may re-prompt once
  with a system instruction to avoid those terms, then scrub again.

---

## Error Handling
- All handled errors return the shared `ApiError` shape (`{"error": "...", "code"?: "..."}`),
  never request/response bodies or PII.
- Missing model env var → 5xx `ApiError` for that endpoint only (service stays up, Req 4.4).
- Missing `ANTHROPIC_API_KEY` at startup → fail fast (Req 2.3).
- Rate limit → 429 `ApiError`. Validation → 422/400 `ApiError`.
- A global exception handler logs error-only metadata and returns a generic `ApiError` (no
  stack/body leakage to the client).

---

## Testing Strategy (pytest + httpx against the app)

### TC-1 Health check
- **Precondition:** app running (stub or full).
- **Action:** `GET /api/health`.
- **Expected:** 200, body `{"status":"ok"}`, no sensitive data.

### TC-2 Contract conformance
- **Action:** Call each endpoint with a valid payload built from the `/contracts` types; assert
  the response validates against the corresponding contract response type.
- **Expected:** Every endpoint's response matches its contract shape; a payload that violates
  the contract is rejected with 422/400 `ApiError`.

### TC-3 Key never leaks / least-privilege split
- **Action (static):** assert only `extract.py` and `letter.py` import `anthropic_client`;
  assert no response model or returned payload can contain the key; grep the built frontend for
  the key value.
- **Action (runtime):** inspect all endpoint responses for the key string.
- **Expected:** key absent from every response and from the frontend bundle; the four non-model
  handlers do not import the Anthropic client.

### TC-4 CORS
- **Action:** With `ALLOWED_ORIGINS` set to one origin, send a preflight from that origin and
  from a disallowed one.
- **Expected:** allowed origin gets matching ACAO; disallowed origin does not; `*` is never
  returned.

### TC-5 Rate limiting
- **Action:** Fire a burst above `RATE_LIMIT_BURST` at `GET /api/procedures` and above
  `MODEL_RATE_LIMIT_PER_MIN` at `POST /api/extract`.
- **Expected:** excess requests get 429 `ApiError`; the service stays healthy.

### TC-6 No-body logging
- **Action:** Send `POST /api/extract` with a unique marker string in the body; capture logs.
- **Expected:** marker string absent from logs; only error-level metadata present; key absent.

### TC-7 Banned-words enforcement
- **Action:** Drive `letter`/`extract` so the model would produce a banned term (mock the
  Anthropic call to return banned text); call the endpoint.
- **Expected:** the returned text contains no banned term (substituted/regenerated); the
  guardrail reports the mitigation.

---

## Deploy & Teardown

### Local run (`scripts/run.*`)
```
uvicorn app.main:app --reload --port 8000
```
Reads `.env` (copy from `.env.example`, fill `ANTHROPIC_API_KEY`, model IDs). Locally the port
is 8000; in production the app binds `$PORT` (Render injects it).

### Deploy — Render (chosen host)
The service deploys to **Render** as a single web service (one container serving static + API,
one public HTTPS `*.onrender.com` URL). Two ways to wire it, both using the same `Dockerfile`:

- **Blueprint (preferred, reproducible):** commit a `render.yaml` describing one `web` service
  with `env: docker`, and the env vars (`ANTHROPIC_API_KEY`, `EXTRACT_MODEL_ID`,
  `LETTER_MODEL_ID`, `ALLOWED_ORIGINS`). On Render, "New → Blueprint" points at the repo and
  provisions the service. Secrets are set in the dashboard (marked `sync: false` in the
  blueprint so the key is never committed).
- **Dashboard:** "New → Web Service" → connect the repo → Render detects the `Dockerfile` →
  set the env vars → deploy.

Start command (baked into the Dockerfile / Render start):
`uvicorn app.main:app --host 0.0.0.0 --port $PORT` — Render injects `$PORT`, so the app must read
it from the environment rather than hard-coding 8000.

Render specifics to account for:
- **HTTPS + URL** are provided automatically (`https://<service>.onrender.com`).
- **Free tier cold starts:** a free web service spins down after inactivity and takes ~30–60s to
  wake on the next request. Hit the URL once to warm it before a demo, or use a paid instance to
  avoid spin-down. `GET /api/health` is a convenient warm-up/health endpoint (Render can also use
  it as the service health check path).
- **Same-origin:** since static + API are one service, `ALLOWED_ORIGINS` can stay empty in the
  default deployment.

`scripts/deploy.*` documents the blueprint flow and, optionally, triggers a deploy via a Render
**Deploy Hook** URL (a repo push to the connected branch also auto-deploys).

### One-line teardown
Delete the Render service (removes the deployment and its URL). Easiest is the dashboard
(**Service → Settings → Delete**). For a scripted one-liner, call the Render API with a token:
```
curl -X DELETE https://api.render.com/v1/services/<service-id> -H "Authorization: Bearer $RENDER_API_KEY"
```
The README records the exact service id / one-liner once the service exists. (Because everything
is one Render service with no external datastore, deleting it leaves nothing orphaned.)

### Stub-first (`Req 9`)
Ship `main.py` with the static mount + `GET /api/health` and a placeholder `frontend/dist/
index.html` first; deploy to get the public URL, then fill in the routers.

---

## Notes / Settled decisions
- **Host: Render** (single Docker web service, blueprint via `render.yaml`). The Dockerfile keeps
  it portable if the team ever switches, but Render is the target. Mind the free-tier cold start.
- **Validation: the `/contracts` Pydantic v2 models are used directly by FastAPI.** No second set
  of server-side models; `/contracts` remains the single source of truth. (Decision closed.)
- **Reference data** for `procedures`/`compare` (Medicare reference, MA price ranges) is assumed
  to come from `/data/processed`; its schema/source is out of scope here and owned by the data
  task. This spec only consumes it.
