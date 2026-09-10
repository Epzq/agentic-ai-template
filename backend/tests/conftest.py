"""Shared test harness.

`live_server` exists because **Starlette's `TestClient` cannot test streaming**: it writes
the whole response into a `BytesIO` and only returns once the app is done
(`starlette/testclient.py:296,343`), so `client.stream()` on an SSE route blocks until the
run ends. Anything about incremental delivery needs a real socket.
"""

from __future__ import annotations

import socket
import threading
import time

import pytest
import uvicorn

from roia.api import RunRecord, create_app
from roia.config import Settings
from roia.events import Event, Run
from roia.pipeline import RunInputs

INPUTS = RunInputs(
    grant_src="https://example.test/call", profile_url="https://example.test/me"
)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def app(tmp_path):
    return create_app(Settings(_env_file=None, dev=True), runs_dir=tmp_path / "runs")


@pytest.fixture
def live_server(app):
    """A real uvicorn server in a thread. Yields `(base_url, run)` for a run to drive."""
    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "uvicorn did not start"
        time.sleep(0.02)

    run = Run("run-live")
    app.state.roia.runs["run-live"] = RunRecord(run=run, inputs=INPUTS)
    try:
        yield f"http://127.0.0.1:{port}", run
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def read_until(lines, seen: list[Event], stop) -> None:
    """Consume SSE lines into `seen` until `stop(seen)`. Keep-alive comments start with
    `:` and are skipped, which is exactly what a browser does with them."""
    for line in lines:
        if line.startswith("data:"):
            seen.append(Event.model_validate_json(line.removeprefix("data:").strip()))
            if stop(seen):
                return
