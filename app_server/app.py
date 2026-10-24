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
from pipeline import jsonio

from backend.analyze.handler import AnalyzeError, analyze_bill
from backend.analyze.store import ReferenceStore
from backend.compare.service import compare as compare_service
from backend.compare.service import list_procedures as list_procedures_service
from backend.compare.store import Store as CompareStore

from .clients import get_client

# Routes the server understands (for /health and 404 messages).
ROUTES = ["/health", "/procedures", "/compare", "/samples", "/extract", "/analyze", "/letter"]

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = REPO_ROOT / "frontend"
SAMPLES_DIR = REPO_ROOT / "synthetic" / "samples"

# Sample scenarios offered in the UI picker. The prompt-injection sample is a test
# fixture, not a demo, so it is left out.
_SAMPLE_LABELS = {
    "mixed": "Sample: ER visit with several questions",
    "high_price": "Sample: a charge well above reference",
    "duplicate": "Sample: the same test billed twice",
    "quantity": "Sample: an unusual quantity",
    "unbundling": "Sample: related services billed separately",
    "unknown_code": "Sample: a code with no reference price",
    "clean": "Sample: a bill with nothing unusual",
}

# Headers sent on every response. The CSP allows only same-origin scripts; inline style
# attributes are used for small color swatches, hence 'unsafe-inline' for styles only.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    ),
}

_STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}
# Only these subtrees of /frontend are public. Tests and READMEs are not served.
_STATIC_PREFIXES = ("app/", "src/compare/")


def load_samples(samples_dir: Path = SAMPLES_DIR) -> list[dict]:
    """Read the synthetic sample bills into a small, UI-ready list.

    Only line items and bill metadata go out; the samples' synthetic reference data and
    expected flags stay server-side (analysis always uses the real reference store).
    """
    out: list[dict] = []
    if not samples_dir.exists():
        return out
    for path in sorted(samples_dir.glob("bill-*.json")):
        try:
            bill = jsonio.read_json(path)
        except (OSError, ValueError):
            continue
        scenario = bill.get("scenario")
        if scenario not in _SAMPLE_LABELS:
            continue
        meta = bill.get("bill_metadata") or {}
        out.append(
            {
                "id": str(bill.get("bill_id") or path.stem),
                "label": _SAMPLE_LABELS[scenario],
                "scenario": scenario,
                "metadata": {
                    "hospital_name": meta.get("hospital_name"),
                    "statement_date": meta.get("statement_date"),
                    "total": meta.get("total_billed"),
                },
                "line_items": bill.get("line_items") or [],
            }
        )
    order = list(_SAMPLE_LABELS)
    out.sort(key=lambda s: order.index(s["scenario"]))
    return _load_demo_bills() + out


DEMO_DIR = REPO_ROOT / "data" / "demo"


def _load_demo_bills(demo_dir: Path = DEMO_DIR) -> list[dict]:
    """Fictional test bills priced against the real processed data (data/demo/*.json).

    Listed first in the picker. Only label, metadata and line items are sent.
    """
    out: list[dict] = []
    if not demo_dir.exists():
        return out
    for path in sorted(demo_dir.glob("*.json")):
        try:
            bill = jsonio.read_json(path)
        except (OSError, ValueError):
            continue
        if not isinstance(bill, dict) or not bill.get("line_items"):
            continue
        out.append(
            {
                "id": str(bill.get("id") or path.stem),
                "label": str(bill.get("label") or path.stem),
                "scenario": str(bill.get("scenario") or "demo"),
                "metadata": bill.get("metadata") or {},
                "line_items": bill["line_items"],
            }
        )
    return out


def static_file(path: str, frontend_dir: Path = FRONTEND_DIR) -> Optional[tuple[str, bytes]]:
    """Resolve a GET path to a public frontend file. Returns (content_type, bytes) or None.

    "/" serves the app shell. Anything else must sit under an allowed prefix, have an
    allowed extension, and resolve inside /frontend (no path traversal).
    """
    rel = path.lstrip("/")
    parts = rel.replace("\\", "/").split("/")
    if any(p in ("..", ".") or p.startswith(".") for p in parts if p):
        return None  # no traversal segments or dotfiles, ever
    if rel in ("", "index.html"):
        rel = "index.html"
    elif not rel.startswith(_STATIC_PREFIXES) or "tests" in parts:
        return None
    suffix = Path(rel).suffix.lower()
    if suffix not in _STATIC_TYPES:
        return None
    root = frontend_dir.resolve()
    target = (root / rel).resolve()
    # Defense in depth: the resolved file must sit at the shell or inside a public subtree.
    allowed_roots = [(root / p.rstrip("/")).resolve() for p in _STATIC_PREFIXES]
    inside = target == (root / "index.html").resolve() or any(
        _is_within(target, base) for base in allowed_roots
    )
    if not inside or not target.is_file():
        return None
    return _STATIC_TYPES[suffix], target.read_bytes()


def _is_within(target: Path, base: Path) -> bool:
    try:
        target.relative_to(base)
        return True
    except ValueError:
        return False


@dataclass
class AppContext:
    """Built once at startup: reference data + model client, shared across requests."""

    compare_store: CompareStore
    analyze_store: ReferenceStore
    client: Any
    model_is_real: bool
    samples: list = dataclasses.field(default_factory=list)

    @classmethod
    def build(cls, processed_dir: Optional[str] = None) -> "AppContext":
        processed_dir = processed_dir or str(pipeline_config.PROCESSED_DIR)
        client, is_real = get_client()
        return cls(
            compare_store=CompareStore.load(processed_dir),
            analyze_store=ReferenceStore.load(processed_dir),
            client=client,
            model_is_real=is_real,
            samples=load_samples(),
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

    if path == "/samples" and method == "GET":
        return 200, {
            "samples": ctx.samples,
            "note": "Sample bills are fictional and for demos only.",
        }

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
    if not ctx.model_is_real:
        # No model configured: skip the call and return the handler's own single,
        # clear "enter lines by hand" result instead of two retry warnings.
        from backend.extract.handler import WARN_EXTRACTION_UNAVAILABLE
        from backend.extract.models import ExtractionResult

        return 200, _asdict(ExtractionResult(warnings=[WARN_EXTRACTION_UNAVAILABLE]))
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
