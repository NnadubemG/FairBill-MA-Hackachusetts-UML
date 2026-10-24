# Frontend shell

Dependency-free browser modules for the medical-bill flow. This shell uses the canonical dollar-based contract shapes from `/contracts` and consumes ND's `src/compare` component without changing it.

## Run

From the repository root:

```powershell
python -m http.server 5500 --directory frontend
```

Open `http://127.0.0.1:5500`.

The price comparison screen calls the currently available `GET /compare?code=...` route. Extraction, analysis, and letter screens call the team-agreed `POST /extract`, `POST /analyze`, and `POST /letter` routes. Until those HTTP adapters are deployed at the same origin, the shell displays a clear unavailable state; the example-bill path allows the confirm/results UI to be reviewed without inventing reference values.

## Validation

```powershell
node --check frontend/src/app.mjs
node --check frontend/src/api.mjs
node --check frontend/src/image.mjs
node --test "frontend/src/compare/tests/*.test.mjs"
```

## Privacy and accessibility

- Bill values stay in page memory and request payloads; there is no analytics or browser persistence.
- Images are resized in-browser to a maximum 1800-pixel edge; PDFs above 4 MB are rejected before upload.
- Inputs have labels, status messages are announced, keyboard focus moves to each screen, table headers are semantic, uncertain rows have text as well as color, and a skip link is provided.
- Massachusetts resource links are centralized in `src/resources.mjs` and marked for human verification before public release.
