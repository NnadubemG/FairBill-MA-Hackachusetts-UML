#!/usr/bin/env bash
#
# Deploy helper for the Medical-Bill Helper (Render, single Docker web service).
#
# Render deploys are driven by the committed render.yaml blueprint. The normal
# flow is:
#   1. Push to the connected branch  -> Render auto-deploys (autoDeploy: true).
#   2. Or trigger a one-off deploy via a Render Deploy Hook URL.
#
# This script covers the Deploy Hook path and prints the manual steps. It does
# NOT bake secrets anywhere — the Anthropic key and model IDs are set in the
# Render dashboard (sync: false in render.yaml).
#
# Env:
#   RENDER_DEPLOY_HOOK_URL  (optional) a Render Deploy Hook URL for this service.
set -euo pipefail

echo "== Medical-Bill Helper — Render deploy =="
echo

if [[ -n "${RENDER_DEPLOY_HOOK_URL:-}" ]]; then
  echo "Triggering deploy via Deploy Hook..."
  curl -fsS -X POST "$RENDER_DEPLOY_HOOK_URL" && echo && echo "Deploy triggered."
  exit 0
fi

cat <<'EOF'
No RENDER_DEPLOY_HOOK_URL set. First-time / manual deploy:

  1. Commit and push (contracts/, server/, frontend/dist/, render.yaml).
  2. On Render: New -> Blueprint -> select this repo. Render reads render.yaml
     and provisions one Docker web service (build context = repo root).
  3. In the service's Environment, set the secrets:
       ANTHROPIC_API_KEY   = <your Anthropic key>
       EXTRACT_MODEL_ID    = <Anthropic model id for extraction>
       LETTER_MODEL_ID     = <Anthropic model id for letters>
  4. Deploy. The public URL is https://<service>.onrender.com
  5. Warm it once (free tier cold start ~30-60s):
       curl https://<service>.onrender.com/api/health

For scripted re-deploys, create a Deploy Hook (Settings -> Deploy Hook) and set
RENDER_DEPLOY_HOOK_URL, then re-run this script.
EOF
