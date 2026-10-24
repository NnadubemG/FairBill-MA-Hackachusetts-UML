"""Plain-language explanations (`/backend/explain`).

Takes the ``Flag`` objects produced by ``/core`` and fills ``Flag.explanation`` with a
short, plain-language rewrite. One batched model call covers all flags. Every
explanation is checked by code; a flag whose explanation fails a check (or has none)
gets a deterministic fallback instead.

Owner: Sam. This package does not redefine any ``/contracts`` type.
"""
