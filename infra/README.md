# FairBill MA AWS deployment

The production stack is one Python 3.12 Lambda Function URL behind CloudFront. The Lambda serves both static frontend files and the six JSON routes. CloudFront is the only public origin caller: Origin Access Control signs origin requests, so users cannot bypass CloudFront by calling the Function URL directly.

## Current live URL

**Pending first deployment.** After deployment, copy the `CloudFrontUrl` stack output here.

## Prerequisites

- AWS CLI v2
- AWS SAM CLI
- Python 3.12
- AWS credentials able to manage CloudFormation, Lambda, IAM, CloudFront, Secrets Manager, CloudWatch Logs, S3 deployment artifacts, and AWS Budgets
- A replacement Anthropic key because the prior key was exposed
- Direct Anthropic model IDs for extraction, explanation, and letters

Verify identity without printing credentials:

```powershell
aws sts get-caller-identity
```

## Secret rotation

Create the replacement key in the Anthropic console. Do not paste it into source files, `.env`, CloudFormation parameters, deployment logs, or chat. Store it only in Secrets Manager:

```powershell
aws secretsmanager create-secret `
  --name fairbill/anthropic `
  --secret-string '{"api_key":"<NEW_KEY>"}'
```

If the secret already exists, rotate its value:

```powershell
aws secretsmanager put-secret-value `
  --secret-id fairbill/anthropic `
  --secret-string '{"api_key":"<NEW_KEY>"}'
```

Then revoke the exposed key in the Anthropic console. Record only the returned secret ARN—not the secret value.

## Offline first deployment

Offline mode needs no Anthropic secret or model IDs. It verifies packaging, CloudFront, routes, static assets, reference data, and fixed fallback behavior:

```powershell
.\infra\deploy.ps1 -Offline -BudgetEmail you@example.com
```

The script writes detailed output under `%TEMP%`, not the repository. AWS Budget email subscriptions require confirmation from the recipient.

## Live deployment

```powershell
.\infra\deploy.ps1 `
  -SecretArn <secret-arn> `
  -ExtractModel <direct-anthropic-model-id> `
  -ExplainModel <direct-anthropic-model-id> `
  -LetterModel <direct-anthropic-model-id> `
  -BudgetEmail you@example.com
```

The deployment script:
1. runs `infra/build.py` to create the ignored `infra/build/` Lambda bundle;
2. runs `sam validate --lint` when SAM is available locally (CI always runs it);
3. creates or reuses a private, encrypted S3 artifact bucket;
4. uses AWS CLI `cloudformation package` and `cloudformation deploy`;
5. writes stack outputs to `%TEMP%\fairbill-stack-output.json`.

Set `-Region` or `-StackName` to override `us-east-1` and `fairbill-ma`.

## Update

Pull current `main`, run the required checks, and rerun the same deployment command. CloudFormation updates the stack and CloudFront distribution in place.

```powershell
python -m pytest -q
python -m pipeline.validate
.\infra\deploy.ps1 -SecretArn <arn> -ExtractModel <id> -ExplainModel <id> -LetterModel <id> -BudgetEmail you@example.com
```

## Smoke test

Automated HTTP checks:

```powershell
python infra/smoke.py <cloudfront-url> --expect-live --large-upload
```

Then use a private browser window and check:
- home page and browser console (no CSP errors);
- every available sample through confirm and results;
- itemized-bill, coding-review, and financial-assistance letters;
- compare page;
- PDF upload;
- `/health` reports `model: live` after live secret configuration.

Infrastructure verification:

```powershell
# Reserved concurrency
aws lambda get-function-concurrency --function-name fairbill-ma-app

# Cache behavior and security headers
aws cloudfront get-distribution-config --id <DistributionId>

# Recent logs: inspect only metadata; bill content must be absent
aws logs tail /aws/lambda/fairbill-ma-app --since 15m
```

Expected behavior:
- `/health`, `/procedures`, `/compare`, `/extract`, `/analyze`, and `/letter` use the managed CloudFront caching-disabled policy and return `Cache-Control: no-store`.
- Static files use CloudFront’s caching-optimized policy and return a short public `max-age`.
- CSP permits the current inline compare page scripts/styles while blocking external scripts, frames, and objects.
- A roughly 4 MB raw PDF becomes about 5.3 MB after base64 encoding and stays below the 6 MB synchronous request cap.
- Lambda reserved concurrency defaults to 5.
- Application code logs only the generic `ERROR request_failed` marker.

## Rollback

List recent stack events and deploy a known-good Git revision with the same parameters:

```powershell
aws cloudformation describe-stack-events --stack-name fairbill-ma --max-items 30
# check out the known-good revision, then rerun infra/deploy.ps1
```

For a failed CloudFormation update, AWS normally rolls back automatically. Confirm `StackStatus` before retrying.

## Tear down

```powershell
sam delete --stack-name fairbill-ma --region us-east-1 --no-prompts
aws secretsmanager delete-secret --secret-id fairbill/anthropic --recovery-window-in-days 7
```

Secret deletion has a recovery window. Do not use immediate deletion unless the account owner explicitly accepts that risk.

## Cost and abuse controls

- The CloudFront URL is public and has no login. Automated clients can still create Lambda and Anthropic spend.
- Function URL direct access is blocked with IAM and CloudFront OAC, preventing a simple CloudFront bypass.
- Reserved concurrency limits simultaneous Lambda work but is not a per-user rate limit.
- The optional AWS Budget sends forecasted alerts at 80% and actual alerts at 100% of the monthly amount (default `$20`). Budgets notify; they do not stop spend.
- CloudFront does not provide a strict request-rate cap here. Before wider use, add AWS WAF rate-based rules, authentication, or both. WAF has its own cost, so it is not included automatically.
- Model-backed endpoints are the primary cost risk. Monitor Lambda invocations, Anthropic usage, and CloudFront request volume during the event.

## Compromises and pending checks

- The infrastructure files described as prebuilt were absent from all fetched Git refs and were reconstructed on `David_T3`.
- The latest `main` currently exposes the compare page but not the complete multi-screen frontend described in the smoke checklist. Deployment can proceed, but full browser-flow acceptance depends on that frontend being merged by its owner.
- A real deployment requires account credentials, a newly rotated Anthropic key, three approved model IDs, and a budget notification email. None are stored in this repository.
