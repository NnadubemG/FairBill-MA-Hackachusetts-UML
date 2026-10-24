param(
    [string]$SecretArn = "",
    [string]$ExtractModel = "",
    [string]$ExplainModel = "",
    [string]$LetterModel = "",
    [string]$Region = "us-east-1",
    [string]$StackName = "fairbill-ma",
    [string]$ArtifactBucket = "",
    [string]$BudgetEmail = "",
    [decimal]$MonthlyBudget = 20,
    [switch]$Offline
)

$ErrorActionPreference = "Stop"
$log = Join-Path $env:TEMP "fairbill-deploy.txt"
$output = Join-Path $env:TEMP "fairbill-stack-output.json"
$packaged = Join-Path $env:TEMP "fairbill-packaged.yaml"
$template = Join-Path $PSScriptRoot "template.yaml"
$repo = Split-Path -Parent $PSScriptRoot

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = "C:\Users\dontm\AppData\Local\Programs\Python\Python312\python.exe" }
$aws = (Get-Command aws -ErrorAction SilentlyContinue).Source
if (-not $aws -and (Test-Path "C:\Program Files\Amazon\AWSCLIV2\aws.exe")) {
    $aws = "C:\Program Files\Amazon\AWSCLIV2\aws.exe"
}
if (-not $aws) { throw "AWS CLI v2 is required" }

$offlineMode = $Offline -or [string]::IsNullOrWhiteSpace($SecretArn) -or
    [string]::IsNullOrWhiteSpace($ExtractModel) -or
    [string]::IsNullOrWhiteSpace($ExplainModel) -or
    [string]::IsNullOrWhiteSpace($LetterModel)
if ($offlineMode) {
    $SecretArn = "arn:aws:secretsmanager:${Region}:000000000000:secret:offline"
    $ExtractModel = "offline"; $ExplainModel = "offline"; $LetterModel = "offline"
}

"Building Lambda bundle" | Out-File $log
& $python (Join-Path $PSScriptRoot "build.py") *>> $log
if ($LASTEXITCODE -ne 0) { throw "Bundle build failed; see $log" }

# SAM lint runs in CI via aws-actions/setup-sam. Use it locally too when present.
$sam = (Get-Command sam -ErrorAction SilentlyContinue).Source
if ($sam) {
    & $sam validate --lint --region $Region --template-file $template *>> $log
    if ($LASTEXITCODE -ne 0) { throw "SAM validation failed; see $log" }
} else {
    "SAM CLI unavailable locally; relying on CI sam validate --lint" | Out-File $log -Append
}

$identityRaw = & $aws sts get-caller-identity --output json 2>> $log
if ($LASTEXITCODE -ne 0) { throw "AWS credentials missing. Run 'aws login', then retry. See $log" }
$account = ($identityRaw | ConvertFrom-Json).Account
if (-not $ArtifactBucket) { $ArtifactBucket = "fairbill-deploy-$account-$Region".ToLowerInvariant() }

& $aws s3api head-bucket --bucket $ArtifactBucket 2>> $log
if ($LASTEXITCODE -ne 0) {
    if ($Region -eq "us-east-1") {
        & $aws s3api create-bucket --bucket $ArtifactBucket --region $Region *>> $log
    } else {
        & $aws s3api create-bucket --bucket $ArtifactBucket --region $Region `
            --create-bucket-configuration "LocationConstraint=$Region" *>> $log
    }
    if ($LASTEXITCODE -ne 0) { throw "Could not create artifact bucket; see $log" }
    & $aws s3api put-public-access-block --bucket $ArtifactBucket `
        --public-access-block-configuration `
        "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true" *>> $log
    & $aws s3api put-bucket-encryption --bucket $ArtifactBucket `
        --server-side-encryption-configuration `
        '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}' *>> $log
}

& $aws cloudformation package --template-file $template --s3-bucket $ArtifactBucket `
    --output-template-file $packaged --region $Region *>> $log
if ($LASTEXITCODE -ne 0) { throw "CloudFormation packaging failed; see $log" }

$params = @(
    "AnthropicSecretArn=$SecretArn", "ExtractModelId=$ExtractModel",
    "ExplainModelId=$ExplainModel", "LetterModelId=$LetterModel",
    "OfflineMode=$($offlineMode.ToString().ToLowerInvariant())",
    "MonthlyBudgetAmount=$MonthlyBudget", "BudgetEmail=$BudgetEmail"
)
& $aws cloudformation deploy --template-file $packaged --stack-name $StackName `
    --region $Region --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset `
    --parameter-overrides $params *>> $log
if ($LASTEXITCODE -ne 0) { throw "CloudFormation deployment failed; see $log" }

& $aws cloudformation describe-stacks --stack-name $StackName --region $Region `
    --query "Stacks[0].Outputs" --output json | Out-File $output -Encoding utf8
Write-Host "Deployment complete. Outputs: $output"
Write-Host "Full deploy log: $log"
Get-Content $output
