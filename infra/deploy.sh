#!/usr/bin/env bash
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
STACK_NAME="${STACK_NAME:-fairbill-ma}"
SECRET_ARN="${SECRET_ARN:-}"
EXTRACT_MODEL="${EXTRACT_MODEL:-}"
EXPLAIN_MODEL="${EXPLAIN_MODEL:-}"
LETTER_MODEL="${LETTER_MODEL:-}"
BUDGET_EMAIL="${BUDGET_EMAIL:-}"
MONTHLY_BUDGET="${MONTHLY_BUDGET:-20}"
OFFLINE_MODE="${OFFLINE_MODE:-false}"
LOG="${TMPDIR:-/tmp}/fairbill-deploy.txt"
OUTPUT="${TMPDIR:-/tmp}/fairbill-stack-output.json"
PACKAGED="${TMPDIR:-/tmp}/fairbill-packaged.yaml"

if [[ "$OFFLINE_MODE" == "true" || -z "$SECRET_ARN" || -z "$EXTRACT_MODEL" || -z "$EXPLAIN_MODEL" || -z "$LETTER_MODEL" ]]; then
  OFFLINE_MODE=true
  SECRET_ARN="arn:aws:secretsmanager:${REGION}:000000000000:secret:offline"
  EXTRACT_MODEL=offline; EXPLAIN_MODEL=offline; LETTER_MODEL=offline
fi

python infra/build.py >"$LOG" 2>&1
if command -v sam >/dev/null 2>&1; then
  sam validate --lint --region "$REGION" --template-file infra/template.yaml >>"$LOG" 2>&1
else
  echo "SAM CLI unavailable locally; relying on CI sam validate --lint" >>"$LOG"
fi

ACCOUNT="$(aws sts get-caller-identity --query Account --output text 2>>"$LOG")" || {
  echo "AWS credentials missing; run aws login" >&2; exit 1;
}
ARTIFACT_BUCKET="${ARTIFACT_BUCKET:-fairbill-deploy-${ACCOUNT}-${REGION}}"
if ! aws s3api head-bucket --bucket "$ARTIFACT_BUCKET" 2>>"$LOG"; then
  if [[ "$REGION" == "us-east-1" ]]; then
    aws s3api create-bucket --bucket "$ARTIFACT_BUCKET" --region "$REGION" >>"$LOG" 2>&1
  else
    aws s3api create-bucket --bucket "$ARTIFACT_BUCKET" --region "$REGION" \
      --create-bucket-configuration "LocationConstraint=$REGION" >>"$LOG" 2>&1
  fi
  aws s3api put-public-access-block --bucket "$ARTIFACT_BUCKET" \
    --public-access-block-configuration \
    'BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true' >>"$LOG" 2>&1
  aws s3api put-bucket-encryption --bucket "$ARTIFACT_BUCKET" \
    --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}' >>"$LOG" 2>&1
fi

aws cloudformation package --template-file infra/template.yaml --s3-bucket "$ARTIFACT_BUCKET" \
  --output-template-file "$PACKAGED" --region "$REGION" >>"$LOG" 2>&1
aws cloudformation deploy --template-file "$PACKAGED" --stack-name "$STACK_NAME" \
  --region "$REGION" --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset \
  --parameter-overrides \
    "AnthropicSecretArn=$SECRET_ARN" "ExtractModelId=$EXTRACT_MODEL" \
    "ExplainModelId=$EXPLAIN_MODEL" "LetterModelId=$LETTER_MODEL" \
    "OfflineMode=$OFFLINE_MODE" "MonthlyBudgetAmount=$MONTHLY_BUDGET" \
    "BudgetEmail=$BUDGET_EMAIL" >>"$LOG" 2>&1
aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" \
  --query 'Stacks[0].Outputs' --output json >"$OUTPUT"
printf 'Deployment complete. Outputs: %s\nFull deploy log: %s\n' "$OUTPUT" "$LOG"
cat "$OUTPUT"
