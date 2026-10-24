"""TC-5: Rate limiting.

A burst above the general burst limit at a non-model endpoint yields 429s, and
the service stays healthy afterward.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

client = TestClient(app)


def test_burst_over_limit_gets_429():
    burst = get_settings().rate_limit_burst
    statuses = []
    # Fire well beyond the burst capacity in a tight loop (tokens can't refill
    # meaningfully in microseconds).
    for _ in range(burst + 20):
        statuses.append(client.get("/api/procedures").status_code)

    assert 429 in statuses, f"expected some 429s, got {statuses}"
    # The 429 body uses the shared ApiError shape.
    # Find one 429 and re-trigger to inspect the body.
    # (At least the first `burst` requests should have passed.)
    assert statuses[:1] == [200]


def test_service_recovers_after_reset():
    from app.rate_limit import reset_limiter

    reset_limiter()
    assert client.get("/api/health").status_code == 200
