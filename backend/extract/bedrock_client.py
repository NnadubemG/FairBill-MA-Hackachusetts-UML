"""Bedrock client abstraction for extraction.

Three pieces:

- ``BedrockClient``: the Protocol the handler depends on. One method, ``invoke``,
  returns the model's raw JSON string (structured output).
- ``FakeBedrockClient``: a deterministic, offline client used for dev and tests until
  real model ids are available. No network, no randomness.
- ``make_client``: builds the real boto3-backed client. The model id is read from the
  environment (never hardcoded). boto3 is imported lazily so the fake path has no
  dependency on it.

Privacy: this module never logs prompts, document bytes, or model output.
"""

from __future__ import annotations

import hashlib
import json
from typing import Protocol, runtime_checkable

from . import config


class BedrockError(RuntimeError):
    """Raised when the real Bedrock call fails in a way the caller should handle."""


@runtime_checkable
class BedrockClient(Protocol):
    """What the extraction handler needs from a model client.

    ``content`` is a list of message content blocks (e.g. a document/image block and
    a text block). ``system`` is the system instruction. ``repair_hint``, when set,
    is a validation error message from a prior attempt, asking the model to fix its
    output. The return value is the model's raw response text (expected to be JSON).
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


class FakeBedrockClient:
    """Deterministic, offline stand-in for Bedrock.

    Construct it with scripted responses. Two lookup modes, checked in order:

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
        raise BedrockError(
            "FakeBedrockClient had no scripted response for this request "
            "(no fingerprint match, empty queue, no default)."
        )


class _RealBedrockClient:
    """boto3-backed Bedrock Runtime client. Not exercised until real ids exist.

    The model id comes from the environment via ``config.get_model_id()``. boto3 is
    imported here (lazily) so the fake path never needs it installed.
    """

    def __init__(self, model_id: str, region: str) -> None:
        import boto3  # lazy import; only required on the real path

        self._model_id = model_id
        self._runtime = boto3.client("bedrock-runtime", region_name=region)

    def invoke(
        self,
        *,
        system: str,
        content: list[dict],
        repair_hint: str | None = None,
    ) -> str:
        messages = [{"role": "user", "content": list(content)}]
        if repair_hint:
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Your previous output failed validation with this "
                                f"error: {repair_hint}. Return only corrected JSON "
                                "matching the required schema."
                            ),
                        }
                    ],
                }
            )
        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "system": system,
                "messages": messages,
                "max_tokens": 4096,
            }
        )
        try:
            resp = self._runtime.invoke_model(modelId=self._model_id, body=body)
            payload = json.loads(resp["body"].read())
            # Anthropic messages API: concatenate text blocks from the response.
            parts = [
                block.get("text", "")
                for block in payload.get("content", [])
                if block.get("type") == "text"
            ]
            return "".join(parts)
        except Exception as exc:  # noqa: BLE001 - surface as a handled error type
            # Do not include request/response bodies in the message (privacy).
            raise BedrockError(f"Bedrock invoke failed: {type(exc).__name__}") from exc


def make_client() -> BedrockClient:
    """Build the real Bedrock client. Model id comes from the environment.

    Raises ``config.ConfigError`` if the model id is unset. Use ``FakeBedrockClient``
    for offline dev and tests.
    """
    model_id = config.get_model_id()  # raises ConfigError if unset
    region = config.get_region()
    return _RealBedrockClient(model_id=model_id, region=region)


__all__ = [
    "BedrockClient",
    "BedrockError",
    "FakeBedrockClient",
    "make_client",
]
