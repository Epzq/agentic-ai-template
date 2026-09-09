from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from ..config import Settings

# ---------------------------------------------------------------------------
# The web layer is a thin shell over the same analyst the CLI uses. It owns no
# agent logic: routes read Settings, call into the package, and return JSON.
# fastapi lives in the optional ".[web]" extra, so nothing here is imported by
# `agentic_ai/__init__.py` - only `create_app()` and the CLI's `serve` reach it.
# ---------------------------------------------------------------------------

STATIC_DIR = Path(__file__).parent / "static"
INDEX_HTML = STATIC_DIR / "index.html"


def _has_gemini_key() -> bool:
    """Whether the research tools can run at all - the same pair of variables
    ``ask_gemini`` checks. Without one, every web tool returns 'gemini error:'."""
    return bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"))


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app. ``settings`` is injectable, as everywhere else."""
    settings = settings or Settings()
    app = FastAPI(title="agentic-ai grant-fit analyst")

    @app.get("/api/health")
    def health() -> dict:
        """Liveness plus the two facts the page needs before it can be useful."""
        return {"ok": True, "model": settings.model, "gemini_key": _has_gemini_key()}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(INDEX_HTML, media_type="text/html")

    return app
