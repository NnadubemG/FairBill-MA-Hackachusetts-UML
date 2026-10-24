"""Parse the model's JSON reply, tolerating a markdown code fence.

Models sometimes wrap JSON in a fence (three backticks, optionally followed by ``json``),
sometimes with a short sentence before it. ``parse_model_json`` accepts all of these.

Plain JSON is always tried first, so valid JSON that happens to contain backticks inside
a string (for example in a line description from a bill) is never changed. Only when the
plain parse fails do we look for a fence. Failures raise the same exceptions as
``json.loads`` (``JSONDecodeError``, or ``TypeError`` for a non-string), so callers keep
their existing error handling.

Pure: no logging, no I/O. The reply text is untrusted data and is only parsed.
"""

from __future__ import annotations

import json
import re
from typing import Any

# A complete fenced block: ```lang\n ... ``` (the language tag is optional).
# "Lazy" stops at the first closing fence; "greedy" stops at the last one. The greedy form
# is needed when the JSON itself contains three backticks inside a string.
_FENCED_LAZY = re.compile(r"```[A-Za-z0-9_+-]*[ \t]*\r?\n?(.*?)\r?\n?```", re.DOTALL)
_FENCED_GREEDY = re.compile(r"```[A-Za-z0-9_+-]*[ \t]*\r?\n?(.*)\r?\n?```", re.DOTALL)
# An opening fence with no closing one (for example a reply cut off at the token limit).
_OPEN_FENCE = re.compile(r"^```[A-Za-z0-9_+-]*[ \t]*\r?\n?")


def strip_fence(raw: object) -> object:
    """Return the text inside the first code fence, or ``raw`` unchanged if none.

    Non-strings are returned unchanged.
    """
    if not isinstance(raw, str):
        return raw
    match = _FENCED_LAZY.search(raw)
    if match:
        return match.group(1).strip()
    stripped = raw.strip()
    if stripped.startswith("```"):
        return _OPEN_FENCE.sub("", stripped, count=1).strip()
    return raw


def _candidates(raw: str) -> list[str]:
    """Texts to try parsing, in order: the reply as is, then fence contents."""
    found: list[str] = [raw]
    for pattern in (_FENCED_GREEDY, _FENCED_LAZY):
        match = pattern.search(raw)
        if match:
            found.append(match.group(1).strip())
    stripped = raw.strip()
    if stripped.startswith("```"):
        found.append(_OPEN_FENCE.sub("", stripped, count=1).strip())
    unique: list[str] = []
    for text in found:
        if text not in unique:
            unique.append(text)
    return unique


def parse_model_json(raw: object) -> Any:
    """Parse the model's reply as JSON, accepting an optional code fence.

    Tries the reply as is, then the text inside a fence (widest block first, then the
    first block), and returns the first one that parses. If none parse, raises the error
    from the reply as is (``JSONDecodeError``; ``TypeError`` for a non-string).
    """
    if not isinstance(raw, str):
        return json.loads(raw)  # type: ignore[arg-type]  # raises TypeError, as before
    first_error: json.JSONDecodeError | None = None
    for text in _candidates(raw):
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            first_error = first_error or exc
    assert first_error is not None
    raise first_error


__all__ = ["strip_fence", "parse_model_json"]
