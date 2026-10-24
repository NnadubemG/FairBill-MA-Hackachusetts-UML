# app_server — runnable HTTP server

A dependency-free (stdlib `http.server`) server that wires the team's real backend
handlers behind the app's routes, so the whole system runs end to end. It does **not**
reimplement any logic — it imports and calls the existing handlers.

| Route | Method | Backend | Notes |
| --- | --- | --- | --- |
| `/health` | GET | — | liveness + whether the model is live or offline-fallback |
| `/procedures` | GET | `backend.compare` | curated procedure list |
| `/compare?code=XXXXX` | GET | `backend.compare` | one code across hospitals |
| `/analyze` | POST | `backend.analyze` | `{line_items:[...]}` → AnalysisResult (+explain) |
| `/extract` | POST | `backend.extract` | `{content_type, document_base64}` → line items |
| `/letter` | POST | `backend.letter` | `{letter_type, patient, flags, line_items}` → draft |

## Run it

```
# from the repo root
python -m app_server.server --port 8000 [--data data/processed]
```

- **Offline by default.** With no `ANTHROPIC_API_KEY` set, a deterministic offline model
  client is used; the model-backed routes (`/extract`, `/explain` via analyze, `/letter`)
  return their standard fallback wording. Set `ANTHROPIC_API_KEY` (and the model id env
  vars) to use the real model.
- **Reference data** is loaded once from `--data` (default `data/processed`). With no
  processed data yet, `/procedures` and `/compare` return honest empty results — no
  invented numbers. Run `python -m pipeline.run all ...` first to populate real data.

## Quick check

```
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/procedures
curl "http://127.0.0.1:8000/compare?code=99213"
```

## Design

- `app.py` — pure `route(ctx, method, path, query, body) -> (status, dict)`. No
  `http.server` import, so it is unit-tested without a socket.
- `server.py` — thin `http.server` adapter: parse request, call `route`, write JSON,
  CORS enabled. Never logs request bodies.
- `clients.py` — picks the real Anthropic client if configured, else the offline fake;
  never fails startup over a missing key or package.

## Privacy / safety
- No request body or bill/patient content is ever logged.
- All string inputs are treated as inert data.
- Nothing is persisted.

## Dependencies
- Stdlib only for the server itself. The reused backend handlers require `jsonschema`
  (used by `backend/extract`); install it with the backends' dev requirements.
