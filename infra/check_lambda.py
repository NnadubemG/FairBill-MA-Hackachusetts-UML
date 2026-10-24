"""Offline, no-network smoke check for app_server.lambda_handler."""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.update(
    {
        "OFFLINE_MODE": "true",
        "DATA_DIR": str(ROOT / "data" / "processed"),
        "STATIC_DIR": str(ROOT / "frontend" / "src" / "compare"),
    }
)

from app_server.lambda_handler import handler  # noqa: E402


def invoke(method: str, path: str, payload: dict | None = None, query: str = "") -> tuple[int, dict, bytes]:
    body = None if payload is None else json.dumps(payload)
    event = {
        "version": "2.0",
        "rawPath": path,
        "rawQueryString": query,
        "requestContext": {"http": {"method": method}},
        "body": body,
        "isBase64Encoded": False,
    }
    result = handler(event, None)
    raw = base64.b64decode(result["body"]) if result.get("isBase64Encoded") else result["body"].encode()
    return result["statusCode"], result["headers"], raw


def main() -> int:
    status, headers, raw = invoke("GET", "/health")
    health = json.loads(raw)
    assert status == 200 and health == {"status": "ok", "model": "offline-fallback"}
    assert headers["cache-control"] == "no-store"

    status, headers, raw = invoke("GET", "/")
    assert status == 200 and b"FairBill MA" in raw
    assert "max-age" in headers["cache-control"]

    assert invoke("GET", "/procedures")[0] == 200
    assert invoke("GET", "/compare", query="code=99213")[0] == 200
    assert invoke("POST", "/analyze", {"line_items": []})[0] == 200

    for letter_type in ("itemized_bill", "coding_review", "financial_assistance"):
        payload = {"letter_type": letter_type, "patient": {}, "flags": [], "line_items": []}
        assert invoke("POST", "/letter", payload)[0] == 200

    document = base64.b64encode(b"%PDF-1.4 offline smoke").decode("ascii")
    payload = {"content_type": "application/pdf", "document_base64": document}
    assert invoke("POST", "/extract", payload)[0] == 200

    print("OFFLINE LAMBDA SMOKE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
