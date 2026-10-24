"""FastAPI app factory for the Massachusetts Medical-Bill Helper.

Serves:
  - the API under /api/*  (JSON; never falls back to the SPA)
  - the built frontend from frontend/dist at /  (with SPA fallback)

For the stub, frontend/dist contains a placeholder index.html and /api exposes
only GET /api/health.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import health

# Repo layout:  <repo>/server/app/main.py  ->  frontend/dist is <repo>/frontend/dist
REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


def create_app() -> FastAPI:
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

    # --- API router under /api ---
    api = APIRouter(prefix="/api")
    api.include_router(health.router)
    app.include_router(api)

    # Guard: any unmatched /api/* path returns a JSON 404, never the SPA.
    @app.exception_handler(404)
    async def _not_found(request, exc):  # noqa: ANN001
        if request.url.path.startswith("/api"):
            return JSONResponse(status_code=404, content={"error": "not_found"})
        # Non-API navigational route -> SPA fallback if the frontend exists.
        index = FRONTEND_DIST / "index.html"
        if index.is_file():
            return FileResponse(index)
        return JSONResponse(status_code=404, content={"error": "not_found"})

    # --- Static frontend at / (mounted last so /api wins) ---
    if FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    s = get_settings()
    uvicorn.run("app.main:app", host=s.host, port=s.port, reload=True)
