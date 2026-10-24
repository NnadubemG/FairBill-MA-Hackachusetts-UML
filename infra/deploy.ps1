# Build and deploy FairBill MA to AWS (Windows PowerShell).
# Requires: AWS CLI v2 + AWS SAM CLI, with credentials configured (aws configure / SSO).
#
#   .\infra\deploy.ps1                                  # offline/demo mode
#   .\infra\deploy.ps1 -SecretArn arn:aws:secretsmanager:... -ExtractModel <model> -ExplainModel <model> -LetterModel <model>
#
# The Anthropic key is NEVER passed here. Store it once in Secrets Manager:
#   aws secretsmanager create-secret --name fairbill/anthropic --secret-string '{"api_key":"<key>"}'
# and pass that secret's ARN as -SecretArn.

param(
  [string]$StackName = "fairbill-ma",
  [string]$Region = "us-east-1",
  [string]$SecretArn = "",
  [string]$ExtractModel = "",
  [string]$ExplainModel = "",
  [string]$LetterModel = "",
  [int]$MaxConcurrency = 10
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot

foreach ($tool in "aws", "sam") {
  if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "$tool is not installed or not on PATH." }
}

python "$repo\infra\build.py"
if ($LASTEXITCODE -ne 0) { throw "bundle build failed" }

Push-Location "$repo\infra"
try {
  sam deploy `
    --template-file template.yaml `
    --stack-name $StackName `
    --region $Region `
    --resolve-s3 `
    --capabilities CAPABILITY_IAM `
    --no-fail-on-empty-changeset `
    --parameter-overrides `
      "AnthropicSecretArn=$SecretArn" `
      "ExtractModelId=$ExtractModel" `
      "ExplainModelId=$ExplainModel" `
      "LetterModelId=$LetterModel" `
      "MaxConcurrency=$MaxConcurrency"
  if ($LASTEXITCODE -ne 0) { throw "sam deploy failed" }
  aws cloudformation describe-stacks --stack-name $StackName --region $Region `
    --query "Stacks[0].Outputs[?OutputKey=='PublicUrl'].OutputValue" --output text
} finally {
  Pop-Location
}
