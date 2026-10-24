#!/usr/bin/env bash
# Build and deploy FairBill MA to AWS (macOS/Linux).
# Requires: AWS CLI v2 + AWS SAM CLI, with credentials configured.
#
#   ./infra/deploy.sh                       # offline/demo mode
#   SECRET_ARN=arn:... EXTRACT_MODEL=<model> EXPLAIN_MODEL=<model> LETTER_MODEL=<model> ./infra/deploy.sh
#
# The Anthropic key is never passed here; store it in Secrets Manager and pass its ARN.
set -euo pipefail
cd "$(dirname "$0")/.."

STACK_NAME="${STACK_NAME:-fairbill-ma}"
REGION="${REGION:-us-east-1}"

command -v aws >/dev/null || { echo "aws CLI not found"; exit 1; }
command -v sam >/dev/null || { echo "sam CLI not found"; exit 1; }

python3 infra/build.py

cd infra
sam deploy \
  --template-file template.yaml \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --resolve-s3 \
  --capabilities CAPABILITY_IAM \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    "AnthropicSecretArn=${SECRET_ARN:-}" \
    "ExtractModelId=${EXTRACT_MODEL:-}" \
    "ExplainModelId=${EXPLAIN_MODEL:-}" \
    "LetterModelId=${LETTER_MODEL:-}" \
    "MaxConcurrency=${MAX_CONCURRENCY:-10}"

aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='PublicUrl'].OutputValue" --output text
