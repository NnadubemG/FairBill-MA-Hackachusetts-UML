"""Shared pytest fixtures.

Ensures the repo root is importable (so `from contracts import ...` works even
when pytest is invoked without PYTHONPATH set) and resets per-test state.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# <repo>/server/tests/conftest.py -> repo root is parents[2]
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Each test starts with fresh rate-limit buckets."""
    from app.rate_limit import reset_limiter

    reset_limiter()
    yield
    reset_limiter()
