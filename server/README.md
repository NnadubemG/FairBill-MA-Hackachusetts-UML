# Server — Massachusetts Medical-Bill Helper

A single **FastAPI (Python 3.12)** service that is the whole backend. It:

- serves the built frontend (`/frontend/dist`) at `/` with SPA fallback,
- exposes the API under `/api/*`,
- holds the **Anthropic API key** server-side and calls Anthropic **only** from the
  `extract` and `letter` handlers,
- imports all request/response + domain types from the shared **`/contracts`**
  package (the single source of truth — never redefined here).

Frontend and API share one origin, so there is one public URL and CORS is a
non-issue in the default deployment. Deploys to **Render** as one Docker web
service. (This replaces the old AWS design in `.kiro/specs/infra`, now superseded.)

---

## Layout

```
server/
  app/
    main.py              # app factory: static mount + /api router + middleware
    config.py            # env-driven settings (pydantic-settings; SecretStr key)
    logging_setup.py     # error-only logger; no request/response bodies ever
    guardrails.py        # banned-words enforcement (from product.md)
    anthropic_client.py  # thin Anthropic wrapper; imported ONLY by extract/letter
    routers/
      health.py          # GET  /api/health      (no key)
      extract.py         # POST /api/extract     (Anthropic)
      analyze.py         # POST /api/analyze     (no key)
      procedures.py      # GET  /api/procedures  (no key)
      compare.py         # GET  /api/compare     (no key)
      letter.py          # POST /api/letter      (Anthropic)
  tests/                 # pytest (TC-1..TC-7)
  scripts/               # run.* (local dev), deploy.* (Render)
  pyproject.toml
  Dockerfile             # built from the REPO ROOT (see below)
  .env.example
../render.yaml           # Render blueprint (at repo root)
../contracts/            # shared contracts (imported, not vendored)
../frontend/dist/        # built static site served at /
```

---

## Local development

Requires Python 3.12. Install deps and run with reload:

```bash
# from repo root
pip install -e "server[dev]"          # or: pip install <deps from pyproject>
cp server/.env.example server/.env    # then fill in the values
```

Run (the scripts put the repo root on PYTHONPATH so `from contracts import ...`
resolves):

```bash
# macOS/Linux
server/scripts/run.sh
# Windows PowerShell
server/scripts/run.ps1
```

The app serves at <http://localhost:8000> — `/` is the frontend, `/api/health`
is the liveness check.

### Environment variables

Documented in `.env.example`. Summary:

| Var                 | Required                 | Purpose                                   |
|---------------------|--------------------------|-------------------------------------------|
| `ANTHROPIC_API_KEY` | yes (for extract/letter) | Anthropic API key, held server-side only  |
| `EXTRACT_MODEL_ID`  | yes (for extract)        | Anthropic model id for extraction         |
| `LETTER_MODEL_ID`   | yes (for letter)         | Anthropic model id for letter drafting    |
| `ALLOWED_ORIGINS`   | no                       | Comma-separated CORS origins; empty = same-origin |
| `PORT`              | no                       | Bind port; Render injects it (8000 local) |

The key uses `SecretStr` and is never logged, never returned, and never shipped
to the browser.

---

## Docker

The image is built from the **repo root** (not `server/`) so it can copy both
`contracts/` and `server/` without duplicating the shared contracts:

```bash
# from repo root
docker build -f server/Dockerfile -t medbill .
docker run -p 8000:8000 --env-file server/.env medbill
```

---

## Deploy to Render

One Docker web service, provisioned from the committed `render.yaml` blueprint.

1. Commit and push (`contracts/`, `server/`, `frontend/dist/`, `render.yaml`).
2. On Render: **New → Blueprint** → select this repo. Render reads `render.yaml`
   and provisions a Docker web service (build context = repo root,
   health check path `/api/health`).
3. In the service **Environment**, set the secrets (marked `sync: false`, so they
   are never committed): `ANTHROPIC_API_KEY`, `EXTRACT_MODEL_ID`, `LETTER_MODEL_ID`.
4. Deploy. The public URL is `https://<service>.onrender.com`.
5. **Warm it once** before a demo — the free tier spins down after inactivity and
   cold-starts in ~30–60s:
   ```bash
   curl https://<service>.onrender.com/api/health
   ```

`scripts/deploy.*` prints these steps and can trigger a one-off deploy if you set
`RENDER_DEPLOY_HOOK_URL` to a Render Deploy Hook. Pushing to the connected branch
also auto-deploys (`autoDeploy: true`).

---

## One-line teardown

Everything is a single Render service with no external datastore, so deleting the
service leaves nothing orphaned.

- **Dashboard:** Service → Settings → **Delete**.
- **Scripted (one line)** — needs a Render API token and the service id:
  ```bash
  curl -X DELETE https://api.render.com/v1/services/<SERVICE_ID> \
       -H "Authorization: Bearer $RENDER_API_KEY"
  ```
  Record the real `<SERVICE_ID>` here once the service exists:

  > Service id: `____________________`  (fill in after first deploy)

---

## Tests

```bash
# from repo root, with contracts on PYTHONPATH
pip install -e "server[dev]"
cd server && python -m pytest
```

Test cases TC-1…TC-7 cover: health, contract conformance, key-never-leaks +
least-privilege import check, CORS allow/deny, rate limiting, no-body logging,
and banned-words enforcement (Anthropic mocked).
