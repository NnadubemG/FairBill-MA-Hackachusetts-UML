"""Real client for letters.

Uses the shared Anthropic client from ``/backend/extract`` but reads the model name from
``LETTER_MODEL_ID`` (a small, cheap model), not from ``EXTRACT_MODEL_ID`` or
``EXPLAIN_MODEL_ID``. The API key comes from ``ANTHROPIC_API_KEY``. Neither value is
hardcoded or logged.

Tests and dev should use ``FakeLLMClient`` instead; it needs no key and no network.
"""

from __future__ import annotations

from backend.extract.llm_client import LLMClient, make_client

from . import config


def make_letter_client() -> LLMClient:
    """Build the real client for letters.

    Raises ``backend.extract.config.ConfigError`` if ``LETTER_MODEL_ID`` or
    ``ANTHROPIC_API_KEY`` is unset.
    """
    return make_client(model_env_var=config.ENV_MODEL_ID)


__all__ = ["make_letter_client"]
