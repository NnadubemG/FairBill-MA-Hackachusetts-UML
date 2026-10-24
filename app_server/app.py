"""Pure routing core: build the app context once, dispatch a request to a handler.

Kept free of http.server so it is unit-testable. `route()` takes already-parsed inputs
(method, path, query dict, parsed JSON body) and returns (status_code, response_dict).
Every handler reused here is the team's real one; this module only adapts types to JSON
and never logs request bodies.
"""

from __future__ import annotations

import base64
import binascii
import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from pipeline import config as pipeline_config

from backend.analyze.handler import AnalyzeError, analyze_bill
from backend.analyze.store import ReferenceStore
from backend.compare.service import compare as compare_service
from backend.compare.service import list_procedures as list_procedures_service
from backend.compare.store import Store as CompareStore

from .clients import get_client

# Routes the server understands (for /health and 404 messages).
ROUTES = ["/health", "/procedures", "/compare", "/extract", "/analyze", "/letter"]


@dataclass
class AppContext:
    """Built once at startup: reference data + model client, shared across requests."""

    compare_store: CompareStore
    analyze_store: ReferenceStore
    client: Any
    model_is_real: bool

    @classmethod
    def build(cls, processed_dir: Optional[str] = None) -> "AppContext":
        processed_dir = processed_dir or str(pipeline_config.PROCESSED_DIR)
        client, is_real = get_client()
        return cls(
            compare_store=CompareStore.load(processed_dir),
            analyze_store=ReferenceStore.load(processed_dir),
            client=client,
            model_is_real=is_real,
        )


def _asdict(obj) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _asdict(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, (list, tuple)):
        return [_asdict(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _asdict(v) for k, v in obj.items()}
    return obj


def _explain_callable(ctx: AppContext):
    """Adapt the explain handler into the (flags -> flags) callable analyze expects.

    Best-effort: analyze already treats explain as optional and swallows failures, so
    we simply return the explained flags or let analyze fall back.
    """
    from backend.explain.handler import explain as explain_handler

    def _explain(flags):
        return explain_handler(flags, client=ctx.client).flags

    return _explain


def route(
    ctx: AppContext,
    method: str,
    path: str,
    query: dict,
    body: Optional[dict],
) -> tuple[int, dict]:
    """Dispatch one request. Returns (status, response_dict). Never raises for client
    errors; returns a body-free error message instead."""
    if path == "/health":
        return 200, {"status": "ok", "model": "live" if ctx.model_is_real else "offline-fallback"}

    if path == "/procedures" and method == "GET":
        return 200, list_procedures_service(ctx.compare_store)

    if path == "/compare" and method == "GET":
        code = (query.get("code") or [""])[0] if isinstance(query.get("code"), list) else query.get("code")
        if not code or not str(code).strip():
            return 400, {"error": "missing required query parameter: code"}
        return 200, compare_service(ctx.compare_store, str(code))

    if path == "/analyze" and method == "POST":
        if not isinstance(body, dict):
            return 400, {"error": "request body must be a JSON object"}
        try:
            result = analyze_bill(
                body.get("line_items"),
                ctx.analyze_store,
                explain=_explain_callable(ctx),
            )
            return 200, _asdict(result)
        except AnalyzeError as exc:
            return 400, {"error": str(exc)}

    if path == "/extract" and method == "POST":
        return _handle_extract(ctx, body)

    if path == "/letter" and method == "POST":
        return _handle_letter(ctx, body)

    return 404, {"error": "not found", "routes": ROUTES}


def _handle_extract(ctx: AppContext, body: Optional[dict]) -> tuple[int, dict]:
    from backend.extract.handler import extract

    if not isinstance(body, dict):
        return 400, {"error": "request body must be a JSON object"}
    content_type = body.get("content_type")
    b64 = body.get("document_base64")
    if not isinstance(content_type, str) or not isinstance(b64, str):
        return 400, {"error": "expected content_type and document_base64"}
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        return 400, {"error": "document_base64 is not valid base64"}
    result = extract(raw, content_type, client=ctx.client)
    return 200, _asdict(result)


def _handle_letter(ctx: AppContext, body: Optional[dict]) -> tuple[int, dict]:
    from backend.letter.handler import generate_letter
    from backend.letter.models import InvalidLetterType, LetterRequest, PatientFields
    from backend.letter._contracts import Flag, LineItem

    if not isinstance(body, dict):
        return 400, {"error": "request body must be a JSON object"}

    letter_type = body.get("letter_type")
    if not isinstance(letter_type, str):
        return 400, {"error": "expected letter_type"}

    patient_in = body.get("patient") or {}
    patient = PatientFields(
        name=str(patient_in.get("name", "")),
        account_number=str(patient_in.get("account_number", "")),
        hospital=str(patient_in.get("hospital", "")),
        date=str(patient_in.get("date", "")),
        notes=str(patient_in.get("notes", "")),
    ) if isinstance(patient_in, dict) else PatientFields()

    try:
        flags = [_to_flag(f) for f in (body.get("flags") or [])]
        line_items = [_to_line_item(li) for li in (body.get("line_items") or [])]
    except (TypeError, KeyError):
        return 400, {"error": "malformed flags or line_items"}

    request = LetterRequest(
        letter_type=letter_type, patient=patient, flags=flags, line_items=line_items
    )
    try:
        result = generate_letter(request, client=ctx.client)
    except InvalidLetterType:
        return 400, {"error": "unknown letter type"}
    return 200, _asdict(result)


def _to_flag(d: dict):
    from backend.letter._contracts import Flag

    return Flag(
        line_item_id=d["line_item_id"],
        flag_type=d["flag_type"],
        severity=d["severity"],
        reason=d["reason"],
        basis=d["basis"],
        data_source=d.get("data_source"),
        data_year=d.get("data_year"),
        explanation=d.get("explanation"),
    )


def _to_line_item(d: dict):
    from backend.letter._contracts import LineItem

    return LineItem(
        id=d["id"],
        description=d["description"],
        billed_amount=d["billed_amount"],
        code=d.get("code"),
        code_system=d.get("code_system"),
        raw_description=d.get("raw_description"),
        quantity=d.get("quantity"),
        unit=d.get("unit"),
        date_of_service=d.get("date_of_service"),
    )
