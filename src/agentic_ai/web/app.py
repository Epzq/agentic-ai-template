from __future__ import annotations

import logging
import os
import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

from ..config import Settings
from ..documents import _TEXT_SUFFIXES
from ..stream import AnalysisEvent, stream_analysis

# ---------------------------------------------------------------------------
# The web layer is a thin shell over the same analyst the CLI uses. It owns no
# agent logic: routes read Settings, call into the package, and return JSON.
# fastapi lives in the optional ".[web]" extra, so nothing here is imported by
# `agentic_ai/__init__.py` - only `create_app()` and the CLI's `serve` reach it.
# ---------------------------------------------------------------------------

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
INDEX_HTML = STATIC_DIR / "index.html"

# Exactly what `documents.load_document` can parse - kept in step with it rather
# than retyped, so the browser is never allowed to upload something unreadable.
SUPPORTED_SUFFIXES = frozenset(_TEXT_SUFFIXES | {".pdf", ".docx"})

# A call sheet is a few hundred KB; this is a generous ceiling that still stops a
# stray multi-GB upload from filling the workdir.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_CHUNK = 64 * 1024


def get_model() -> BaseChatModel | None:
    """The orchestrator model for a run. ``None`` lets ``stream_analysis`` build the
    one ``Settings`` describes; tests override this dependency with a scripted model."""
    return None


def _sse(event: AnalysisEvent) -> str:
    """One server-sent event. The browser parses the JSON payload directly."""
    return f"data: {event.model_dump_json()}\n\n"


# The end-of-stream marker. It is deliberately not an AnalysisEvent: `done` is the
# transport's business, not the analyst's, so stream.py's five event types stay
# exactly as WI-1 defined them.
DONE_EVENT = 'data: {"type": "done"}\n\n'


class UploadResponse(BaseModel):
    """What the browser gets back: a handle, never a filesystem path."""

    run_id: str
    filename: str


def _has_gemini_key() -> bool:
    """Whether the research tools can run at all - the same pair of variables
    ``ask_gemini`` checks. Without one, every web tool returns 'gemini error:'."""
    return bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"))


def _safe_upload_path(run_dir: Path, filename: str) -> Path:
    """Resolve an uploaded file's name inside ``run_dir``, refusing anything that
    escapes it - the same guard shape as ``_safe_path()`` in tools.py.

    The name is reduced to its last component first, so '../../x.md' becomes
    'x.md'. Backslashes are folded to '/' so a Windows-style path can't smuggle a
    directory through on posix.
    """
    name = PurePosixPath(filename.replace("\\", "/")).name
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=400, detail=f"unusable filename: {filename!r}")
    target = (run_dir / name).resolve()
    if target.parent != run_dir.resolve():
        raise HTTPException(status_code=400, detail=f"filename escapes the run folder: {name!r}")
    return target


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app. ``settings`` is injectable, as everywhere else."""
    settings = settings or Settings()
    app = FastAPI(title="agentic-ai grant-fit analyst")

    uploads_dir = Path(settings.workdir).resolve() / "uploads"
    # run_id -> the document on disk. In-process on purpose: the browser holds the
    # id, never the path, so there is nothing for it to tamper with.
    runs: dict[str, Path] = {}
    app.state.runs = runs

    @app.get("/api/health")
    def health() -> dict:
        """Liveness plus the two facts the page needs before it can be useful."""
        return {"ok": True, "model": settings.model, "gemini_key": _has_gemini_key()}

    @app.post("/api/upload", response_model=UploadResponse)
    async def upload(file: UploadFile) -> UploadResponse:
        """Store one context document and return the run_id that stands for it."""
        suffix = PurePosixPath((file.filename or "").replace("\\", "/")).suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"unsupported document type: {suffix or '(no extension)'}. "
                    f"Accepted: {', '.join(sorted(SUPPORTED_SUFFIXES))}"
                ),
            )

        run_id = str(uuid.uuid4())
        run_dir = uploads_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        target = _safe_upload_path(run_dir, file.filename or "")

        size = 0
        try:
            with target.open("wb") as out:
                while chunk := await file.read(_CHUNK):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail=f"file is larger than {MAX_UPLOAD_BYTES // 1024 // 1024} MB",
                        )
                    out.write(chunk)
        except Exception:
            shutil.rmtree(run_dir, ignore_errors=True)  # no partial upload left behind
            raise

        runs[run_id] = target
        return UploadResponse(run_id=run_id, filename=target.name)

    @app.get("/api/analyse")
    def analyse(
        run_id: str,
        pi_url: str,
        call: str | None = None,
        model: Annotated[BaseChatModel | None, Depends(get_model)] = None,
    ) -> StreamingResponse:
        """Stream one analysis of a previously uploaded document as SSE."""
        document = runs.get(run_id)
        if document is None:
            raise HTTPException(status_code=404, detail=f"unknown run_id: {run_id!r}")

        def events() -> Iterator[str]:
            # A plain sync generator: StreamingResponse wraps it with
            # iterate_in_threadpool, so the blocking agent run never touches the
            # event loop. The stream always terminates with a `done` event, even
            # after a failure, so the browser can always re-enable its button.
            try:
                for event in stream_analysis(
                    str(document), pi_url, call, settings=settings, model=model
                ):
                    yield _sse(event)
            except GeneratorExit:
                # Best-effort note when this generator is closed explicitly. The run
                # stops either way: once the browser is gone nothing pulls from here,
                # so the agent loop is left suspended at its yield and goes no
                # further - measured, not assumed. A tool call already in flight does
                # finish first, and this handler may not run promptly, so don't rely
                # on it for cleanup that has to happen.
                log.info("client disconnected; abandoning run %s", run_id)
                raise
            except Exception as exc:  # noqa: BLE001 - the browser sees it, not a 500
                yield _sse(AnalysisEvent(type="error", text=f"stream failed: {exc}"))
            yield DONE_EVENT

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(INDEX_HTML, media_type="text/html")

    return app
