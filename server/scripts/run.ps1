# Local dev runner (Windows PowerShell).
# Puts the shared /contracts package on PYTHONPATH and starts uvicorn with reload.
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$env:PYTHONPATH = "$repoRoot;$env:PYTHONPATH"
Push-Location (Split-Path -Parent $PSScriptRoot)   # /server
try {
    uvicorn app.main:app --reload --port 8000
} finally {
    Pop-Location
}
