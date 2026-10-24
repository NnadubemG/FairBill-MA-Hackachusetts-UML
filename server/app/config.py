"""Environment-driven settings for the server.

Uses pydantic-settings so config comes from the environment (and a local `.env`).
Secrets (the Anthropic key) use `SecretStr` so they are never accidentally printed
or serialized.

NOTE: For the stub (health check only), `ANTHROPIC_API_KEY` and the model IDs are
NOT required — the stub must run with zero secrets so we can get a public URL early.
They become required once the `extract`/`letter` handlers are implemented; that check
is enforced in those handlers (Requirement 4.4), not at stub startup.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- server ---
    # Render injects PORT; default 8000 for local dev.
    port: int = Field(default=8000, alias="PORT")
    host: str = Field(default="0.0.0.0", alias="HOST")

    # --- CORS ---
    # Comma-separated string of exact allowed origins. Empty => same-origin only.
    # Stored as a raw string (not List[str]) so pydantic-settings reads it
    # literally from the env rather than attempting to JSON-decode it. The parsed
    # list is exposed via the `allowed_origins` property below.
    allowed_origins_raw: str = Field(default="", alias="ALLOWED_ORIGINS")

    # --- Anthropic (optional for the stub; needed by extract/letter later) ---
    anthropic_api_key: Optional[SecretStr] = Field(default=None, alias="ANTHROPIC_API_KEY")
    extract_model_id: Optional[str] = Field(default=None, alias="EXTRACT_MODEL_ID")
    letter_model_id: Optional[str] = Field(default=None, alias="LETTER_MODEL_ID")

    # --- rate limiting (used when middleware is added) ---
    rate_limit_per_min: int = Field(default=30, alias="RATE_LIMIT_PER_MIN")
    rate_limit_burst: int = Field(default=5, alias="RATE_LIMIT_BURST")
    model_rate_limit_per_min: int = Field(default=10, alias="MODEL_RATE_LIMIT_PER_MIN")

    @property
    def allowed_origins(self) -> List[str]:
        """Exact allowed CORS origins, parsed from the comma-separated env value.

        Empty list => same-origin only (no CORS middleware added).
        """
        raw = self.allowed_origins_raw or ""
        return [o.strip() for o in raw.split(",") if o.strip()]


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Return a cached Settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
