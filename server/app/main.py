"""FastAPI app factory for the Massachusetts Medical-Bill Helper.

Serves:
  - the API under /api/*  (JSON; never falls back to the SPA)
  - the built frontend from frontend/dist at /  (with SPA fallback)

Middleware/handlers:
  - CORS (same-origin by default; exact origins only when configured)
  - request body-size cap (protects synchronous handlers from huge uploads)
  - error-only, no-body logging
  - validation (422) and HTTP errors normalized to the shared `ApiError` shape
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.logging_setup import configure_logging, log_error
from app.routers import analyze, compare, extract, health, letter, procedures

# Repo layout:  <repo>/server/app/main.py  ->  frontend/dist is <repo>/frontend/dist
REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"

# Cap request bodies. Uploads are expected to be small (text / shrunk images);
# a few MB is plenty and protects the synchronous handlers from abuse.
MAX_BODY_BYTES = 6 * 1024 * 1024  # 6 MB


def _api_error(status_code: int, error: str, code: str | None = None) -> JSONResponse:
    content: dict[str, str] = {"error": error}
    if code is not None:
        content["code"] = code
    return JSONResponse(status_code=status_code, content=content)


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    app = FastAPI(title="Medical-Bill Helper", version="0.1.0")

    # CORS: same-origin by default (empty allow list). Only add the middleware
    # with real origins when configured; never use "*".
    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.allowed_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["content-type"],
        )

    # --- Request body-size cap ---
    @app.middleware("http")
    async def _limit_body(request: Request, call_next):  # noqa: ANN001
        cl = request.headers.get("content-length")
        if cl is not None:
            try:
                if int(cl) > MAX_BODY_BYTES:
                    return _api_error(413, "payload_too_large", "payload_too_large")
            except ValueError:
                return _api_error(400, "bad_content_length", "bad_request")
        return await call_next(request)

    # --- Error normalization to the shared ApiError shape ---
    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):  # noqa: ANN001
        log_error(request.url.path, 422, message="validation_error")
        return _api_error(422, "validation_error", "invalid_request")

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):  # noqa: ANN001
        if exc.status_code == 404:
            # Navigational 404s fall back to the SPA; /api/* stays a JSON 404.
            if not request.url.path.startswith("/api"):
                index = FRONTEND_DIST / "index.html"
                if index.is_file():
                    return FileResponse(index)
            return _api_error(404, "not_found", "not_found")
        if exc.status_code >= 500:
            log_error(request.url.path, exc.status_code, message="http_error")
        detail = exc.detail if isinstance(exc.detail, str) else "error"
        return _api_error(exc.status_code, detail, detail)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):  # noqa: ANN001
        # Never leak stack/body to the client; log only error-level metadata.
        log_error(request.url.path, 500, message=type(exc).__name__)
        return _api_error(500, "internal_error", "internal_error")

    # --- API router under /api ---
    api = APIRouter(prefix="/api")
    api.include_router(health.router)
    api.include_router(extract.router)
    api.include_router(analyze.router)
    api.include_router(procedures.router)
    api.include_router(compare.router)
    api.include_router(letter.router)
    app.include_router(api)

    # --- Static frontend at / (mounted last so /api wins) ---
    if FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    s = get_settings()
    uvicorn.run("app.main:app", host=s.host, port=s.port, reload=True)
