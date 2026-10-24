# Kiro build log

Notable moments, decisions, and compromises while building the Massachusetts
Medical-Bill Helper server (FastAPI + Anthropic API, deployed on Render).

## Steps 4–10 — continuous build (Anthropic + Render, no AWS)

### Step 4 — Dockerfile, render.yaml, deploy scripts, README

- **Docker build context = repo root, not `/server`.** The shared `/contracts`
  package is the single source of truth and must not be vendored/duplicated into
  `/server`. So the image is built from the repo root and copies both
  `contracts/` and `server/`. `render.yaml` sets `dockerContext: .` and
  `dockerfilePath: ./server/Dockerfile`.
- **`PYTHONPATH=/app`** in the image so `from contracts import ...` and
  `from app... import ...` both resolve (contracts and the server app sit side by
  side under `/app`).
- **Deps installed from `pyproject.toml`.** Added `anthropic` and `slowapi` to the
  runtime deps now that the handlers that need them are being implemented (they
  were commented out in the stub).
- **Start command reads `$PORT`** (Render injects it): the Dockerfile CMD uses a
  shell form so `$PORT` expands, defaulting to 8000 locally.
- **Health check path** for Render is `/api/health`.
- **Secrets never committed:** `render.yaml` marks `ANTHROPIC_API_KEY`,
  `EXTRACT_MODEL_ID`, `LETTER_MODEL_ID` with `sync: false` (set in the dashboard).

#### Compromise — Docker not verifiable locally
- `docker` is not installed on the dev machine, so the image could not be built
  locally to verify. Mitigation: the Dockerfile is kept simple and the same start
  path (`uvicorn app.main:app`) is verified by running the app directly and by the
  pytest suite. The real image build happens on Render at deploy time.
- The **actual Render deploy is a manual step for the account owner** (needs the
  Render account + Anthropic key). Everything needed for it (Dockerfile,
  render.yaml, deploy scripts, README teardown) is committed.

### Steps 5–6 & server tasks 5–13 — server implementation + tests

- **Config: `ALLOWED_ORIGINS` stored as a raw string, parsed via a property.**
  pydantic-settings tries to JSON-decode `List[str]` env vars, which broke on a
  plain comma-separated value. Switched the field to `str` and exposed
  `allowed_origins` as a computed `List[str]` property. (Decision/compromise.)
- **Rate limiting: in-process token bucket keyed by client IP** (honors
  X-Forwarded-For first hop for Render's proxy). Fine for the single-instance
  hackathon deploy; a multi-instance deploy would need a shared store. Documented.
- **Reference data: graceful fallback.** `/data/processed` doesn't exist yet
  (owned by a separate data task). `reference_data.py` loads
  `data/processed/procedures.json` if present, else serves a small built-in
  sample so `procedures`/`compare`/`analyze` work now. Clearly marked as sample.
- **Model handlers return endpoint-specific 5xx** (503 when the model id is
  missing, 502 on bad model output) so one misconfigured endpoint never takes the
  whole service down (Req 4.4).
- **Terminal quirk:** this machine's shell echoes/garbles multi-part commands and
  `execute_pwsh` returned exit -1 with no stdout; switched to the background
  process tool to capture test output reliably. `python` is not on PATH — used the
  explicit interpreter at
  `C:\Users\dontm\AppData\Local\Programs\Python\Python312\python.exe`.
- **Tests:** 26 passing — TC-1 health, TC-2 contract conformance (+ extra=forbid),
  TC-3 key-never-leaks + least-privilege import check, TC-4 CORS allow/deny,
  TC-5 rate limiting, TC-6 no-body logging, TC-7 banned-words (Anthropic mocked),
  plus extract parse/err paths.
- Server spec tasks 1–13 marked complete. Task 14 (live Render deploy) stays open:
  it needs the Render account + Anthropic key (owner's manual step).

### Step 7 frontend handoff
- The local shell could not complete `npm install`: Node was installed outside PATH, PowerShell blocked `npm.ps1`, and corrected attempts stalled before creating `node_modules`.
- Mitigation: changed `server/Dockerfile` to a multi-stage build. Render uses `node:22-slim` to install pinned packages and run `npm run build`, then copies `frontend/dist` into the Python image.
- A teammate can independently verify with `cd frontend`, `npm install`, and `npm run build` on a Node-compatible machine.

### Frontend build issue resolved
- Found the compatible invocation: run `cmd.exe` with `C:\Program Files\nodejs` prepended to PATH so esbuild's child process can resolve `node`.
- `npm install` completed and created `package-lock.json`; TypeScript and Vite then built the real `frontend/dist` bundle successfully.
- Docker now copies the lockfile and uses reproducible `npm ci` in its Node build stage.
