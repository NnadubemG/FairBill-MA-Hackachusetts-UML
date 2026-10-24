"""Runnable HTTP server that wires the real backend handlers behind the app's routes.

Stdlib only (http.server). No new dependencies. Reuses the team's actual handlers and
contracts -- it does not reimplement any logic:

    POST /extract     -> backend.extract        (bill bytes -> LineItem[])
    POST /analyze     -> backend.analyze         (LineItem[] -> AnalysisResult, +explain)
    GET  /procedures  -> backend.compare         (curated procedure list)
    GET  /compare     -> backend.compare         (one code across hospitals)
    POST /letter      -> backend.letter          (flags -> LetterDraft)
    GET  /health      -> liveness

Runs offline by default: if ANTHROPIC_API_KEY is not set, a deterministic FakeLLMClient
is used, and the model-backed handlers (extract/explain/letter) fall back to their
standard wording. Set ANTHROPIC_API_KEY to use the real model.

Nothing is persisted and no request body is ever logged.
"""
