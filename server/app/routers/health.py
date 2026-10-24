"""GET /api/health — liveness check.

No secrets, no Anthropic client. Also used as Render's health check path.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
