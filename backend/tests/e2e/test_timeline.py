"""WI-2.4b — the live activity timeline (AC7).

Driven against the replayer (`?fixture=run-001`), which is a byte-identical stream to a live
run and ends in `run.finished` the same way — so `es.close()` and dedupe-on-seq are exercised
without a five-minute run or a single API call.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

FIXTURE = "run-001"
#: The recorded run: 162 events, of which 85 are evidence.added and 25 are tool steps.
TOTAL_EVENTS = 162
TOTAL_SOURCES = 85
TOTAL_TOOLS = 25


def replay(ui: str, speed: int = 200) -> str:
    return f"{ui}/runs/{FIXTURE}?fixture={FIXTURE}&speed={speed}"


def wait_for_replay(page: Page, timeout: int = 30000) -> None:
    """Wait for the STREAM to finish, not the snapshot.

    ⚠️ `run-status` is the wrong signal under `?fixture=`: the snapshot answers `finished`
    immediately — the recorded run genuinely is — while the stream is still replaying at
    `&speed=`. Asserting on the status chip and then counting rows reads a half-built
    timeline, which is exactly how the first version of these tests failed.
    """
    expect(page.get_by_test_id("event-count")).to_have_text(
        f"{TOTAL_EVENTS} events", timeout=timeout
    )


def test_ac7_the_timeline_streams_well_over_fifteen_events(ui: str, page: Page) -> None:
    """`The activity timeline streams >= 15 events during a run`."""
    page.goto(replay(ui))

    expect(page.get_by_test_id("timeline")).to_be_visible()
    expect(page.get_by_test_id("event-count")).to_have_text(f"{TOTAL_EVENTS} events")

    rows = page.get_by_test_id("timeline-event")
    assert rows.count() >= 15, f"AC7 wants >= 15, got {rows.count()}"
    # 10 stages + 25 tools + 4 warnings + run.started + identity.resolved + run.finished.
    assert rows.count() == 42, "one row per step, not one per raw event"


def test_ac7_the_timeline_remains_visible_after_completion(ui: str, page: Page) -> None:
    """`and remains visible after completion` — the second half of AC7, and the half a
    stream-driven timeline gets wrong if closing the stream clears its state."""
    page.goto(replay(ui))
    wait_for_replay(page)
    expect(page.get_by_test_id("stream-live")).to_have_count(0)
    before = page.get_by_test_id("timeline-event").count()

    page.wait_for_timeout(1500)

    expect(page.get_by_test_id("timeline")).to_be_visible()
    assert page.get_by_test_id("timeline-event").count() == before


def test_the_sources_counter_reaches_every_evidence_row(ui: str, page: Page) -> None:
    page.goto(replay(ui))
    wait_for_replay(page)

    expect(page.get_by_test_id("sources-count")).to_have_text(f"Sources ({TOTAL_SOURCES})")


def test_started_and_finished_collapse_into_one_row_with_a_duration(ui: str, page: Page) -> None:
    """The run emits 25 `tool.started` and 25 `tool.finished`. Rendered raw that is 50 rows
    saying the same 25 things twice."""
    page.goto(replay(ui))
    wait_for_replay(page)

    tools = page.locator('[data-testid=timeline-event][data-kind=tool]')
    assert tools.count() == TOTAL_TOOLS

    # Every tool finished, so every tool row carries a duration rather than a spinner.
    assert page.get_by_test_id("timeline-running").count() == 0
    assert "search_literature" in (page.get_by_test_id("timeline").text_content() or "")


def test_the_stream_closes_on_run_finished_and_does_not_reconnect(ui: str, page: Page) -> None:
    """🔴 The one that bites. The server ends the stream itself after `run.finished`, and an
    `EventSource` treats a server-closed connection as a *dropped* one — it reconnects after
    ~3 s, replays all 162 events, and does it again, forever. `es.close()` is the only thing
    that stops it, and nothing else in the UI would look wrong while it happened.
    """
    opened: list[str] = []
    page.on("request", lambda r: opened.append(r.url) if "/events" in r.url else None)

    page.goto(replay(ui))
    wait_for_replay(page)

    # Longer than EventSource's ~3 s reconnect delay. A shorter wait proves nothing.
    page.wait_for_timeout(5000)

    assert len(opened) == 1, f"the stream reconnected: {opened}"
    expect(page.get_by_test_id("event-count")).to_have_text(f"{TOTAL_EVENTS} events")


def test_repeated_sequence_numbers_are_rendered_once(ui: str, page: Page) -> None:
    """Every connection replays from seq 0 — `Last-Event-ID` is ignored by design (AC8a), so
    any reconnect re-sends the whole run. Dedupe on `seq` is what makes that harmless.

    Served by hand rather than by the replayer, because the honest server never repeats a
    seq: the only way to test the guard is to feed it duplicates.
    """
    ts = "2026-09-06T00:00:00Z"
    started = f'{{"seq":1,"ts":"{ts}","type":"stage.started","stage":"ingest"}}'
    ended = f'{{"seq":2,"ts":"{ts}","type":"stage.finished","stage":"ingest","ms":900}}'
    frames = [
        (0, f'{{"seq":0,"ts":"{ts}","type":"run.started","inputs":{{}}}}'),
        (1, started),
        (2, ended),
        (1, started),  # the replay a reconnect would produce
        (2, ended),
        (3, f'{{"seq":3,"ts":"{ts}","type":"run.finished"}}'),
    ]
    body = "".join(f"id: {seq}\r\ndata: {data}\r\n\r\n" for seq, data in frames)
    page.route(
        "**/api/runs/run-dup/events*",
        lambda route: route.fulfill(status=200, content_type="text/event-stream", body=body),
    )
    page.route(
        "**/api/runs/run-dup?**",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"run_id":"run-dup","status":"finished",'
            '"inputs":{"grant_src":"x","profile_url":"y","answers":{}},'
            '"warnings":[],"events":[],"report":null}',
        ),
    )

    page.goto(f"{ui}/runs/run-dup?fixture={FIXTURE}")

    expect(page.get_by_test_id("event-count")).to_have_text("4 events")
    # run.started, the ingest stage (collapsed), run.finished — each exactly once.
    assert page.get_by_test_id("timeline-event").count() == 3
    assert page.get_by_test_id("timeline").text_content().count("ingest") == 1


def test_a_reload_mid_replay_restores_the_timeline_from_seq_zero(ui: str, page: Page) -> None:
    """AC8b through the stream rather than the snapshot: the run id is in the URL, so a
    refresh reconnects and the server replays everything it has already sent."""
    page.goto(replay(ui, speed=8))
    expect(page.get_by_test_id("timeline-event").first).to_be_visible(timeout=15000)

    page.reload()

    expect(page.get_by_test_id("run-status")).to_have_text("finished")
    expect(page.get_by_test_id("event-count")).to_have_text(f"{TOTAL_EVENTS} events", timeout=30000)
    assert page.get_by_test_id("timeline-event").count() == 42
