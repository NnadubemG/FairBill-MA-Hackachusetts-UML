# Requirements: Server (`/server`)

## Introduction

This spec defines a **single FastAPI service (Python 3.12)** that serves the Massachusetts
Medical-Bill Helper end to end. It **holds the Anthropic API key server-side**, serves the
static frontend, and exposes the `/api/*` endpoints. **No AWS** — this spec supersedes
`.kiro/specs/infra` (AWS CDK), which is kept only as historical reference.

The service is one deployable unit producing one public URL: it serves the built frontend
(`/frontend/dist`) and the API from the same origin, which also makes CORS trivial.

All request/response and domain types come from the shared **`/contracts`** module
(`contracts/contracts.py` / `contracts/index.ts`) — the single source of truth. The server
**imports** these; it must not redefine them.

### Glossary
- **Stub**: Minimal deployable slice — a placeholder frontend page + `GET /api/health` — used
  to get a public URL running before the real handlers exist.
- **Bedrock-equivalent split**: Only the `extract` and `letter` handlers call Anthropic;
  `analyze`, `procedures`, `compare`, `health` never touch the model or the key.
- **Banned words**: The list in `.kiro/steering/product.md` that generated/returned text must
  never contain.

---

## Requirements

### Requirement 1: Single FastAPI service, no AWS
**User Story:** As the team, I want one Python service that serves everything, so that there is
one thing to run, one public URL, and no cloud-provider lock-in.

#### Acceptance Criteria
1. THE service SHALL be a single **FastAPI** app running on **Python 3.12**.
2. THE service SHALL serve the static frontend from `/frontend/dist` at the site root (`/`).
3. THE service SHALL expose the API under the `/api` path prefix.
4. THE service SHALL NOT depend on any AWS service or SDK.
5. WHERE a static asset path does not match a built file THEN the service SHALL return
   `index.html` (SPA fallback) for navigational routes, while `/api/*` paths SHALL never fall
   back to the SPA.
6. THE service SHALL bind the host `0.0.0.0` and the port from the `PORT` environment variable
   when set (defaulting to 8000 locally), so it runs correctly on **Render**.

### Requirement 2: Anthropic API key is held server-side only
**User Story:** As a security-conscious operator, I want the Anthropic key to live only on the
server, so that it is never exposed to the browser.

#### Acceptance Criteria
1. THE service SHALL read `ANTHROPIC_API_KEY` from the environment (supporting a local `.env`).
2. THE key SHALL NEVER be sent to the client, embedded in the frontend bundle, or returned in
   any API response.
3. IF `ANTHROPIC_API_KEY` is missing at startup THEN the service SHALL fail fast with a clear
   error (handlers that need it SHALL NOT start serving).
4. ONLY the `extract` and `letter` handlers SHALL use the key / call Anthropic. `analyze`,
   `procedures`, `compare`, and `health` SHALL NOT access the key or the Anthropic client.

### Requirement 3: Endpoints match the shared contracts
**User Story:** As a frontend developer, I want the API to match `/contracts` exactly, so that
the client and server never drift.

#### Acceptance Criteria
1. THE service SHALL expose: `POST /api/extract`, `POST /api/analyze`, `GET /api/procedures`,
   `GET /api/compare`, `POST /api/letter`, and `GET /api/health`.
2. EACH endpoint's request and response SHALL use the types defined in `contracts/contracts.py`
   (`ExtractRequest`/`ExtractResponse`, `AnalyzeRequest`/`AnalyzeResponse`,
   `ProceduresRequest`/`ProceduresResponse`, `CompareRequest`/`CompareResponse`,
   `LetterRequest`/`LetterResponse`).
3. THE server SHALL NOT redefine any domain type already defined in `/contracts`.
4. WHERE runtime validation is needed THEN the server SHALL validate requests against the
   contract shapes and reject invalid payloads with a 422/400 and the shared `ApiError` shape.

### Requirement 4: Model configuration via environment
**User Story:** As an operator, I want to set models without code changes, so that I can swap
models per environment.

#### Acceptance Criteria
1. THE `extract` handler SHALL read its model ID from `EXTRACT_MODEL_ID`.
2. THE `letter` handler SHALL read its model ID from `LETTER_MODEL_ID`.
3. Model IDs SHALL be Anthropic **direct-API** model names (not Bedrock IDs).
4. WHERE a required model env var is missing THEN the affected endpoint SHALL return a clear
   5xx error (using `ApiError`) rather than crashing the whole service.

### Requirement 5: CORS
**User Story:** As a developer, I want correct CORS, so that the browser can call the API.

#### Acceptance Criteria
1. WHEN frontend and API share the same origin (default deployment) THEN no cross-origin
   requests occur and CORS is a non-issue.
2. WHERE a separate frontend origin is configured (e.g. local dev on a different port) THEN the
   service SHALL allow exactly that configured origin, not `*`.
3. THE allowed origin(s) SHALL be configurable via environment (e.g. `ALLOWED_ORIGINS`).

### Requirement 6: Abuse protection (rate limiting)
**User Story:** As an operator, I want request throttling, so that the API and the Anthropic
spend are protected from abuse.

#### Acceptance Criteria
1. THE service SHALL enforce **application-level rate limiting** with a **low burst limit** and
   a modest steady rate.
2. WHEN a client exceeds the limit THEN the service SHALL return HTTP **429** with `ApiError`.
3. THE model-calling endpoints (`extract`, `letter`) SHALL be rate-limited at least as strictly
   as the others.
4. THE limits SHALL be configurable constants.

### Requirement 7: Privacy-preserving logging
**User Story:** As a privacy-conscious operator, I want only errors logged and never bill
content, so that sensitive medical/financial data is never persisted.

#### Acceptance Criteria
1. THE service SHALL log **errors only** (no info/debug logging of payloads).
2. THE service SHALL NEVER log request bodies or response bodies, nor the text sent to or
   returned from Anthropic.
3. WHERE access logging exists THEN it SHALL record only non-body metadata (method, route,
   status, latency, request id).
4. THE Anthropic API key SHALL never appear in any log line.

### Requirement 8: Content guardrails (banned words)
**User Story:** As the product owner, I want generated text to respect the product guardrails,
so that the app never gives advice it must not give.

#### Acceptance Criteria
1. THE `extract` and `letter` handlers SHALL enforce the **banned-words list** from
   `.kiro/steering/product.md` on model-generated text before returning it.
2. WHEN generated text contains a banned term THEN the service SHALL mitigate it (regenerate,
   soften, or substitute the neutral alternative) so the response is clean.
3. THE guardrail SHALL apply to drafted letters and any model-authored labels/explanations.

### Requirement 9: Stub-first delivery
**User Story:** As the team, I want a public URL early, so that we can integrate and demo
before the real handlers are done.

#### Acceptance Criteria
1. THE first runnable increment SHALL be a **stub**: a placeholder frontend page served at `/`
   plus a working `GET /api/health` returning 200 and minimal JSON.
2. THE stub SHALL run with the same start/deploy script as the full service.

### Requirement 10: Operational tooling (Render)
**User Story:** As a developer, I want simple run, deploy, and teardown on **Render**, so that I
can iterate fast during the hackathon.

#### Acceptance Criteria
1. THE spec SHALL provide a **run script** for local dev (reload) and deploy to **Render** via a
   `Dockerfile` + `render.yaml` blueprint (single web service serving static + API).
2. THE spec SHALL provide a **one-line teardown** that deletes the Render service (e.g. the
   Render API `DELETE /v1/services/<id>`), leaving no orphaned resources.
3. THE service SHALL document all required environment variables in a `.env.example`
   (`ANTHROPIC_API_KEY`, `EXTRACT_MODEL_ID`, `LETTER_MODEL_ID`, `ALLOWED_ORIGINS`), with no
   real secrets committed; secrets SHALL be set in the Render dashboard (`sync: false` in the
   blueprint), never committed.
4. WHERE deployed on Render's free tier THEN the team SHALL account for cold-start spin-up
   (~30–60s) by warming `GET /api/health` before a demo.

### Requirement 11: Verifiable test cases
**User Story:** As a reviewer, I want documented test cases, so that I can confirm the service
behaves correctly and safely.

#### Acceptance Criteria
1. THE design SHALL list concrete test cases covering at minimum: **health check**, **contract
   conformance**, **key-never-leaks**, **CORS**, **rate limiting**, **no-body logging**, and
   **banned-words enforcement**.
2. EACH test case SHALL state its precondition, action, and expected result.
