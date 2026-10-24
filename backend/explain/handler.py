"""Explain handler: one batched model call, checked per flag, with fallbacks.

Flow (see the design doc):
  flags -> one model call -> parse -> for each flag: accept the model text, or use the
  deterministic fallback -> same flags with ``explanation`` set.

Any failure in the model path (call, parsing) turns into fallbacks for every flag. The
handler does not raise for an expected model failure and does not retry. Nothing about
the flags or the model reply is logged or written to disk.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Sequence

from backend.extract.llm_client import LLMClient

from . import config, prompts
from ._contracts import Flag
from .checks import accept
from .models import ExplainResult
from .templates import fallback

# Fixed, generic warning. Never contains flag text.
WARN_MODEL_UNAVAILABLE = (
    "The AI helper was not available, so standard wording was used for the explanations."
)


def explain(flags: Sequence[Flag], *, client: LLMClient) -> ExplainResult:
    """Fill ``Flag.explanation`` for every flag.

    ``client`` is injected (use ``FakeLLMClient`` for dev and tests). At most one model
    call is made. Flags beyond ``MAX_FLAGS_PER_CALL`` use the fallback.
    """
    all_flags = list(flags)
    if not all_flags:
        return ExplainResult()

    batch = all_flags[: config.MAX_FLAGS_PER_CALL]
    valid_keys = {prompts.key_for(i) for i in range(len(batch))}

    # --- the single model call; any failure means "no model text" ---------------
    model_text: dict[str, str] = {}
    warnings: list[str] = []
    try:
        raw = client.invoke(
            system=prompts.build_system_prompt(),
            content=prompts.build_user_content(batch),
            max_tokens=prompts.compute_max_tokens(len(batch)),
        )
        model_text = prompts.parse_response(raw, valid_keys)
    except Exception:  # noqa: BLE001 - deterministic fallback for ANY model failure
        # No exception detail is kept or logged (privacy).
        model_text = {}
    if not model_text:
        warnings.append(WARN_MODEL_UNAVAILABLE)

    # --- per flag: use the model text only if it passes every check -------------
    out: list[Flag] = []
    fallback_count = 0
    for index, flag in enumerate(all_flags):
        text = model_text.get(prompts.key_for(index)) if index < len(batch) else None
        if text is not None and accept(text, flag):
            explanation = text.strip()
        else:
            explanation = fallback(flag)
            fallback_count += 1
        out.append(replace(flag, explanation=explanation))

    return ExplainResult(flags=out, fallback_count=fallback_count, warnings=warnings)


__all__ = ["explain", "WARN_MODEL_UNAVAILABLE"]
