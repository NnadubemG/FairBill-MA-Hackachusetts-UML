"""LLM client abstraction (direct Anthropic API).

Three pieces:

- ``LLMClient``: the Protocol the handler depends on. One method, ``invoke``,
  returns the model's raw text (expected to be JSON).
- ``FakeLLMClient``: a deterministic, offline client for dev and tests. No network,
  no randomness.
- ``make_client``: builds the real client that calls the Anthropic Messages API. The
  API key comes from ``ANTHROPIC_API_KEY`` and the model name from an environment
  variable. Neither is ever hardcoded. The ``anthropic`` package is imported lazily so
  the fake path (and all tests) need no install and no network.

Privacy: this module never logs prompts, document bytes, model output, or the API key.
Errors carry only the exception type.
"""

from __future__ import annotations

import hashlib
import json
from typing import Protocol, runtime_checkable

from . import config

# Upper bound on the model's reply. Extraction output is a short JSON object.
DEFAULT_MAX_TOKENS = 4096
# Seconds to wait for the API before giving up (the handler then uses its fallback).
DEFAULT_TIMEOUT_SECONDS = 60.0


class LLMError(RuntimeError):
    """Raised when the real model call fails in a way the caller should handle."""


@runtime_checkable
class LLMClient(Protocol):
    """What the extraction handler needs from a model client.

    ``content`` is a list of Anthropic-format content blocks (e.g. an image or
    document block and a text block). ``system`` is the system instruction.
    ``repair_hint``, when set, is a validation error message from a prior attempt,
    asking the model to fix its output. The return value is the model's raw reply
    text (expected to be JSON).
    """

    def invoke(
        self,
        *,
        system: str,
        content: list[dict],
        repair_hint: str | None = None,
    ) -> str: ...


def _fingerprint(system: str, content: list[dict], repair_hint: str | None) -> str:
    """Stable hash of the request, used to look up scripted fake responses.

    Deterministic: the same request always maps to the same key, with no reliance on
    dict ordering, clock, or randomness.
    """
    payload = json.dumps(
        {"system": system, "content": content, "repair_hint": repair_hint},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class FakeLLMClient:
    """Deterministic, offline stand-in for the real model.

    Construct it with scripted responses. Lookup modes, checked in order:

    1. ``by_fingerprint``: maps a request fingerprint (see ``fingerprint``) to a raw
       response string. Use this to script an exact request/response pair.
    2. ``responses``: a FIFO queue of raw response strings, consumed one per
       ``invoke`` call. Use this for simple ordered scripting (e.g. invalid output on
       the first call, valid on the retry).

    If ``raise_on_invoke`` is set, every ``invoke`` raises it, to exercise the
    deterministic fallback path. ``default`` is returned when no scripted response
    matches.
    """

    def __init__(
        self,
        *,
        by_fingerprint: dict[str, str] | None = None,
        responses: list[str] | None = None,
        default: str | None = None,
        raise_on_invoke: Exception | None = None,
    ) -> None:
        self._by_fingerprint = dict(by_fingerprint or {})
        self._queue = list(responses or [])
        self._default = default
        self._raise = raise_on_invoke
        self.calls = 0  # number of invoke() calls, for tests to assert on

    @staticmethod
    def fingerprint(
        system: str, content: list[dict], repair_hint: str | None = None
    ) -> str:
        """Expose the request fingerprint so tests can script by_fingerprint."""
        return _fingerprint(system, content, repair_hint)

    def invoke(
        self,
        *,
        system: str,
        content: list[dict],
        repair_hint: str | None = None,
    ) -> str:
        self.calls += 1
        if self._raise is not None:
            raise self._raise

        key = _fingerprint(system, content, repair_hint)
        if key in self._by_fingerprint:
            return self._by_fingerprint[key]
        if self._queue:
            return self._queue.pop(0)
        if self._default is not None:
            return self._default
        raise LLMError(
            "FakeLLMClient had no scripted response for this request "
            "(no fingerprint match, empty queue, no default)."
        )


class _AnthropicClient:
    """Real client: calls the Anthropic Messages API.

    The ``anthropic`` package is imported here (lazily) so the fake path never needs
    it installed. The API key is passed to the SDK and is not stored anywhere else.
    """

    def __init__(self, api_key: str, model: str) -> None:
        import anthropic  # lazy import; only required on the real path

        self._model = model
        self._client = anthropic.Anthropic(
            api_key=api_key, timeout=DEFAULT_TIMEOUT_SECONDS
        )

    def invoke(
        self,
        *,
        system: str,
        content: list[dict],
        repair_hint: str | None = None,
    ) -> str:
        # The bill stays in its own content block. Our instructions are separate text
        # blocks. A repair hint is another text block in the same user turn.
        blocks = list(content)
        if repair_hint:
            blocks.append(
                {
                    "type": "text",
                    "text": (
                        "Your previous output failed validation with this error: "
                        f"{repair_hint}. Return only corrected JSON matching the "
                        "required schema."
                    ),
                }
            )
        try:
            message = self._client.messages.create(
                model=self._model,
                max_tokens=DEFAULT_MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": blocks}],
            )
            return "".join(
                block.text
                for block in message.content
                if getattr(block, "type", None) == "text"
            )
        except Exception as exc:  # noqa: BLE001 - surface as a handled error type
            # Only the exception type goes in the message (privacy: never include
            # request or response bodies, or anything that could hold the API key).
            # "from None" drops the original exception so it cannot be logged later.
            raise LLMError(f"Model call failed: {type(exc).__name__}") from None


def make_client() -> LLMClient:
    """Build the real client. API key and model name come from the environment.

    Raises ``config.ConfigError`` if ``ANTHROPIC_API_KEY`` or the model name is unset.
    Use ``FakeLLMClient`` for offline dev and tests.
    """
    api_key = config.get_api_key()  # raises ConfigError if unset
    model = config.get_model_id()  # raises ConfigError if unset
    return _AnthropicClient(api_key=api_key, model=model)


__all__ = [
    "LLMClient",
    "LLMError",
    "FakeLLMClient",
    "make_client",
]
