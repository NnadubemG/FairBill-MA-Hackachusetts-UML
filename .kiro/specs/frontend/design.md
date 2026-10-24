# Design: Frontend (`/frontend`)

## Architecture
- React 18 + Vite 5 + TypeScript 5.
- `App.tsx` owns in-memory screen and line-item state; no router or persistence dependency.
- `src/lib/api.ts` switches between typed fixtures and same-origin `/api/*` using `VITE_USE_FIXTURES`.
- `@contracts` resolves to repo-root `contracts/index.ts`; types are not redefined.
- `src/lib/image.ts` converts an accepted PDF/image to the shared extraction contract, resizing images in-browser.
- `src/config/resources.ts` owns all Massachusetts links.
- Production compilation runs in the Docker Node stage and is copied into the FastAPI image.

## Accessibility
- A skip link and programmatic focus on the main region after screen changes.
- Visible focus outlines; explicit labels; semantic headings/table headers.
- Errors use `role=alert`; progress/notices use `role=status`.
- Text accompanies all status/color treatment; uncertain table rows include a label.
- Responsive table wrapper and sufficient text/background contrast.

## Privacy
Bill data exists only in React memory and request payloads. No local/session storage, cookies for bill content, or analytics are used.
