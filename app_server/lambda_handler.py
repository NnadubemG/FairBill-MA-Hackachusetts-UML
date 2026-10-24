"""AWS Lambda entry point (Function URL / API Gateway HTTP API, payload v2).

    Handler: app_server.lambda_handler.handler

Serves the same web app and JSON API as the local server, through the same pure core
(app.route / app.static_file). The context (reference data + model client) is built
once per cold start. Never logs request bodies or uploaded content: nothing here
prints, and errors return a generic message.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any, Optional
from urllib.parse import parse_qs

from .app import ROUTES, SECURITY_HEADERS, AppContext, route, static_file

MAX_BODY_BYTES = 8 * 1024 * 1024
_CTX: Optional[AppContext] = None


def _load_api_key_from_secret() -> None:
    """If ANTHROPIC_SECRET_ARN is set, read the key from Secrets Manager into the env.

    The secret may be a plain string or JSON with an "api_key" field. Failure is silent
    (the app then runs in offline mode); the value is never logged.
    """
    arn = os.environ.get("ANTHROPIC_SECRET_ARN", "").strip()
    if not arn or os.environ.get("ANTHROPIC_API_KEY"):
        return
    try:
        import boto3  # bundled in the Lambda Python runtime

        raw = boto3.client("secretsmanager").get_secret_value(SecretId=arn).get("SecretString") or ""
        try:
            parsed = json.loads(raw)
            key = parsed.get("api_key", "") if isinstance(parsed, dict) else ""
        except json.JSONDecodeError:
            key = raw
        if key.strip():
            os.environ["ANTHROPIC_API_KEY"] = key.strip()
    except Exception:  # noqa: BLE001 - never surface secret-handling details
        return


def _ctx() -> AppContext:
    global _CTX
    if _CTX is None:
        _load_api_key_from_secret()
        _CTX = AppContext.build()
    return _CTX


def _response(status: int, body: bytes | str, content_type: str, cache: str = "no-store") -> dict:
    headers = {"Content-Type": content_type, "Cache-Control": cache, **SECURITY_HEADERS}
    if isinstance(body, bytes):
        if content_type.startswith(("text/", "application/json", "image/svg")):
            return {"statusCode": status, "headers": headers, "body": body.decode("utf-8"),
                    "isBase64Encoded": False}
        return {"statusCode": status, "headers": headers,
                "body": base64.b64encode(body).decode("ascii"), "isBase64Encoded": True}
    return {"statusCode": status, "headers": headers, "body": body, "isBase64Encoded": False}


def _json(status: int, payload: dict) -> dict:
    return _response(status, json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")


def handler(event: dict, context: Any = None) -> dict:
    http = (event.get("requestContext") or {}).get("http") or {}
    method = (http.get("method") or event.get("httpMethod") or "GET").upper()
    path = event.get("rawPath") or event.get("path") or "/"
    query = parse_qs(event.get("rawQueryString") or "")

    if method == "OPTIONS":
        return _response(204, "", "text/plain")

    if method == "GET" and path not in ROUTES:
        found = static_file(path)
        if found is not None:
            content_type, body = found
            return _response(200, body, content_type, cache="public, max-age=300")

    body: Any = None
    if method == "POST":
        raw = event.get("body") or ""
        try:
            data = base64.b64decode(raw) if event.get("isBase64Encoded") else raw.encode("utf-8")
        except (ValueError, TypeError):
            return _json(400, {"error": "request body could not be read"})
        if len(data) > MAX_BODY_BYTES:
            return _json(413, {"error": "request body too large (max 8 MB)"})
        if data:
            try:
                body = json.loads(data.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return _json(400, {"error": "request body must be valid JSON"})

    try:
        status, payload = route(_ctx(), method, path, query, body)
    except Exception:  # noqa: BLE001 - never leak details or bill content
        return _json(500, {"error": "internal error"})
    return _json(status, payload)
