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
_FENCED = re.compile(r"```[A-Za-z0-9_+-]*[ \t]*\r?\n?(.*?)\r?\n?```", re.DOTALL)
# An opening fence with no closing one (for example a reply cut off at the token limit).
_OPEN_FENCE = re.compile(r"^```[A-Za-z0-9_+-]*[ \t]*\r?\n?")


def strip_fence(raw: object) -> object:
    """Return the text inside the first code fence, or ``raw`` unchanged if none.

    Non-strings are returned unchanged.
    """
    if not isinstance(raw, str):
        return raw
    match = _FENCED.search(raw)
    if match:
        return match.group(1).strip()
    stripped = raw.strip()
    if stripped.startswith("```"):
        return _OPEN_FENCE.sub("", stripped, count=1).strip()
    return raw


def parse_model_json(raw: object) -> Any:
    """Parse the model's reply as JSON, accepting an optional code fence."""
    try:
        return json.loads(raw)  # type: ignore[arg-type]
    except (json.JSONDecodeError, TypeError):
        unfenced = strip_fence(raw)
        if unfenced is raw:  # nothing to strip: report the original error
            raise
        return json.loads(unfenced)  # type: ignore[arg-type]


__all__ = ["strip_fence", "parse_model_json"]
