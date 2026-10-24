# Implementation Plan: Server (`/server`)

> Supersedes `.kiro/specs/infra` (AWS CDK). Single FastAPI (Python 3.12) service, no AWS.
> Stub-first: tasks 1–4 get a public URL (static page + health check) before real handlers.
> All domain/request/response types are imported from `/contracts` — never redefined.

- [ ] 1. Scaffold the FastAPI project in `/server`
  - Create `pyproject.toml` (fastapi, uvicorn[standard], pydantic>=2, anthropic, rate-limit lib),
    `app/` package, `app/config.py` (pydantic `BaseSettings` with `ANTHROPIC_API_KEY: SecretStr`,
    model IDs, `ALLOWED_ORIGINS`, rate-limit settings, and `PORT` default 8000), and
    `.env.example`.
  - Wire `/contracts` onto the import path (editable local package or PYTHONPATH).
  - _Requirements: 1.1, 1.6, 2.1, 2.3, 4.1, 4.2, 10.3_

- [ ] 2. Wire contract models directly into FastAPI
  - The `/contracts` types are already Pydantic v2 models, so type the endpoints straight off
    them (`response_model=`/typed request params) with no second server-side model set. Add an
    exception handler that normalizes `RequestValidationError` (422) to the shared `ApiError`.
  - _Requirements: 3.2, 3.3, 3.4_

- [ ] 3. Implement the stub: static mount + `GET /api/health`
  - `app/main.py`: app factory, mount `StaticFiles('frontend/dist', html=True)` at `/` with SPA
    fallback (but `/api/*` never falls back), include `/api` router. Bind `0.0.0.0:$PORT`.
  - `app/routers/health.py`: `{"status":"ok"}` 200 (also serves as Render's health check path).
  - Placeholder `frontend/dist/index.html`.
  - _Requirements: 1.2, 1.3, 1.5, 1.6, 3.1, 9.1_

- [ ] 4. Render deploy wiring + teardown and the first stub deploy
  - Add a `Dockerfile` (python:3.12-slim, install deps, copy `frontend/dist`, run
    `uvicorn app.main:app --host 0.0.0.0 --port $PORT`) and a `render.yaml` blueprint (one `web`
    service, `env: docker`, env vars with secrets `sync: false`). `scripts/run.*` for local dev.
  - Document the one-line teardown (Render API `DELETE /v1/services/<id>`) in `server/README.md`.
  - Deploy the stub to Render; confirm the `*.onrender.com` URL serves the page and
    `/api/health` (warm it once for cold start). **(Public URL milestone.)**
  - _Requirements: 9.2, 10.1, 10.2, 10.4_

- [ ] 5. Error-only, no-body logging
  - `app/logging_setup.py`: root logger at ERROR; `log_error(route,status,request_id,msg)`
    (metadata only). Replace/disable uvicorn access log with a metadata-only formatter. Ensure
    the key (SecretStr) can never be logged.
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [ ] 6. Rate limiting middleware
  - Low burst + modest steady rate; stricter limit for `extract`/`letter`; 429 → `ApiError`.
    Limits come from config.
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [ ] 7. CORS
  - Add CORS middleware driven by `ALLOWED_ORIGINS` (exact origins, never `*`); same-origin
    default needs none.
  - _Requirements: 5.1, 5.2, 5.3_

- [ ] 8. Anthropic client wrapper (key isolation)
  - `app/anthropic_client.py` built from the config key; imported **only** by `extract.py` and
    `letter.py`. Never logs prompt/response text.
  - _Requirements: 2.2, 2.4, 7.2, 7.4_

- [ ] 9. Banned-words guardrail
  - `app/guardrails.py`: load the `product.md` list (single stored copy), `scrub(text)` with
    case-insensitive + variant matching and neutral substitution; optional one re-prompt.
  - _Requirements: 8.1, 8.2, 8.3_

- [ ] 10. Implement `POST /api/extract` (Anthropic)
  - Validate `ExtractRequest`; call Anthropic with `EXTRACT_MODEL_ID`; map to `ExtractResponse`
    (`line_items`, `overall_confidence`); apply guardrail to labels; missing model var → 5xx
    `ApiError`.
  - _Requirements: 3.1, 3.2, 4.1, 4.4, 8.1_

- [ ] 11. Implement `POST /api/letter` (Anthropic)
  - Validate `LetterRequest`; call Anthropic with `LETTER_MODEL_ID`; return `LetterResponse`
    (`LetterDraft`); apply guardrail to subject/body; always a draft, never sent.
  - _Requirements: 3.1, 3.2, 4.2, 4.4, 8.1, 8.3_

- [ ] 12. Implement the non-model endpoints
  - `POST /api/analyze` (`AnalyzeRequest`→`AnalyzeResponse`), `GET /api/procedures`
    (`ProceduresResponse`), `GET /api/compare` (`CompareResponse` with `ratio_to_medicare` +
    flags). Deterministic logic over `/data/processed`; **no Anthropic client import.**
  - _Requirements: 2.4, 3.1, 3.2_

- [ ] 13. Tests TC-1 … TC-7
  - pytest + httpx: health, contract conformance, key-never-leaks + least-privilege import
    check, CORS allow/deny, rate limiting, no-body logging, banned-words enforcement (mock
    Anthropic).
  - _Requirements: 11.1, 11.2, and verification of 1–8_

- [ ] 14. Full deploy to Render and verification
  - Build the real frontend into `frontend/dist`, set the env vars in the Render dashboard
    (`ANTHROPIC_API_KEY`, `EXTRACT_MODEL_ID`, `LETTER_MODEL_ID`, `ALLOWED_ORIGINS`), deploy via
    the blueprint, run TC-1…TC-7 against the `*.onrender.com` URL, and record it.
  - _Requirements: all_
