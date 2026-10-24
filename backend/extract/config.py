"""Configuration for bill extraction.

All environment-dependent values are read here so the rest of the package stays
pure and testable. The model name and the API key are NEVER hardcoded; they come from
the environment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Environment variable names (values are supplied by the environment, not this repo).
# Neither value has a default on purpose: unset is an error, not a silent fallback.
ENV_MODEL_ID = "EXTRACT_MODEL_ID"  # Anthropic model name used for extraction
ENV_API_KEY = "ANTHROPIC_API_KEY"  # secret: never hardcode, commit, or log


class ConfigError(RuntimeError):
    """Raised when required configuration is missing (e.g. the model id)."""


@dataclass(frozen=True)
class Thresholds:
    """Tunable, deterministic post-processing thresholds.

    Kept here (not in code) so they are easy to find and label. None of these
    invent data; they only decide when a line is marked for user confirmation.
    """

    # A line whose model confidence is below this is marked needs_confirmation.
    confirm_below: str = "high"  # one of "high" | "medium" | "low"


def get_model_id() -> str:
    """Return the Anthropic model name from the environment.

    Raises ConfigError if unset. We never hardcode or guess a model name.
    """
    model_id = os.environ.get(ENV_MODEL_ID, "").strip()
    if not model_id:
        raise ConfigError(
            f"{ENV_MODEL_ID} is not set. The real client needs a model name "
            "from the environment; use the fake client for offline dev/tests."
        )
    return model_id


def get_api_key() -> str:
    """Return the Anthropic API key from the environment.

    Raises ConfigError if unset. The error names the variable only, never a value.
    """
    api_key = os.environ.get(ENV_API_KEY, "").strip()
    if not api_key:
        raise ConfigError(
            f"{ENV_API_KEY} is not set. The real client needs an API key from the "
            "environment; use the fake client for offline dev/tests."
        )
    return api_key


# Confidence ordering, low to high. Used to compare against Thresholds.confirm_below.
CONFIDENCE_ORDER: tuple[str, ...] = ("low", "medium", "high")


def is_below(confidence: str, floor: str) -> bool:
    """True if `confidence` ranks below `floor` in CONFIDENCE_ORDER."""
    return CONFIDENCE_ORDER.index(confidence) < CONFIDENCE_ORDER.index(floor)
