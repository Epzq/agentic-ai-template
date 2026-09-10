"""Replay a recorded run over SSE — `demo-spec.md` §8.2's demo-day insurance.

Two jobs, and the second is the one you will use daily.

**Insurance.** If the wifi dies or OpenAlex rate-limits five minutes before the demo,
`?fixture=run-001` plays back a real cold run with no API calls at all.

**The frontend iteration loop.** Nobody can develop a timeline against a 2-minute run. At
`?speed=10` the same 162 events arrive in about three seconds, in the same order, through
the same endpoint, framed identically to the live stream — so the UI cannot tell the
difference and there is only ever one parser to maintain.

A fixture is a **pair**: `run-001.jsonl` (the events) and `run-001.report.json` (what that
same run produced). `tests/test_replay.py` asserts the two describe the same run, because
regenerating one half and not the other would produce a replay whose timeline and report
disagree — the single most confusing thing this file could do.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any

from roia.events import Event, read_jsonl
from roia.paths import FIXTURES_DIR
from roia.report import Report

#: A fixture name is a path segment we build a filename from, so it is whitelisted rather
#: than escaped: `?fixture=../../etc/passwd` must not reach the filesystem at all.
FIXTURE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

#: Slightly faster than the real run, so the Done line ("a full run replays in 20 s")
#: holds without the playback feeling like a fast-forward. `?speed=10` for development.
DEFAULT_SPEED = 1.5
MAX_SPEED = 1000.0

#: No single pause longer than this, however long the real one was. In `run-001` the LLM #4
#: assessment call is a **100.2 s gap out of 132 s** — 76% of the run is one silent wait.
#: Replayed faithfully that is dead air, and speeding it up enough to remove it turns the
#: other 161 events into an unreadable blur. Clipping it keeps both halves watchable. The
#: timings the UI *displays* are the recorded ones either way: `ts` and `ms` ride along
#: inside each event and are never rewritten.
MAX_GAP_S = 3.0

#: Injected together so a test can drive the schedule on a fake clock. They come as a
#: pair on purpose: a fake sleep with a real clock makes every wait look longer than the
#: last, because the pacing below is measured against elapsed time rather than accumulated.
SleepFn = Callable[[float], Awaitable[Any]]
ClockFn = Callable[[], float]


@dataclass(frozen=True)
class Fixture:
    """A recorded run: its events, and the report the same run produced."""

    name: str
    events: list[Event]
    report: Report | None


def fixture_path(name: str, suffix: str) -> Path:
    """Resolve `fixtures/{name}{suffix}`, refusing anything that is not a plain name."""
    if not FIXTURE_NAME.match(name):
        raise ValueError(f"not a fixture name: {name!r}")
    return FIXTURES_DIR / f"{name}{suffix}"


def available_fixtures() -> list[str]:
    """Every replayable fixture on disk. Used to say something useful in a 404."""
    if not FIXTURES_DIR.is_dir():
        return []
    return sorted(
        path.stem for path in FIXTURES_DIR.glob("*.jsonl") if FIXTURE_NAME.match(path.stem)
    )


def load_fixture(name: str) -> Fixture:
    """Load a recorded run. Raises `FileNotFoundError` if there is no such fixture.

    The report half is optional: `run-000.jsonl` is a hand-built event log with no run
    behind it, and it is still perfectly good for exercising the timeline.
    """
    events = read_jsonl(fixture_path(name, ".jsonl"))
    report_file = fixture_path(name, ".report.json")
    report = Report.model_validate_json(report_file.read_text()) if report_file.is_file() else None
    return Fixture(name=name, events=events, report=report)


def schedule(
    events: list[Event], *, speed: float = DEFAULT_SPEED, max_gap_s: float = MAX_GAP_S
) -> list[tuple[float, Event]]:
    """Pair each event with the second it should be sent at, starting from zero.

    Pure, and the whole of the pacing logic — the async part below only sleeps. Offsets are
    cumulative rather than per-event so that a slow consumer cannot make the replay drift
    steadily later and later.
    """
    if speed <= 0:
        raise ValueError(f"speed must be positive, got {speed}")
    offsets: list[tuple[float, Event]] = []
    elapsed = 0.0
    for index, event in enumerate(events):
        if index:
            gap = (event.ts - events[index - 1].ts).total_seconds()
            elapsed += min(max(gap, 0.0), max_gap_s) / speed
        offsets.append((elapsed, event))
    return offsets


async def replay_events(
    events: list[Event],
    *,
    speed: float = DEFAULT_SPEED,
    max_gap_s: float = MAX_GAP_S,
    sleep: SleepFn | None = None,
    clock: ClockFn = monotonic,
) -> AsyncIterator[Event]:
    """Yield the recorded events at their recorded pacing, divided by `speed`.

    Each wait is measured against the schedule's absolute offset rather than added to the
    last one, so a slow consumer costs the replay that event's lateness and not the whole
    run's: the playback catches up instead of drifting steadily further behind.
    """
    wait = sleep or asyncio.sleep
    started = clock()
    for offset, event in schedule(events, speed=speed, max_gap_s=max_gap_s):
        behind = offset - (clock() - started)
        if behind > 0:
            await wait(behind)
        yield event
