# Requirements: Frontend (`/frontend`)

## Goal
A static React + Vite + TypeScript single-page app for a stressed, non-expert Massachusetts resident. The app is calm, plain-spoken, keeps the user in control, and uses `/contracts` as its only domain type source.

## Requirements
1. Provide Home, Confirm, Results, Letter, and Compare screens without login.
2. Home accepts pasted text plus PDF/image attachment; images are resized to an approximately 1800px maximum long edge and oversized PDFs are rejected with a clear message.
3. Confirm displays every extracted field in an editable semantic table, highlights `needs_confirmation` rows, and requires an explicit “Looks right” action.
4. Results displays per-line labels, Medicare reference, Massachusetts range, grounded flags, suggested questions, and a visible general-information note.
5. Letter provides type/recipient/context controls and an editable draft with copy and print controls; it does not send the draft.
6. Compare accepts a code and charged amount, displays references/flags, and reserves a chart component slot.
7. Use same-origin `/api/*`; support fixtures for development and the live API for production.
8. Do not persist bill content or include analytics.
9. Keep Massachusetts resource links in one configuration file and mark each for human verification before public release.
10. Meet keyboard, labeling, focus, contrast, heading, table, live-message, and upload accessibility needs.
11. Avoid the banned language defined in `.kiro/steering/product.md` in UI and model-facing copy.
