"""Model client selection: real Anthropic client if configured, else offline fake.

The app must run for a demo with no API key. The backend handlers already degrade
gracefully when the client fails, so an offline fake that returns nothing usable simply
yields standard fallback wording rather than an error.
"""

from __future__ import annotations

import os

from backend.extract.llm_client import FakeLLMClient, LLMClient


def get_client() -> tuple[LLMClient, bool]:
    """Return (client, is_real).

    If ANTHROPIC_API_KEY is set, try the real Anthropic client. On any failure building
    it (missing package, bad config), fall back to the offline fake so the server still
    starts. Without the key, use the fake directly.
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from backend.extract.llm_client import make_client

            return make_client(), True
        except Exception:
            # Fall through to the offline client; never fail server startup on this.
            pass
    # Offline: no scripted responses -> handlers take their deterministic fallback path.
    return FakeLLMClient(default=""), False
