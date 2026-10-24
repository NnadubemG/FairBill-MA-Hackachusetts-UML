"""Thin wrapper over the official Anthropic SDK.

LEAST-PRIVILEGE RULE (enforced structurally + by test TC-3):
  This module is imported ONLY by `app/routers/extract.py` and
  `app/routers/letter.py`. The non-model handlers (health, analyze, procedures,
  compare) must never import it.

The wrapper:
  - builds the client from the server-side `ANTHROPIC_API_KEY` (a SecretStr),
  - never logs prompt or response text,
  - raises a small, body-free error type on failure so callers can map it to the
    shared `ApiError` shape without leaking content.
"""

from __future__ import annotations

from typing import Optional

from app.config import get_settings


class AnthropicConfigError(RuntimeError):
    """Raised when a required piece of Anthropic config is missing.

    Carries only a short, non-sensitive message (never a key or body).
    """


class AnthropicCallError(RuntimeError):
    """Raised when an Anthropic API call fails.

    Carries only a short, non-sensitive message (never prompt/response text).
    """


def _require_key() -> str:
    settings = get_settings()
    if settings.anthropic_api_key is None:
        raise AnthropicConfigError("ANTHROPIC_API_KEY is not configured")
    return settings.anthropic_api_key.get_secret_value()


def complete(
    *,
    model: str,
    system: str,
    user_content: str,
    document_base64: Optional[str] = None,
    document_media_type: Optional[str] = None,
    max_tokens: int = 2048,
    temperature: float = 0.2,
) -> str:
    """Send a single-turn message to Anthropic and return its text response.

    An optional base64 PDF/image is represented using Anthropic's document/image
    content block. Prompt, document, and response content are not logged.
    """
    if not model:
        raise AnthropicConfigError("model id is not configured")

    api_key = _require_key()

    try:
        import anthropic
    except Exception as exc:  # pragma: no cover - import environment issue
        raise AnthropicConfigError("anthropic SDK is not available") from exc

    content: list[dict] = []
    if document_base64 and document_media_type:
        block_type = "document" if document_media_type == "application/pdf" else "image"
        content.append(
            {
                "type": block_type,
                "source": {
                    "type": "base64",
                    "media_type": document_media_type,
                    "data": document_base64,
                },
            }
        )
    content.append({"type": "text", "text": user_content})

    client = anthropic.Anthropic(api_key=api_key)
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": content}],
        )
    except Exception as exc:
        raise AnthropicCallError(type(exc).__name__) from exc

    parts: list[str] = []
    for block in getattr(resp, "content", []) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


def extract_model_id() -> Optional[str]:
    return get_settings().extract_model_id


def letter_model_id() -> Optional[str]:
    return get_settings().letter_model_id
