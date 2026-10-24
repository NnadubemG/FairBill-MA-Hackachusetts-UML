---
inclusion: always
---

# Team and ownership

Four people, each using their own Kiro session. Stay inside your owned folders. If a task needs a change in
someone else's folder, stop and tell the user to coordinate with that person instead of editing it.

## Ownership

| Person | Role | Owns (can edit) | Produces |
|---|---|---|---|
| Thomas | Contracts, checks engine, Kiro workflow, writeup, video | /contracts, /core, /synthetic, /.kiro/steering, /.kiro/hooks, /docs | Shared schemas, deterministic checks (Flags), synthetic bills with ground truth, hooks, Kiro writeup, demo video |
| Sam | AI features | /backend/extract, /backend/explain, /backend/letter, /evals | Bill extraction (LineItems), plain-language explanations, letter drafts, eval results |
| ND | Data and visualization | /pipeline, /data/processed, /backend/compare, /frontend/src/compare | Processed price data, compare/lookup API, price charts |
| David | AWS and front end | /infra, /frontend (except /frontend/src/compare), deploy scripts | Public URL, API Gateway and Lambdas, CloudFront hosting, app screens |

## Shared, owned by one person

- /contracts is owned by Thomas. Everyone reads it. Never edit a schema outside Thomas's session.
  Request changes by describing the needed field and why. Changes must stay backward compatible.
- /.kiro/steering is owned by Thomas. Others may suggest additions.
- /docs/kiro-log.md: everyone appends one line when something notable happens. Do not rewrite others' lines.

## Interfaces (who depends on whom)

- ND -> everyone: /data/processed/*.json (hospitals, procedures, prices, medicare, ncci_pairs, chia_tiers).
  Thomas's /core and ND's compare API read these. The format is fixed by /contracts.
- Sam -> Thomas and David: extract returns LineItem[] plus bill metadata. Thomas's /core takes LineItem[]
  and returns Flag[]. The analyze handler combines core output with compare data.
- Thomas -> Sam and David: Flag[] is the only thing /core outputs. Sam's explain handler rewrites Flag.explanation.
- David -> everyone: the deployed stub URL and the API routes: POST /extract, POST /analyze, GET /procedures,
  GET /compare, POST /letter. Route names and response shapes follow /contracts.
- Thomas's synthetic bills + ground truth feed Sam's evals.

## Rules for working in parallel

- Work on your own git branch named <name>/<topic> (for example sam/extraction). Open a PR into main.
  Keep PRs small. Merge often so nobody drifts.
- Pull main before starting each new task.
- Do not reformat or "clean up" files you do not own.
- If main breaks, tell the team immediately and fix the breakage before adding features.
- Never commit raw data (/data/raw), /private, or secrets.
- Before merging, the relevant hook or test must pass:
  /core changes need pytest; /data or /pipeline changes need pipeline/validate.py.

## Handoff points (check at these times)

- 0:30: contracts and steering are committed and everyone has pulled them.
- 2:00: stub URL is live. First processed data exists. Extraction works on one bill. /core checks run on
  fixtures.
- 4:00: end-to-end flow works on the live URL with real processed data.
- 5:30: feature freeze. Only bug fixes after this.

## When unsure

Ask the user which person owns the thing. Do not guess and do not edit across ownership lines.
