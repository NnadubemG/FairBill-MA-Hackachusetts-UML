"""Configuration for bill extraction.

All environment-dependent values are read here so the rest of the package stays
pure and testable. Model ids are NEVER hardcoded; they come from the environment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Environment variable names (values supplied by deployment, not by this repo).
ENV_MODEL_ID = "EXTRACT_MODEL_ID"
ENV_AWS_REGION = "AWS_REGION"

# Default AWS region if the environment does not set one. The model id has no
# default on purpose: an unset model id is an error, not a silent fallback.
DEFAULT_AWS_REGION = "us-east-1"


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
    """Return the Bedrock model id from the environment.

    Raises ConfigError if unset. We never hardcode or guess a model id.
    """
    model_id = os.environ.get(ENV_MODEL_ID, "").strip()
    if not model_id:
        raise ConfigError(
            f"{ENV_MODEL_ID} is not set. The real Bedrock client needs a model id "
            "from the environment; use the fake client for offline dev/tests."
        )
    return model_id


def get_region() -> str:
    """Return the AWS region, defaulting to DEFAULT_AWS_REGION."""
    return os.environ.get(ENV_AWS_REGION, "").strip() or DEFAULT_AWS_REGION


# Confidence ordering, low to high. Used to compare against Thresholds.confirm_below.
CONFIDENCE_ORDER: tuple[str, ...] = ("low", "medium", "high")


def is_below(confidence: str, floor: str) -> bool:
    """True if `confidence` ranks below `floor` in CONFIDENCE_ORDER."""
    return CONFIDENCE_ORDER.index(confidence) < CONFIDENCE_ORDER.index(floor)
