"""AWS Lambda Function URL adapter for the unified FairBill MA application.

The Anthropic key is fetched from Secrets Manager during cold start, used to
construct clients, and then removed from the process environment. Request and
response bodies are never logged.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
from urllib.parse import parse_qs

from app_server.app import AppContext, route
from backend.analyze.store import ReferenceStore
from backend.compare.store import Store as CompareStore
from backend.extract.llm_client import FakeLLMClient, make_client

API_PATHS = {"/health", "/procedures", "/compare", "/extract", "/analyze", "/letter"}
STATIC_DIR = Path(os.environ.get("STATIC_DIR", "/var/task/static")).resolve()
DATA_DIR = os.environ.get("DATA_DIR", "/var/task/data/processed")


def _offline() -> bool:
    return os.environ.get("OFFLINE_MODE", "true").lower() == "true"


def _load_secret() -> str:
    import boto3

    arn = os.environ.get("ANTHROPIC_SECRET_ARN", "")
    if not arn:
        raise RuntimeError("Anthropic secret ARN is not configured")
    value = boto3.client("secretsmanager").get_secret_value(SecretId=arn)
    payload = json.loads(value["SecretString"])
    key = payload.get("api_key")
    if not isinstance(key, str) or not key:
        raise RuntimeError("Anthropic secret is missing api_key")
    return key


def _build_runtime() -> tuple[AppContext, dict[str, object]]:
    compare_store = CompareStore.load(DATA_DIR)
    analyze_store = ReferenceStore.load(DATA_DIR)
    fallback = FakeLLMClient(default="")
    if _offline():
        return AppContext(compare_store, analyze_store, fallback, False), {
            "extract": fallback,
            "analyze": fallback,
            "letter": fallback,
        }

    key = _load_secret()
    os.environ["ANTHROPIC_API_KEY"] = key
    try:
        clients = {
            "extract": make_client("EXTRACT_MODEL_ID"),
            "analyze": make_client("EXPLAIN_MODEL_ID"),
            "letter": make_client("LETTER_MODEL_ID"),
        }
    finally:
        os.environ.pop("ANTHROPIC_API_KEY", None)
    return AppContext(compare_store, analyze_store, clients["extract"], True), clients


_CONTEXT, _CLIENTS = _build_runtime()


def _response(status: int, body: bytes, content_type: str, *, api: bool) -> dict:
    headers = {
        "content-type": content_type,
        "x-content-type-options": "nosniff",
        "cache-control": "no-store" if api else "public, max-age=300",
    }
    return {
        "statusCode": status,
        "headers": headers,
        "body": base64.b64encode(body).decode("ascii"),
        "isBase64Encoded": True,
    }


def _json_response(status: int, payload: dict) -> dict:
    return _response(
        status,
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        "application/json; charset=utf-8",
        api=True,
    )


def _static(path: str) -> dict:
    relative = path.lstrip("/") or "index.html"
    candidate = (STATIC_DIR / relative).resolve()
    try:
        candidate.relative_to(STATIC_DIR)
    except ValueError:
        return _json_response(404, {"error": "not found"})

    if not candidate.is_file():
        candidate = STATIC_DIR / "index.html"
    if not candidate.is_file():
        return _json_response(404, {"error": "frontend not built"})
    content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
    return _response(200, candidate.read_bytes(), content_type, api=False)


def handler(event: dict, context: object) -> dict:
    """Translate a Lambda Function URL payload into the pure app router."""
    request = event.get("requestContext", {}).get("http", {})
    method = str(request.get("method", "GET")).upper()
    path = str(event.get("rawPath") or "/")

    if method == "OPTIONS":
        return _response(204, b"", "text/plain", api=path in API_PATHS)
    if method == "GET" and path not in API_PATHS:
        return _static(path)

    body = None
    raw_body = event.get("body")
    if raw_body:
        try:
            raw = base64.b64decode(raw_body) if event.get("isBase64Encoded") else raw_body.encode("utf-8")
            body = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return _json_response(400, {"error": "request body must be valid JSON"})

    route_client = "analyze" if path == "/analyze" else path.lstrip("/")
    if route_client in _CLIENTS:
        _CONTEXT.client = _CLIENTS[route_client]

    try:
        status, payload = route(
            _CONTEXT,
            method,
            path,
            parse_qs(event.get("rawQueryString", "")),
            body,
        )
        return _json_response(status, payload)
    except Exception:
        # Generic metadata only: no exception detail, body, query, or bill content.
        print("ERROR request_failed")
        return _json_response(500, {"error": "request failed"})
