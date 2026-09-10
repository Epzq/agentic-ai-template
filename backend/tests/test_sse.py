"""WI-2.2 — `GET /api/runs/{id}/events` (`demo-spec.md` §6.2, §6.3).

Two layers, because they prove different things.

The **async tests** drive `_event_stream` directly. They can interleave an emit with a
subscribe at exactly the wrong moment, which is the only way to show that AC8a's
replay-and-subscribe really is one critical section rather than two that usually happen
close together.

The **`TestClient` tests** cover framing, headers and status codes — but note that
Starlette's test transport collects the entire body before it returns a response, so it
cannot observe streaming at all. Anything about *incremental* delivery, which is the whole
point of SSE, is tested against a **real uvicorn server on a real socket**. That is the
curl recipe in the work item, run by pytest.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import pathlib
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.middleware.gzip import GZipMiddleware

from roia.api import SSE_IDLE_TICK_SECONDS, RunRecord, _event_stream
from roia.events import Event, Run
from tests.conftest import INPUTS, read_until

F = pathlib.Path(__file__).resolve().parent.parent / "fixtures"

def record_for(run: Run) -> RunRecord:
    return RunRecord(run=run, inputs=INPUTS)


async def drain(stream, count: int, timeout: float = 5.0) -> list[Event]:
    """Pull `count` frames off the generator, failing loudly rather than hanging forever."""
    out: list[Event] = []
    for _ in range(count):
        frame = await asyncio.wait_for(anext(stream), timeout)
        assert frame["id"] == str(json.loads(frame["data"])["seq"]), "id: must carry the seq"
        out.append(Event.model_validate_json(frame["data"]))
    return out


# --- the generator ------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ac8a_a_stream_opened_late_replays_every_earlier_event() -> None:
    """`connecting after 5 events yields all 5, then live ones`."""
    run = Run("run-late")
    for i in range(5):
        run.stage_started(f"stage-{i}")

    stream = _event_stream(record_for(run))
    replayed = await drain(stream, 5)
    assert [event.stage for event in replayed] == [f"stage-{i}" for i in range(5)]
    assert [event.seq for event in replayed] == [0, 1, 2, 3, 4]

    run.warning("thin_literature", "only 3 papers")
    live = await drain(stream, 1)
    assert live[0].type == "warning"
    assert live[0].seq == 5

    run.finished()
    assert (await drain(stream, 1))[0].type == "run.finished"
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(stream), 5.0)


@pytest.mark.asyncio
async def test_replay_and_subscribe_are_one_critical_section() -> None:
    """The AC8a guarantee, stated exactly: an event emitted while a stream is attaching is
    delivered once — never dropped between the backlog and the subscription, never sent
    twice by landing in both.

    A background thread emits continuously; the stream attaches while it is mid-flight,
    so `subscribe` really does run concurrently with `emit` rather than after it. Split
    the critical section in two and events land in the gap between the snapshot and the
    fan-out — verified by making exactly that edit and watching this fail.
    """
    run = Run("run-race")
    stop = threading.Event()

    def emitter() -> None:
        while not stop.is_set() and len(run.events) < 2000:
            run.stage_started(f"s{len(run.events)}")
            time.sleep(0)  # hand the GIL over, or the event loop never gets to subscribe

    thread = threading.Thread(target=emitter)
    thread.start()
    while len(run.events) < 50:  # attach in the middle, not before it starts
        await asyncio.sleep(0.001)

    stream = _event_stream(record_for(run))
    seen = await drain(stream, 1)  # the first `anext` is what subscribes
    raced = thread.is_alive()
    stop.set()
    thread.join(timeout=10)
    run.finished()

    while seen[-1].type != "run.finished":
        seen.extend(await drain(stream, 1))

    # The stream joined somewhere in the middle; from there on it must be a gapless,
    # duplicate-free run of consecutive seqs ending at the last event emitted.
    assert raced, "the emitter finished before the stream attached — nothing was raced"
    assert [event.seq for event in seen] == list(range(len(run.events)))


@pytest.mark.asyncio
async def test_a_finished_run_replays_and_closes_without_waiting() -> None:
    """A rehydrated run has no task and will never emit again. The stream must end, not
    hold the browser open on a run that finished yesterday."""
    run = Run("run-old")
    run.started(grant="x")
    run.finished()

    stream = _event_stream(record_for(run))
    assert [event.type for event in await drain(stream, 2)] == ["run.started", "run.finished"]
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(stream), 5.0)


@pytest.mark.asyncio
async def test_a_run_that_dies_without_a_terminal_event_still_closes_the_stream() -> None:
    """`_execute` turns a crash into `run.failed`, so this only happens to a cancelled
    task — but a stream that waits forever on a dead run is a hung browser tab."""
    run = Run("run-killed")
    run.stage_started("ingest")

    async def forever() -> None:
        await asyncio.sleep(3600)

    record = RunRecord(run=run, inputs=INPUTS, task=asyncio.create_task(forever()))
    stream = _event_stream(record)
    assert (await drain(stream, 1))[0].type == "stage.started"

    record.task.cancel()
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(stream), SSE_IDLE_TICK_SECONDS * 5)


@pytest.mark.asyncio
async def test_a_closed_stream_stops_receiving_events() -> None:
    """Without the `finally`, every tab a demo audience ever opened would keep receiving
    events into a queue nobody reads, for the life of the run."""
    run = Run("run-leak")
    stream = _event_stream(record_for(run))
    run.stage_started("ingest")
    await drain(stream, 1)
    assert run.subscribers == 1

    await stream.aclose()
    assert run.subscribers == 0


@pytest.mark.asyncio
async def test_two_streams_on_one_run_both_receive_everything() -> None:
    """The Done line: two browser tabs on one run both stream."""
    run = Run("run-two-tabs")
    run.started(grant="x")

    first = _event_stream(record_for(run))
    second = _event_stream(record_for(run))
    assert (await drain(first, 1))[0].type == "run.started"
    assert (await drain(second, 1))[0].type == "run.started"
    assert run.subscribers == 2

    run.tool_started("search_literature", "graph neural networks")
    run.finished()

    for stream in (first, second):
        assert [event.type for event in await drain(stream, 2)] == [
            "tool.started", "run.finished",
        ]
        # Exhaust it the way `EventSourceResponse` does: the `finally` that unsubscribes
        # runs when the generator resumes past its last yield, not when a reader walks away.
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(anext(stream), 5.0)

    assert run.subscribers == 0, "both closed themselves on run.finished"


# --- over HTTP ------------------------------------------------------------------------------

@pytest.fixture
def seeded(app):
    """An app holding one run we drive by hand, so the stream is tested without a pipeline."""
    with TestClient(app) as client:
        run = Run("run-http")
        client.app.state.roia.runs["run-http"] = record_for(run)
        yield client, run


def frames(body: str) -> list[Event]:
    """Parse `text/event-stream` back into events, ignoring `:` keep-alive comments."""
    return [
        Event.model_validate_json(line.removeprefix("data:").strip())
        for line in body.splitlines()
        if line.startswith("data:")
    ]


def test_the_stream_replays_a_finished_run_over_http(seeded) -> None:
    client, run = seeded
    for event in read_fixture()[:20]:
        run.emit(event.type, event.model_dump(exclude={"seq", "ts", "type"}))
    run.finished()

    response = client.get("/api/runs/run-http/events")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert [event.seq for event in frames(response.text)] == list(range(21))


def test_the_stream_carries_the_no_buffering_headers(seeded) -> None:
    """A buffering proxy delivers the whole run in one lump at the end, which is exactly
    the failure `demo-spec.md` §10 warns about."""
    client, run = seeded
    run.finished()

    headers = client.get("/api/runs/run-http/events").headers

    assert "no-cache" in headers["cache-control"]
    assert headers["x-accel-buffering"] == "no"


def test_no_gzip_middleware_is_installed(app) -> None:
    """A tripwire. Compression buffers, so adding `GZipMiddleware` app-wide later would
    silently break the live timeline in a way no unit test would otherwise notice."""
    assert not any(m.cls is GZipMiddleware for m in app.user_middleware)


def test_streaming_an_unknown_run_is_a_404(seeded) -> None:
    client, _ = seeded

    assert client.get("/api/runs/run-nope/events").status_code == 404


def read_fixture() -> list[Event]:
    from roia.events import read_jsonl

    return read_jsonl(F / "run-001.jsonl")


# --- against a real socket ------------------------------------------------------------------
#
# Everything above this line goes through Starlette's test transport, which writes the
# whole response into a BytesIO and only hands it over once the app is done. It can never
# show an event arriving *while* a run is going. These do: a real uvicorn server, a real
# port, and `httpx.stream`, which is `curl -N` with assertions.

def test_ac8a_over_a_real_socket_a_late_connection_gets_everything(live_server) -> None:
    """The curl check, automated: connect after five events, receive those five, then
    watch live ones arrive *before* the run ends — which is what makes it a stream."""
    base, run = live_server
    for i in range(5):
        run.stage_started(f"stage-{i}")

    seen: list[Event] = []
    with httpx.stream("GET", f"{base}/api/runs/run-live/events", timeout=15) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        lines = response.iter_lines()

        read_until(lines, seen, lambda s: len(s) == 5)
        assert [event.stage for event in seen] == [f"stage-{i}" for i in range(5)], "AC8a"

        # The five above arrived while the run is still open: nothing has ended it yet.
        run.warning("thin_profile", "one page only")
        read_until(lines, seen, lambda s: len(s) == 6)
        assert seen[5].code == "thin_profile"

        run.finished()
        read_until(lines, seen, lambda s: s[-1].type == "run.finished")

    assert [event.seq for event in seen] == list(range(7))


def test_two_tabs_on_one_run_both_stream(live_server) -> None:
    """The Done line, over two real connections at once."""
    base, run = live_server
    run.started(grant="x")
    tabs: list[list[Event]] = [[], []]
    attached = threading.Barrier(3, timeout=15)

    def tab(seen: list[Event]) -> None:
        with httpx.stream("GET", f"{base}/api/runs/run-live/events", timeout=15) as response:
            lines = response.iter_lines()
            read_until(lines, seen, lambda s: len(s) == 1)   # the replayed run.started
            attached.wait()
            read_until(lines, seen, lambda s: s[-1].type == "run.finished")

    threads = [threading.Thread(target=tab, args=(seen,)) for seen in tabs]
    for thread in threads:
        thread.start()
    attached.wait()  # both are subscribed before anything else is emitted

    run.tool_started("search_literature", "graph neural networks")
    run.finished()
    for thread in threads:
        thread.join(timeout=15)
        assert not thread.is_alive(), "a tab never saw run.finished"

    for seen in tabs:
        assert [event.type for event in seen] == [
            "run.started", "tool.started", "run.finished",
        ]


def test_a_disconnecting_tab_is_unsubscribed(live_server) -> None:
    """A browser tab closed mid-run must not leave the run pushing events into a queue
    nobody drains for the next four minutes."""
    base, run = live_server
    run.started(grant="x")

    with httpx.stream("GET", f"{base}/api/runs/run-live/events", timeout=15) as response:
        read_until(response.iter_lines(), [], lambda s: len(s) == 1)
        assert run.subscribers == 1
        response.close()

    deadline = time.monotonic() + 10
    while run.subscribers and time.monotonic() < deadline:
        run.warning("tick", "poke the stream so it notices the socket is gone")
        time.sleep(0.05)
    assert run.subscribers == 0

    with contextlib.suppress(Exception):
        run.finished()
