"""WI-2.3 — the fixture replayer (`demo-spec.md` §8.2).

What matters here is that a replayed run is **indistinguishable from a live one** to the
frontend: same route, same framing, same order. If that ever stops being true the UI needs
two code paths, and the one exercised during development stops being the one shipped.
"""

from __future__ import annotations

import json
import pathlib

import httpx
import pytest
from fastapi.testclient import TestClient

from roia.api import _sse
from roia.events import Event, read_jsonl
from roia.replay import (
    DEFAULT_SPEED,
    MAX_GAP_S,
    available_fixtures,
    load_fixture,
    replay_events,
    schedule,
)
from tests.conftest import read_until  # `app` and `live_server` are fixtures there

F = pathlib.Path(__file__).resolve().parent.parent / "fixtures"

DONE_LINE_SECONDS = 20  # "a full run replays in 20 s with no API calls"


# --- the fixtures on disk -------------------------------------------------------------------

def test_run_001s_two_halves_describe_the_same_run() -> None:
    """The events and the report are a pair. Regenerate one without the other and the
    timeline would announce evidence the report has never heard of — the most confusing
    thing a replay could do, and invisible until someone clicks a chip."""
    fixture = load_fixture("run-001")
    assert fixture.report is not None

    announced = [event.id for event in fixture.events if event.type == "evidence.added"]
    stored = [row.id for row in fixture.report.evidence]
    assert announced == stored, "the JSONL and the report disagree about the evidence"

    cited = {i for d in fixture.report.directions for i in d.evidence_ids}
    assert cited <= set(announced)
    assert fixture.events[-1].type == "run.finished"
    assert fixture.events[-1].directions == len(fixture.report.directions)


def test_a_fixture_without_a_report_still_loads() -> None:
    """`run-000.jsonl` is a hand-built event log with no run behind it, and it is still a
    perfectly good timeline to develop against."""
    fixture = load_fixture("run-000")

    assert fixture.report is None
    assert len(fixture.events) == 25
    assert fixture.events[-1].type == "run.finished", (
        "a fixture that does not end in run.finished would leave the stream open forever"
    )


def test_every_fixture_on_disk_is_replayable() -> None:
    assert set(available_fixtures()) == {"run-000", "run-001"}
    for name in available_fixtures():
        assert load_fixture(name).events, name


def test_a_fixture_name_cannot_escape_the_fixtures_directory() -> None:
    for name in ("../pyproject", "..", "a/b", "/etc/passwd", "run-001.jsonl", ""):
        with pytest.raises(ValueError, match="not a fixture name"):
            load_fixture(name)


# --- pacing -----------------------------------------------------------------------------------

def test_the_schedule_follows_the_recorded_gaps() -> None:
    events = read_jsonl(F / "run-001.jsonl")

    offsets = [offset for offset, _ in schedule(events, speed=1.0, max_gap_s=1e9)]

    assert offsets[0] == 0.0
    assert offsets == sorted(offsets), "events must never be scheduled backwards"
    span = (events[-1].ts - events[0].ts).total_seconds()
    assert offsets[-1] == pytest.approx(span, abs=0.01)


def test_speed_divides_the_whole_schedule() -> None:
    events = read_jsonl(F / "run-001.jsonl")

    at_one = schedule(events, speed=1.0)
    at_ten = schedule(events, speed=10.0)

    assert [o / 10 for o, _ in at_one] == pytest.approx([o for o, _ in at_ten])


def test_the_hundred_second_model_call_is_clipped() -> None:
    """`run-001` spends 100.2 s of its 132 s inside one LLM call. Replayed faithfully that
    is 76% dead air; sped up enough to hide it, the other 161 events are a blur."""
    events = read_jsonl(F / "run-001.jsonl")
    gaps = [
        (events[i + 1].ts - events[i].ts).total_seconds() for i in range(len(events) - 1)
    ]
    assert max(gaps) > 90, "the fixture no longer has the pathological gap this guards"

    offsets = [offset for offset, _ in schedule(events, speed=1.0)]
    steps = [b - a for a, b in zip(offsets[:-1], offsets[1:], strict=True)]
    assert max(steps) == pytest.approx(MAX_GAP_S, abs=0.01)


def test_the_done_line_a_full_run_replays_inside_twenty_seconds() -> None:
    events = read_jsonl(F / "run-001.jsonl")

    total = schedule(events, speed=DEFAULT_SPEED)[-1][0]

    assert total < DONE_LINE_SECONDS, f"{total:.1f}s at the default speed"
    assert total > 5, "so fast it is not a replay any more, just a dump"


def test_a_non_positive_speed_is_refused() -> None:
    for speed in (0.0, -1.0):
        with pytest.raises(ValueError, match="speed must be positive"):
            schedule([], speed=speed)


def two_second_gaps(count: int) -> list[Event]:
    """Real events, re-timed onto an exact 2 s grid so the arithmetic below is exact."""
    return [
        Event.model_validate({**e.model_dump(), "ts": e.ts.replace(second=i * 2, microsecond=0)})
        for i, e in enumerate(read_jsonl(F / "run-000.jsonl")[:count])
    ]


@pytest.mark.asyncio
async def test_replay_events_waits_for_the_schedule_it_computed() -> None:
    """Driven with a fake clock, so the assertion is about the pacing rather than about
    how long the test was willing to sit there."""
    events = two_second_gaps(5)
    slept: list[float] = []
    now = [0.0]

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    seen = [
        e async for e in replay_events(
            events, speed=2.0, sleep=fake_sleep, clock=lambda: now[0]
        )
    ]

    assert [e.seq for e in seen] == [e.seq for e in events]
    assert len(slept) == 4, "one wait per gap, none before the first event"
    assert slept == pytest.approx([1.0, 1.0, 1.0, 1.0]), "2 s gaps at speed 2"


@pytest.mark.asyncio
async def test_a_slow_consumer_does_not_make_the_replay_drift() -> None:
    """Offsets are absolute, not accumulated. A consumer that stalls for one event costs
    the replay that event's lateness, not the rest of the run's — otherwise a 162-event
    playback would finish steadily later than the schedule says it should."""
    events = two_second_gaps(4)
    slept: list[float] = []
    now = [0.0]

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    stream = replay_events(events, speed=1.0, sleep=fake_sleep, clock=lambda: now[0])
    await anext(stream)
    now[0] += 5.0          # the consumer went away for five seconds
    async for _ in stream:
        pass

    assert sum(slept) == pytest.approx(1.0), (
        f"should have waited only for the one event still ahead of the clock, got {slept}"
    )


# --- over HTTP ---------------------------------------------------------------------------------

@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


def test_the_replayed_snapshot_carries_the_report(client) -> None:
    """WI-2.5 renders from the snapshot and nowhere else, so the report view has to work
    offline too — that is what makes `?fixture=` the demo-day fallback rather than half of one."""
    snapshot = client.get("/api/runs/run-001?fixture=run-001").json()

    assert snapshot["status"] == "finished"
    assert len(snapshot["events"]) == 162
    assert len(snapshot["report"]["directions"]) == 3
    assert len(snapshot["report"]["evidence"]) == 85
    assert snapshot["inputs"]["grant_src"] == "https://www.rgp.gov.sg/nrf-ar/crp"
    assert [w["code"] for w in snapshot["warnings"]] == [
        e["code"] for e in snapshot["events"] if e["type"] == "warning"
    ]


def test_a_replay_needs_no_run_to_exist(client) -> None:
    """The whole point: nothing was posted to `/api/runs` and there is no pipeline."""
    assert client.app.state.roia.runs == {}

    assert client.get("/api/runs/anything/events?fixture=run-000").status_code == 200
    assert client.get("/api/runs/anything?fixture=run-000").status_code == 200


def test_an_unknown_fixture_is_a_404_that_names_the_alternatives(client) -> None:
    response = client.get("/api/runs/x/events?fixture=nope")

    assert response.status_code == 404
    assert "run-001" in response.json()["detail"]


def test_a_traversing_fixture_name_is_rejected_before_the_filesystem(client) -> None:
    for name in ("../pyproject", "..%2F..%2Fetc%2Fpasswd", "run-001.jsonl"):
        response = client.get(f"/api/runs/x/events?fixture={name}")
        assert response.status_code == 422, name


def test_an_out_of_range_speed_is_refused(client) -> None:
    for speed in ("0", "-3", "100000"):
        response = client.get(f"/api/runs/x/events?fixture=run-000&speed={speed}")
        assert response.status_code == 422, speed


def test_a_replayed_frame_is_shaped_exactly_like_a_live_one(client) -> None:
    """One parser in the frontend, not two."""
    body = client.get("/api/runs/x/events?fixture=run-000&speed=1000").text
    events = read_jsonl(F / "run-000.jsonl")

    expected = "".join(
        f"id: {frame['id']}\r\ndata: {frame['data']}\r\n\r\n"
        for frame in (_sse(event) for event in events)
    )
    assert body == expected
    assert "event:" not in body, "a named SSE event never reaches EventSource.onmessage"


def test_the_replay_streams_over_a_real_socket_in_order(live_server) -> None:
    """`?speed=` really does pace it: 25 events that would take 0 s at the recorded
    timestamps still arrive one at a time, and the stream closes on its own."""
    base, _ = live_server
    seen: list[Event] = []

    with httpx.stream(
        "GET", f"{base}/api/runs/x/events?fixture=run-001&speed=200", timeout=30
    ) as response:
        assert response.headers["x-accel-buffering"] == "no"
        read_until(response.iter_lines(), seen, lambda s: s[-1].type == "run.finished")

    recorded = read_jsonl(F / "run-001.jsonl")
    assert [e.seq for e in seen] == [e.seq for e in recorded]
    assert [e.type for e in seen] == [e.type for e in recorded]
    assert len([e for e in seen if e.type == "evidence.added"]) == 85


def test_no_api_calls_are_made_during_a_replay(monkeypatch, client) -> None:
    """`with no API calls` is the Done line's second half.

    The seam is `HTTPTransport`, not `Client.send`: `TestClient` *is* an httpx client and
    routes through its own in-process transport, so patching `send` would only catch the
    test's own request and prove nothing.
    """
    def explode(*args, **kwargs):
        raise AssertionError("the replayer made a network call")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", explode)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", explode)
    monkeypatch.setattr("socket.socket.connect", explode)

    body = client.get("/api/runs/x/events?fixture=run-001&speed=1000").text
    snapshot = client.get("/api/runs/x?fixture=run-001").json()

    assert body.count("data:") == 162
    assert json.loads(body.split("data: ", 1)[1].split("\r\n", 1)[0])["type"] == "run.started"
    assert snapshot["report"] is not None
