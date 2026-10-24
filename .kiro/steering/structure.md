---
inclusion: always
---

# Repository structure

```
/contracts          JSON Schema source of truth + TS/Python mirrors  (owner: Thomas)
/core               Deterministic checks engine, pure Python 3.12     (owner: Thomas)
/synthetic          Synthetic bill generator for testing/demos        (owner: Thomas)
/.kiro/steering     Project rules and conventions                     (owner: Thomas)
/.kiro/hooks        Agent hooks (prefer script-based)                 (owner: Thomas)
/docs               kiro-log.md and writeup material
/private            Local-only. Never committed. Never logged.
```

## Ownership
Thomas owns: Kiro workflow, `/contracts`, `/core`, `/synthetic`, hooks, writeup,
video. Others depend on `/contracts` and `/.kiro/steering`, so those stay backward
compatible and schema breaks are announced first.

## Hard rules on files
- Never add `.kiro` to `.gitignore`.
- Never commit anything from `/private`.
- No secrets in git.
