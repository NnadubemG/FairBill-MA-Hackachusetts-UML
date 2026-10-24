> **SUPERSEDED — replaced by the server spec (direct Anthropic API, no AWS).**
> Kept for historical reference only. Do not implement.

# Requirements: Infrastructure (`/infra`)

## Introduction

This spec defines the AWS infrastructure for the Hackachusetts-UML application, provisioned
with **AWS CDK (TypeScript)**. The infrastructure hosts a static frontend behind CloudFront,
exposes a REST/HTTP API backed by Python 3.12 Lambda functions, and grants two of those
Lambdas scoped access to Amazon Bedrock models. Security, least-privilege IAM, abuse
protection, and privacy-preserving logging are first-class requirements.

A key delivery constraint: a **stub (static page + health-check Lambda) must be deployed
first** so a public URL exists early in the hackathon, before the full backend is ready.

### Glossary
- **Stub**: Minimal deployable slice — a placeholder static page served via CloudFront and a
  single `GET /health` Lambda — used to validate the pipeline and produce a public URL quickly.
- **Core/Data**: Shared Python code (`/core`) and precomputed artifacts (`/data/processed`)
  bundled into the Lambda deployment packages.

---

## Requirements

### Requirement 1: Static frontend hosting
**User Story:** As a user, I want to load the web frontend from a fast, secure public URL, so
that I can use the application in a browser.

#### Acceptance Criteria
1. WHEN the stack is deployed THEN the system SHALL create a **private** S3 bucket (no public
   access, block-all-public-access enabled) that stores the contents of `/frontend/dist`.
2. WHEN a user requests the site URL THEN CloudFront SHALL serve the frontend content from the
   private bucket using an Origin Access Control (OAC), not a public bucket policy.
3. WHEN CloudFront serves content THEN it SHALL enforce HTTPS (redirect HTTP to HTTPS).
4. WHEN a deep link (SPA route) is requested THEN CloudFront SHALL return `index.html` with a
   200 for navigational 403/404 responses (SPA fallback).
5. WHEN the stack outputs are produced THEN the system SHALL output the **CloudFront URL**.

### Requirement 2: API surface
**User Story:** As a frontend, I want a well-defined API, so that I can call backend
operations over HTTPS.

#### Acceptance Criteria
1. WHEN the stack is deployed THEN the system SHALL expose an API Gateway with the routes:
   `POST /extract`, `POST /analyze`, `GET /procedures`, `GET /compare`, `POST /letter`.
2. WHEN the stub is deployed THEN the API SHALL expose `GET /health` returning 200 and a
   minimal JSON body.
3. WHEN the stack outputs are produced THEN the system SHALL output the **API URL**.
4. WHERE the API type is chosen THEN the system SHALL use **HTTP API (API Gateway v2)** for
   lower cost/latency unless a REST-only feature is required, and this choice SHALL be
   documented in the design.

### Requirement 3: Lambda compute
**User Story:** As an operator, I want each route handled by its own Python 3.12 Lambda, so
that permissions and failures are isolated.

#### Acceptance Criteria
1. WHEN the stack is deployed THEN each route SHALL be backed by its own **Python 3.12**
   Lambda function with code from `/backend`.
2. WHEN a Lambda is bundled THEN the deployment package SHALL include the shared `/core`
   module and the `/data/processed` artifacts needed at runtime.
3. WHEN a Lambda runs THEN it SHALL receive model IDs via **environment variables** (not
   hard-coded).

### Requirement 4: Least-privilege IAM
**User Story:** As a security reviewer, I want every Lambda to hold only the permissions it
needs, so that blast radius is minimized.

#### Acceptance Criteria
1. WHEN IAM roles are created THEN each Lambda SHALL have its own execution role.
2. THE **extract** and **letter** Lambdas SHALL be granted `bedrock:InvokeModel`
   (and `bedrock:InvokeModelWithResponseStream` if streaming is used) scoped to the specific
   model ARNs derived from the configured model IDs.
3. THE `analyze`, `procedures`, `compare`, and `health` Lambdas SHALL NOT have any Bedrock
   permissions.
4. NO Lambda SHALL be granted wildcard (`*`) resource access for Bedrock.
5. EACH Lambda SHALL have only the CloudWatch Logs permissions required to write to its own
   log group, and no other permissions beyond what its handler requires.

### Requirement 5: CORS
**User Story:** As a frontend developer, I want the API to accept requests from the CloudFront
domain, so that the browser does not block calls.

#### Acceptance Criteria
1. WHEN the API receives a request from the CloudFront domain THEN CORS SHALL allow that
   origin, the methods used by the routes, and the required headers.
2. WHEN a request arrives from a non-allowed origin THEN the API SHALL NOT return permissive
   CORS headers for that origin.
3. WHERE a browser sends a preflight `OPTIONS` THEN the API SHALL respond with the correct
   CORS headers.

### Requirement 6: Abuse protection (throttling)
**User Story:** As an operator, I want request throttling, so that the API is protected from
abuse and runaway cost.

#### Acceptance Criteria
1. WHEN the API is deployed THEN it SHALL enforce a **low burst limit** and a modest steady
   rate limit at the stage/route level.
2. WHEN clients exceed the configured rate or burst THEN the API SHALL return HTTP 429.
3. THE throttle values SHALL be defined as configurable constants in the CDK code.

### Requirement 7: Privacy-preserving logging
**User Story:** As a privacy-conscious operator, I want only errors logged and never request
or response bodies, so that sensitive content is never persisted.

#### Acceptance Criteria
1. WHEN a Lambda or the API logs THEN it SHALL log **errors only** (no info/debug request
   tracing that includes payloads).
2. THE system SHALL NEVER log request bodies or response bodies to CloudWatch.
3. WHERE API Gateway access logging is enabled THEN the log format SHALL exclude request and
   response bodies.
4. THE design SHALL document how body logging is prevented at each layer.

### Requirement 8: Stub-first delivery
**User Story:** As the team, I want a public URL early, so that we can integrate and demo
before the full backend exists.

#### Acceptance Criteria
1. THE first deployable increment SHALL be a **stub**: a static placeholder page served via
   CloudFront and a single `GET /health` Lambda, with real CloudFront and API URLs output.
2. THE stub SHALL be deployable with the same deploy script used for the full stack.

### Requirement 9: Operational tooling
**User Story:** As a developer, I want simple deploy and teardown, so that I can iterate and
clean up fast during the hackathon.

#### Acceptance Criteria
1. THE system SHALL provide a **deploy script** that builds, bundles, and deploys the stack.
2. THE system SHALL provide a **one-line teardown command** that destroys all stack resources.
3. THE S3 bucket and log groups SHALL be configured so teardown removes them cleanly
   (removal policy / auto-delete suitable for a hackathon environment).

### Requirement 10: Verifiable test cases
**User Story:** As a reviewer, I want documented test cases, so that I can confirm the
infrastructure behaves correctly.

#### Acceptance Criteria
1. THE design SHALL list concrete test cases covering at minimum: **health check**, **CORS**,
   **throttling**, and an **IAM least-privilege check**.
2. EACH test case SHALL state its precondition, action, and expected result.
