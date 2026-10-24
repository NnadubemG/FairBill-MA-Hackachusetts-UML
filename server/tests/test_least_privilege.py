"""TC-3: Key never leaks / least-privilege import split.

Static checks:
  - Only extract.py and letter.py import `anthropic_client`.
  - The four non-model routers do NOT import it.
Runtime check:
  - No endpoint response contains the (test) key string.
"""

from __future__ import annotations

import re
from pathlib import Path

ROUTERS = Path(__file__).resolve().parents[1] / "app" / "routers"

_IMPORT_RE = re.compile(r"anthropic_client")


def _imports_anthropic(path: Path) -> bool:
    return bool(_IMPORT_RE.search(path.read_text(encoding="utf-8")))


def test_only_extract_and_letter_import_anthropic_client():
    offenders = []
    for py in ROUTERS.glob("*.py"):
        if py.name in {"extract.py", "letter.py", "__init__.py"}:
            continue
        if _imports_anthropic(py):
            offenders.append(py.name)
    assert offenders == [], f"non-model routers import anthropic_client: {offenders}"


def test_extract_and_letter_do_import_anthropic_client():
    assert _imports_anthropic(ROUTERS / "extract.py")
    assert _imports_anthropic(ROUTERS / "letter.py")


def test_key_absent_from_responses(monkeypatch):
    secret = "sk-ant-TESTSECRET-should-never-appear"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)

    # Rebuild settings so the env var is picked up.
    import app.config as config

    config._settings = None  # type: ignore[attr-defined]

    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    for method, path, kwargs in [
        ("get", "/api/health", {}),
        ("get", "/api/procedures", {}),
        ("get", "/api/compare", {"params": {"code": "99213", "charged": 10000}}),
        ("post", "/api/analyze", {"json": {"line_items": []}}),
    ]:
        r = getattr(client, method)(path, **kwargs)
        assert secret not in r.text
