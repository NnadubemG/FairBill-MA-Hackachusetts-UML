> **SUPERSEDED — replaced by the server spec (direct Anthropic API, no AWS).**
> Kept for historical reference only. Do not implement.

# Design: Infrastructure (`/infra`)

## Overview

The infrastructure is a single AWS CDK v2 (TypeScript) application in `/infra`. It provisions:

- A **private S3 bucket** holding the built frontend (`/frontend/dist`), fronted by a
  **CloudFront** distribution using **Origin Access Control (OAC)**.
- An **HTTP API (API Gateway v2)** with six routes (`/health` for the stub plus the five app
  routes), each integrated with a dedicated **Python 3.12 Lambda**.
- **Per-Lambda IAM roles** following least privilege; only `extract` and `letter` can invoke
  Bedrock, scoped to specific model ARNs.
- **CORS** limited to the CloudFront origin, **throttling** with a low burst limit, and
  **error-only logging** that never records request/response bodies.

> **MCP note:** The AWS Documentation MCP server was not available in this workspace at spec
> time. This design is grounded in AWS CDK v2 and AWS best practices. If the MCP server is
> added later, re-verify construct names/props (notably `BucketDeployment`, `S3Origin` vs
> `S3BucketOrigin`, and `HttpApi` throttling) against current docs during implementation.

### API type decision (Requirement 2.4)
We use **HTTP API (API Gateway v2)**. Rationale: lower cost and latency, native CORS config,
built-in JWT/none auth, and simpler route-to-Lambda integration. The app needs none of the
REST-only features (API keys/usage plans, request validation models, WAF-at-stage, edge-
optimized endpoints). Throttling is available on HTTP APIs at the stage (default route) and
per-route level, which satisfies Requirement 6.

---

## Architecture

```
                      ┌──────────────────────────────────────────┐
   Browser  ──HTTPS──►│ CloudFront (OAC, HTTPS only, SPA fallback)│
                      └───────────────┬──────────────────────────┘
                                      │ (origin: OAC-signed)
                              ┌───────▼────────┐
                              │ Private S3     │  frontend/dist
                              │ (block public) │
                              └────────────────┘

   Browser  ──HTTPS──► HTTP API (API GW v2)  ── CORS: CloudFront origin only
                        │   throttle: burst=low, rate=modest
                        │
       ┌────────────┬───┴────────┬────────────┬────────────┬───────────┐
       ▼            ▼            ▼            ▼            ▼           ▼
   POST /extract POST /analyze GET /procedures GET /compare POST /letter GET /health
       │            │            │            │            │           │
   Lambda(py3.12) …each its own function + own IAM role…              Lambda
       │                                                   │
   Bedrock:InvokeModel (scoped ARNs)              Bedrock:InvokeModel (scoped ARNs)
   [extract only]                                 [letter only]
```

### Project layout
```
/infra
  ├─ bin/infra.ts                 # CDK app entrypoint
  ├─ lib/infra-stack.ts           # main stack
  ├─ lib/config.ts                # tunables (throttle limits, model IDs, allowed origin)
  ├─ cdk.json
  ├─ package.json
  ├─ tsconfig.json
  ├─ scripts/deploy.ps1           # build frontend + bundle + cdk deploy
  ├─ scripts/deploy.sh            # same for bash
  └─ README.md                    # deploy + teardown instructions

/backend
  ├─ handlers/
  │   ├─ health.py                # GET /health  (stub)
  │   ├─ extract.py               # POST /extract (Bedrock)
  │   ├─ analyze.py               # POST /analyze
  │   ├─ procedures.py            # GET /procedures
  │   ├─ compare.py               # GET /compare
  │   └─ letter.py                # POST /letter  (Bedrock)
  └─ requirements.txt

/core                             # shared python, bundled into each lambda
/data/processed                   # precomputed artifacts, bundled where needed
/frontend/dist                    # built static site (CloudFront origin)
```

---

## Components and Interfaces

### 1. Frontend hosting (S3 + CloudFront)
- **S3 bucket**: `blockPublicAccess: BLOCK_ALL`, `encryption: S3_MANAGED`,
  `removalPolicy: DESTROY` + `autoDeleteObjects: true` (hackathon-friendly teardown).
- **CloudFront**: `Distribution` with a single S3 origin created via
  `S3BucketOrigin.withOriginAccessControl(bucket)` (OAC, the current recommended pattern;
  older code uses OAI — do not use OAI). `viewerProtocolPolicy: REDIRECT_TO_HTTPS`,
  `defaultRootObject: 'index.html'`.
- **SPA fallback**: `errorResponses` mapping 403 and 404 → `/index.html` with 200.
- **Deployment**: `BucketDeployment` with `Source.asset('../frontend/dist')` and
  `distribution` + `distributionPaths: ['/*']` so deploys invalidate the CDN cache.
- For the **stub**, `/frontend/dist` contains a single placeholder `index.html`.

### 2. API (HTTP API v2)
- `HttpApi` with `corsPreflight` restricted to the CloudFront origin (see CORS below).
- Default stage with throttling (see Throttling below) and `autoDeploy: true`.
- Routes map method+path to a `HttpLambdaIntegration` wrapping the route's function.

| Method | Path          | Lambda       | Bedrock |
|--------|---------------|--------------|---------|
| GET    | /health       | `health`     | no      |
| POST   | /extract      | `extract`    | **yes** |
| POST   | /analyze      | `analyze`    | no      |
| GET    | /procedures   | `procedures` | no      |
| GET    | /compare      | `compare`    | no      |
| POST   | /letter       | `letter`     | **yes** |

### 3. Lambda functions (Python 3.12)
- Each route = one `lambda.Function` (`runtime: PYTHON_3_12`), `handler: <file>.handler`.
- **Bundling** `/core` and `/data/processed`: build the deployment asset by copying
  `backend/handlers`, `core/`, and the needed `data/processed/` artifacts into a staging dir.
  Options, in order of preference:
  1. `lambda.Code.fromAsset` with a **local bundling** command (`cp`/`Copy-Item`) that stages
     `handlers + core + data/processed` — no Docker required, fastest for a hackathon.
  2. If native deps are needed, `fromAsset` with Docker `bundling` using the
     `public.ecr.aws/sambda/python:3.12` build image and `pip install -r requirements.txt -t`.
  - Keep `/data/processed` payload small; if it grows large, move to a **Lambda layer** or
    fetch from S3 at runtime (documented as a follow-up, not needed for the stub).
- **Environment variables**: `EXTRACT_MODEL_ID`, `LETTER_MODEL_ID` injected from
  `lib/config.ts`; handlers read model IDs from `os.environ`.
- **Memory/timeout**: Bedrock Lambdas get higher timeout (e.g. 30s) and memory (e.g. 512MB);
  others use modest defaults.

### 4. IAM (least privilege)
- CDK creates a distinct execution role per function automatically (default managed policy
  grants only that function's log group writes — satisfies Req 4.5).
- **extract** and **letter** roles get a narrow inline policy:
  ```
  Action:   bedrock:InvokeModel  (+ InvokeModelWithResponseStream if streaming)
  Resource: arn:aws:bedrock:<region>::foundation-model/<EXTRACT_MODEL_ID>
            arn:aws:bedrock:<region>::foundation-model/<LETTER_MODEL_ID>
  ```
  Model ARNs are derived from the configured model IDs — **no wildcard resource**.
  If inference profiles are used, the policy also scopes to the profile ARN in the account.
- `analyze`, `procedures`, `compare`, `health`: **no Bedrock, no extra permissions.**

### 5. CORS (Requirement 5)
- `HttpApi.corsPreflight`:
  - `allowOrigins: [ '<CloudFront domain>' ]` — exact origin, not `*`.
  - `allowMethods: [GET, POST, OPTIONS]`.
  - `allowHeaders: ['content-type']` (+ auth header if added later).
  - `maxAge: Duration.hours(1)`.
- **Chicken/egg**: the CloudFront domain is created in the same stack. Resolve by either
  (a) referencing `distribution.distributionDomainName` (a token) directly in the CORS config
  so both are created in one `cdk deploy`, or (b) for the stub, deploy CloudFront first and
  pass the domain via context. Preferred: option (a) — CDK orders the dependency correctly.
- Non-allowed origins simply do not receive matching ACAO headers (browser blocks them).

### 6. Throttling (Requirement 6)
- Defined in `lib/config.ts`:
  ```ts
  export const THROTTLE = { rateLimit: 10, burstLimit: 5 }; // req/s steady, burst
  ```
- Applied to the HTTP API default stage `throttle`. Exceeding → API Gateway returns **429**.
- Values are intentionally low for a hackathon; documented as tunable.

### 7. Logging (Requirement 7 — privacy)
Body logging is prevented at **every layer**:
- **Lambda handlers**: configure the Python logger at `ERROR` level. Handlers must not
  `log(event)` or `log(response)`. A shared `core/logging.py` helper exposes `log_error(msg)`
  that accepts only non-body metadata (route, status, request id).
- **API Gateway access logs**: if enabled, use a custom log format containing only
  `requestId, httpMethod, routeKey, status, responseLatency` — **no `$context.integration...`
  body fields, no `$input.body`.** Recommended: keep access logging minimal or disabled for
  the stub; enable the metadata-only format for the full stack.
- **No execution/data tracing** that captures payloads is enabled (no full request/response
  logging, no X-Ray payload capture).
- Log groups get a short retention (e.g. `ONE_WEEK`) and `removalPolicy: DESTROY`.

### 8. Outputs
- `CfnOutput` **CloudFrontUrl** = `https://<distribution domain>`.
- `CfnOutput` **ApiUrl** = HTTP API endpoint.

---

## Configuration (`lib/config.ts`)
```ts
export const ALLOWED_ORIGIN_PLACEHOLDER = true; // resolved to distribution domain at synth
export const THROTTLE = { rateLimit: 10, burstLimit: 5 };
export const MODELS = {
  extract: process.env.EXTRACT_MODEL_ID ?? 'anthropic.claude-3-5-sonnet-20241022-v2:0',
  letter:  process.env.LETTER_MODEL_ID  ?? 'anthropic.claude-3-5-sonnet-20241022-v2:0',
};
export const LOG_RETENTION_DAYS = 7;
```
Model IDs come from environment at deploy time and are passed into Lambda env vars.

---

## Error Handling
- Lambda handlers catch exceptions, log **error-only** metadata (no bodies), and return a
  structured JSON error (`{ "error": "<code>" }`) with an appropriate status.
- API Gateway returns 429 on throttle, 403 on disallowed CORS preflight, 5xx on Lambda faults.
- CloudFront returns `index.html` (200) for 403/404 navigation (SPA), preserving real API
  errors which go through the API domain, not CloudFront.

---

## Testing Strategy

All tests are runnable post-deploy against the live stack (hackathon-appropriate smoke/
integration tests). `{API_URL}` and `{CF_URL}` come from the stack outputs.

### TC-1 Health check
- **Precondition:** Stub (or full stack) deployed.
- **Action:** `curl -s -o /dev/null -w "%{http_code}" {API_URL}/health`
- **Expected:** `200`, body is minimal JSON (e.g. `{"status":"ok"}`), no sensitive data.

### TC-2 Frontend reachability
- **Precondition:** Stack deployed, bucket populated.
- **Action:** `curl -I {CF_URL}`
- **Expected:** `200`, served over HTTPS; HTTP request to the domain redirects to HTTPS.

### TC-3 CORS — allowed origin
- **Precondition:** Stack deployed; CloudFront domain known.
- **Action:** Preflight:
  `curl -i -X OPTIONS {API_URL}/extract -H "Origin: {CF_URL}" -H "Access-Control-Request-Method: POST"`
- **Expected:** `204/200` with `Access-Control-Allow-Origin: {CF_URL}` and allowed methods.

### TC-4 CORS — disallowed origin
- **Action:** Same preflight with `-H "Origin: https://evil.example.com"`.
- **Expected:** Response does **not** include `Access-Control-Allow-Origin: https://evil.example.com`.

### TC-5 Throttling / burst
- **Precondition:** `THROTTLE` set low (e.g. rate 10, burst 5).
- **Action:** Fire a rapid burst (e.g. 50 requests in <1s) at `GET /procedures`.
- **Expected:** At least some responses return **429** (throttled); the API stays healthy.

### TC-6 IAM least-privilege check
- **Action (automated):** For each Lambda role, dump its policies:
  `aws iam list-role-policies` / `get-role-policy` (or inspect the synthesized CloudFormation
  template with `cdk synth`).
- **Expected:**
  - `extract` and `letter` roles contain `bedrock:InvokeModel` scoped to the two model ARNs,
    **no `Resource: "*"`** for Bedrock.
  - `analyze`, `procedures`, `compare`, `health` roles contain **no `bedrock:*`** actions.
  - No role grants permissions beyond logs + its explicit needs.

### TC-7 No-body logging check
- **Action:** Invoke `POST /extract` with a known unique string in the body; then search its
  CloudWatch log group for that string.
- **Expected:** The unique body string is **absent** from logs; only error-level metadata (if
  any error occurred) is present.

### TC-8 Teardown
- **Action:** Run the one-line teardown command.
- **Expected:** Stack deletes cleanly; S3 bucket (and objects) and log groups are removed;
  no orphaned resources remain.

---

## Deploy & Teardown

### Deploy script (`scripts/deploy.ps1` / `.sh`)
Steps:
1. (Full stack) build the frontend into `/frontend/dist`; (stub) ensure placeholder exists.
2. `npm ci` in `/infra`.
3. `cdk bootstrap` (first time only).
4. `EXTRACT_MODEL_ID=... LETTER_MODEL_ID=... cdk deploy --require-approval never`.
5. Print the `CloudFrontUrl` and `ApiUrl` outputs.

### One-line teardown
```
cd infra && npx cdk destroy --force
```
(Bucket auto-deletes objects; log groups have DESTROY removal policy, so nothing is left behind.)
