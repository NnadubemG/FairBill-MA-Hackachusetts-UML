"""Application-level rate limiting (low burst + modest steady rate).

A small in-process token-bucket keyed by client IP. Two buckets per client:
  - a general bucket (RATE_LIMIT_PER_MIN / RATE_LIMIT_BURST)
  - a stricter model bucket (MODEL_RATE_LIMIT_PER_MIN) for extract/letter

Limits come from config (Requirement 6.4). Over-limit -> the dependency raises
HTTP 429, which the app's exception handler renders as the shared `ApiError`.

In-process state is fine for the hackathon single-instance deployment; it is
documented as such. (A multi-instance deployment would need a shared store.)
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict

from fastapi import HTTPException, Request, status

from app.config import get_settings


@dataclass
class _Bucket:
    capacity: float
    refill_per_sec: float
    tokens: float
    last: float = field(default_factory=time.monotonic)

    def allow(self) -> bool:
        now = time.monotonic()
        elapsed = now - self.last
        self.last = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_sec)
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


class _Limiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._general: Dict[str, _Bucket] = {}
        self._model: Dict[str, _Bucket] = {}

    @staticmethod
    def _client_key(request: Request) -> str:
        # Render sits behind a proxy; honor X-Forwarded-For's first hop if present.
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _check(self, store: Dict[str, _Bucket], key: str, per_min: int, burst: int) -> bool:
        with self._lock:
            bucket = store.get(key)
            if bucket is None:
                bucket = _Bucket(
                    capacity=float(burst),
                    refill_per_sec=per_min / 60.0,
                    tokens=float(burst),
                )
                store[key] = bucket
            return bucket.allow()

    def check_general(self, request: Request) -> None:
        s = get_settings()
        key = self._client_key(request)
        if not self._check(self._general, key, s.rate_limit_per_min, s.rate_limit_burst):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="rate_limited",
            )

    def check_model(self, request: Request) -> None:
        s = get_settings()
        key = self._client_key(request)
        # Model endpoints also consume the general bucket, then the stricter one.
        self.check_general(request)
        burst = min(s.rate_limit_burst, max(1, s.model_rate_limit_per_min))
        if not self._check(self._model, key, s.model_rate_limit_per_min, burst):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="rate_limited",
            )

    def reset(self) -> None:
        """Clear all buckets (used by tests)."""
        with self._lock:
            self._general.clear()
            self._model.clear()


_limiter = _Limiter()


def rate_limit_general(request: Request) -> None:
    """FastAPI dependency: enforce the general per-client rate limit."""
    _limiter.check_general(request)


def rate_limit_model(request: Request) -> None:
    """FastAPI dependency: enforce the stricter model-endpoint rate limit."""
    _limiter.check_model(request)


def reset_limiter() -> None:
    _limiter.reset()
