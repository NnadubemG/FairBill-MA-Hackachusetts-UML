#!/usr/bin/env bash
# Local dev runner. Puts the shared /contracts package on PYTHONPATH and starts uvicorn.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$SERVER_DIR")"
export PYTHONPATH="$REPO_ROOT:${PYTHONPATH:-}"
cd "$SERVER_DIR"
exec uvicorn app.main:app --reload --port 8000
