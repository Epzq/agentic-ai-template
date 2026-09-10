"""Harness for the browser tests.

These drive the **built** app served by FastAPI at the same origin — the production
topology — rather than the Vite dev server, so the SPA fallback and the API are exercised
exactly as they will be on the day.

They are opted into (`pytest tests/e2e -m e2e`) because they need chromium and a build.
Neither is a thing to discover from a cryptic failure, so both are checked up front.
"""

from __future__ import annotations

import threading
import time

import pytest
import uvicorn

from roia.api import create_app
from roia.config import Settings
from roia.paths import FRONTEND_DIST
from tests.conftest import free_port

BUILD_HINT = (
    "Build it first:  cd frontend && nvm use && npm run build\n"
    "(Node 20.19+ or 22.12+ — this machine's default node is v18 and Vite refuses it.)"
)


@pytest.fixture(scope="session")
def built_frontend():
    index = FRONTEND_DIST / "index.html"
    if not index.is_file():
        pytest.fail(f"{index} is missing — the browser tests drive the built app.\n{BUILD_HINT}")

    # A stale bundle is worse than a missing one: the suite goes green against the previous
    # build and the change under test was never in the browser at all.
    source = FRONTEND_DIST.parent / "src"
    newest = max((f.stat().st_mtime for f in source.rglob("*") if f.is_file()), default=0.0)
    if newest > index.stat().st_mtime:
        pytest.fail(
            "frontend/dist is older than frontend/src — these tests would pass on stale "
            f"code.\n{BUILD_HINT}"
        )
    return FRONTEND_DIST


@pytest.fixture
def ui(built_frontend, tmp_path) -> str:
    """A real server on a real port, serving the built SPA and the API together."""
    app = create_app(Settings(_env_file=None, dev=False), runs_dir=tmp_path / "runs")
    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 15
    while not server.started:
        assert time.monotonic() < deadline, "uvicorn did not start"
        time.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
