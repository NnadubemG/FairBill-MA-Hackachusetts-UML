# Frontend

Static React + Vite + TypeScript application for the Massachusetts Medical-Bill Helper. FastAPI serves the production build from `frontend/dist` at the same origin as `/api/*`.

## Run locally

Requires Node.js 18 or newer.

```powershell
cd frontend
npm install
npm run dev
```

Vite runs at `http://localhost:5173` and proxies `/api` to FastAPI at `http://localhost:8000`.

The UI uses fixtures by default. To exercise the real API in local development:

```powershell
$env:VITE_USE_FIXTURES = "false"
npm run dev
```

## Validate and build

```powershell
cd frontend
npm install
npm run build
```

`npm run build` runs the TypeScript check and emits the production site into `frontend/dist`.

## Render build

No locally generated frontend artifacts are required for deployment. `server/Dockerfile` contains a Node build stage that installs the pinned frontend packages, sets `VITE_USE_FIXTURES=false`, compiles the app, and copies the resulting `dist` into the Python runtime image.

## Screens and safeguards

- Home: paste text or attach a PDF/image; images are resized in the browser.
- Confirm: every extracted field is editable; uncertain rows are highlighted.
- Results: plain-language descriptions, reference prices, grounded flags, and next questions.
- Letter: editable draft with copy and print controls.
- Compare: code/price lookup plus a reserved chart slot.
- Shared domain types are imported from repo-root `/contracts`.
- Bill content is kept in memory only; there is no analytics or browser persistence.
- Massachusetts resource links are centralized in `src/config/resources.ts` and remain marked for human verification before public release.

## Handoff note

The frontend was validated on the original machine after invoking Node through its
full Windows path: dependencies installed successfully, TypeScript passed, and Vite
produced `frontend/dist`. A teammate can independently repeat `npm ci` and
`npm run build`; Render performs the same build in Linux when deploying from `main`.
