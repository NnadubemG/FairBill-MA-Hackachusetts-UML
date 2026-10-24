> **SUPERSEDED — replaced by the server spec (direct Anthropic API, no AWS).**
> Kept for historical reference only. Do not implement.

# Implementation Plan: Infrastructure (`/infra`)

> Stub-first: tasks 1–5 deliver a deployed public URL (static page + health check) before the
> full backend. Tasks 6+ flesh out the real routes, IAM, CORS, throttling, logging, and tests.

- [-] 1. Scaffold the CDK TypeScript app in `/infra`
  - Initialize a CDK v2 app: `bin/infra.ts`, `lib/infra-stack.ts`, `cdk.json`, `package.json`,
    `tsconfig.json`.
  - Add `lib/config.ts` with `THROTTLE`, `MODELS`, and `LOG_RETENTION_DAYS` tunables.
  - _Requirements: 3.3, 6.3, 9_

- [~] 2. Create the stub static page
  - Add a placeholder `frontend/dist/index.html` ("deploying…" page).
  - _Requirements: 8.1_

- [~] 3. Implement the private S3 bucket + CloudFront (OAC) with SPA fallback
  - Private bucket (`BLOCK_ALL`, encrypted, `autoDeleteObjects`, `DESTROY`).
  - CloudFront distribution via `S3BucketOrigin.withOriginAccessControl`, HTTPS redirect,
    `defaultRootObject`, 403/404 → `/index.html` (200).
  - `BucketDeployment` from `../frontend/dist` with cache invalidation.
  - Output `CloudFrontUrl`.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 9.3_

- [~] 4. Implement the health-check Lambda + HTTP API with `GET /health`
  - `backend/handlers/health.py` returning `{"status":"ok"}` (200), error-level logger only.
  - `HttpApi` with `GET /health` → health Lambda; output `ApiUrl`.
  - _Requirements: 2.2, 2.3, 2.4, 3.1, 7.1_

- [~] 5. Write deploy script + teardown and do the first stub deploy
  - `scripts/deploy.ps1` and `scripts/deploy.sh` (npm ci, bootstrap, deploy, print outputs).
  - Document one-line teardown (`npx cdk destroy --force`) in `infra/README.md`.
  - Deploy the stub; confirm `CloudFrontUrl` and `ApiUrl` are live. **(Public URL milestone.)**
  - _Requirements: 8.1, 8.2, 9.1, 9.2_

- [~] 6. Add Lambda bundling for `/core` and `/data/processed`
  - Create a reusable function that builds a `lambda.Code.fromAsset` staging
    `handlers + core + data/processed` (local bundling; Docker path documented as fallback).
  - _Requirements: 3.1, 3.2_

- [~] 7. Implement the five app-route Lambdas and wire routes
  - Handlers: `extract.py`, `analyze.py`, `procedures.py`, `compare.py`, `letter.py`
    (stub bodies returning valid JSON initially; business logic comes from the backend spec).
  - Routes: `POST /extract`, `POST /analyze`, `GET /procedures`, `GET /compare`,
    `POST /letter` → their Lambdas.
  - Inject `EXTRACT_MODEL_ID` / `LETTER_MODEL_ID` env vars.
  - _Requirements: 2.1, 3.1, 3.3_

- [~] 8. Apply least-privilege IAM
  - Grant **only** `extract` and `letter` a narrow `bedrock:InvokeModel` policy scoped to the
    two model ARNs (no wildcard). Confirm the other roles have no Bedrock permissions.
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [~] 9. Configure CORS for the CloudFront origin
  - `corsPreflight` allowing exactly the CloudFront domain, methods (GET/POST/OPTIONS),
    and `content-type`.
  - _Requirements: 5.1, 5.2, 5.3_

- [~] 10. Configure throttling (low burst)
  - Apply `THROTTLE` (low burst + modest rate) to the HTTP API default stage.
  - _Requirements: 6.1, 6.2, 6.3_

- [~] 11. Enforce privacy-preserving, error-only logging
  - Shared `core/logging.py` `log_error(metadata)` (never bodies). Set loggers to ERROR.
  - If access logging is enabled, use a metadata-only format (no body fields). Short retention.
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [~] 12. Add the post-deploy test scripts (TC-1 … TC-8)
  - Script the health, frontend, CORS (allow/deny), throttling, IAM least-privilege (via
    `cdk synth`/`aws iam`), no-body-logging, and teardown checks from the design.
  - _Requirements: 10.1, 10.2, and verification of 1,2,4,5,6,7,9_

- [~] 13. Full-stack deploy and verification
  - Build the real frontend, deploy the full stack, run TC-1…TC-8, record outputs.
  - _Requirements: all_
