"""Post-deploy metadata/API smoke checks. Uses stdlib only; logs no bill content."""

from __future__ import annotations

import argparse
import base64
import json
import urllib.error
import urllib.request


def request(base: str, path: str, body: dict | None = None) -> tuple[int, dict, dict]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        base.rstrip("/") + path,
        data=data,
        method="POST" if data is not None else "GET",
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            raw = response.read()
            content_type = response.headers.get("content-type", "")
            parsed = json.loads(raw) if "json" in content_type else {}
            return response.status, dict(response.headers), parsed
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), json.loads(exc.read() or b"{}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--expect-live", action="store_true")
    parser.add_argument("--large-upload", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    health_status, health_headers, health = request(args.url, "/health")
    expected_model = "live" if args.expect_live else "offline-fallback"
    if health_status != 200 or health.get("model") != expected_model:
        failures.append(f"health: expected 200/{expected_model}, got {health_status}/{health.get('model')}")
    if "no-store" not in health_headers.get("Cache-Control", ""):
        failures.append("health: missing no-store")

    static_status, static_headers, _ = request(args.url, "/")
    if static_status != 200:
        failures.append(f"static root: {static_status}")
    if "max-age" not in static_headers.get("Cache-Control", ""):
        failures.append("static root: missing cache max-age")
    if not static_headers.get("Content-Security-Policy"):
        failures.append("static root: missing CSP")

    for path in ("/procedures", "/compare?code=99213"):
        status, headers, _ = request(args.url, path)
        if status != 200:
            failures.append(f"{path}: {status}")
        if "no-store" not in headers.get("Cache-Control", ""):
            failures.append(f"{path}: missing no-store")

    for letter_type in ("itemized_bill", "coding_review", "financial_assistance"):
        status, _, _ = request(
            args.url,
            "/letter",
            {"letter_type": letter_type, "patient": {}, "flags": [], "line_items": []},
        )
        if status != 200:
            failures.append(f"letter {letter_type}: {status}")

    if args.large_upload:
        document = base64.b64encode(bytes(4 * 1024 * 1024)).decode("ascii")
        status, _, _ = request(
            args.url,
            "/extract",
            {"content_type": "application/pdf", "document_base64": document},
        )
        if status != 200:
            failures.append(f"4 MB upload: {status}")

    if failures:
        print("SMOKE FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("SMOKE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
