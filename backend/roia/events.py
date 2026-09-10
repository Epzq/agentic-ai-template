"""Run events — the activity timeline the whole UI is driven by.

Built on Day 1 as a plain list-append plus a JSONL writer, so the Day-1 CLI produces
`fixtures/run-001.jsonl` for free (AC7) and Day 2 only has to wire the list to SSE.

Every module built before this one takes an injected `warn` or `emit` callable rather than
importing this module, so ingestion, OpenAlex and the LLM calls can all be tested without
a run. `Run.warning` and `Run.emit` are shaped to drop straight into those slots:

    ingest_grant(url, store, warn=run.warning)
    OpenAlexClient(store, warn=run.warning, emit=run.emit)
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any

from pydantic import BaseModel, ConfigDict

from roia.evidence import Evidence

# The vocabulary, verbatim from demo-spec.md §6.3.
RUN_STARTED = "run.started"
STAGE_STARTED = "stage.started"
STAGE_FINISHED = "stage.finished"
TOOL_STARTED = "tool.started"
TOOL_FINISHED = "tool.finished"
EVIDENCE_ADDED = "evidence.added"
IDENTITY_RESOLVED = "identity.resolved"
WARNING = "warning"
RUN_FINISHED = "run.finished"
RUN_FAILED = "run.failed"

EVENT_TYPES = frozenset({
    RUN_STARTED, STAGE_STARTED, STAGE_FINISHED, TOOL_STARTED, TOOL_FINISHED,
    EVIDENCE_ADDED, IDENTITY_RESOLVED, WARNING, RUN_FINISHED, RUN_FAILED,
})


class Event(BaseModel):
    """One line of the timeline: ``{seq, ts, type, …}``.

    Payload fields sit at the top level rather than under a ``payload`` key, which is what
    §6.3 specifies and what the SSE consumer expects — hence ``extra="allow"``.
    """

    model_config = ConfigDict(extra="allow")

    seq: int
    ts: datetime
    type: str


@dataclass(eq=False)
class Subscription:
    """One open event stream.

    The queue belongs to an event loop, but ``emit`` is called from the pipeline's worker
    thread, so events are handed over with ``call_soon_threadsafe`` rather than
    ``put_nowait`` — the latter is not thread-safe and would corrupt the queue's waiters.
    """

    queue: asyncio.Queue[Event]
    loop: asyncio.AbstractEventLoop

    def push(self, event: Event) -> None:
        try:
            self.loop.call_soon_threadsafe(self.queue.put_nowait, event)
        except RuntimeError:
            # The loop this stream lived on is closed. Its reader is gone with it, and
            # whoever opened the stream drops the subscription in its `finally`. Losing
            # one browser tab must not take down the run that was feeding it.
            return


class Run:
    """One run's event log, and the fan-out to any open event streams.

    ``emit`` runs on the pipeline's worker thread while ``subscribe`` runs on the event
    loop, so the lock is a ``threading.Lock``, not an ``asyncio`` one. It covers exactly
    what §6.3 says it must: appending an event and pushing it to subscribers is one
    critical section, and snapshotting the backlog and joining the fan-out is another.
    That is what makes AC8a exact rather than nearly right — no event can land between a
    new stream reading the backlog and joining, so a late subscriber sees every event
    exactly once, in order.
    """

    def __init__(self, run_id: str, *, jsonl_path: str | Path | None = None) -> None:
        self.run_id = run_id
        self.events: list[Event] = []
        self._lock = threading.Lock()
        self._subs: set[Subscription] = set()
        self._path = Path(jsonl_path) if jsonl_path else None
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text("")  # a run owns its file; never append to a stale one

    def emit(self, type: str, payload: dict[str, Any] | None = None, /, **fields: Any) -> Event:
        """Append one event to the list **and** the JSONL file.

        Takes either a payload dict or keyword fields, because the callables this is wired
        into use both shapes: ``OpenAlexClient(emit=…)`` passes ``(type, payload)`` while
        pipeline code reads better as ``run.emit("stage.started", stage="ingest")``.
        """
        with self._lock:
            # seq, append and fan-out are one critical section: two threads computing
            # len(self.events) concurrently would mint the same seq twice, and WI-2.4b
            # dedupes on seq.
            event = Event(
                seq=len(self.events),
                ts=datetime.now(UTC),
                type=type,
                **{**(payload or {}), **fields},
            )
            self.events.append(event)
            for sub in self._subs:
                sub.push(event)
        # The file write stays outside the lock: it is disk I/O, and a stream subscribing
        # on the event loop should never wait on it.
        if self._path is not None:
            try:
                with self._path.open("a", encoding="utf-8") as handle:
                    handle.write(event.model_dump_json() + "\n")
            except OSError:
                # The list is what SSE and the snapshot read; the file is a convenience.
                # A full disk at event 47 must not end a four-minute run, and there is no
                # one to warn — the warning would be another event, down the same path.
                self._path = None
        return event

    # --- the §6.3 vocabulary, as typed constructors ----------------------------------

    def started(self, **inputs: Any) -> Event:
        return self.emit(RUN_STARTED, inputs=inputs)

    def stage_started(self, stage: str) -> Event:
        return self.emit(STAGE_STARTED, stage=stage)

    def stage_finished(self, stage: str, ms: int) -> Event:
        return self.emit(STAGE_FINISHED, stage=stage, ms=ms)

    def tool_started(self, tool: str, args_summary: str = "") -> Event:
        return self.emit(TOOL_STARTED, tool=tool, args_summary=args_summary)

    def tool_finished(
        self, tool: str, ms: int, summary: str = "", evidence_added: list[str] | None = None
    ) -> Event:
        return self.emit(
            TOOL_FINISHED, tool=tool, ms=ms, summary=summary,
            evidence_added=list(evidence_added or []),
        )

    def evidence_added(self, evidence: Evidence) -> Event:
        """Announce a minted row. Takes the record itself so the four fields cannot drift."""
        return self.emit(
            EVIDENCE_ADDED,
            id=evidence.id,
            source_type=evidence.source_type,
            title=evidence.title,
            url=evidence.url,
        )

    def identity_resolved(
        self,
        author_id: str,
        display_name: str,
        institution: str | None = None,
        confidence: str = "unverified",
        margin: float | None = None,
    ) -> Event:
        """Always ``unverified``: disambiguation is a non-goal (§4) and the UI says so."""
        return self.emit(
            IDENTITY_RESOLVED,
            author_id=author_id,
            display_name=display_name,
            institution=institution,
            confidence=confidence,
            margin=margin,
        )

    def warning(self, code: str, message: str) -> Event:
        """AC9 and AC10a surface here. Signature matches ``evidence.WarnFn`` exactly, so
        every module built before this one accepts ``warn=run.warning`` unchanged."""
        return self.emit(WARNING, code=code, message=message)

    def finished(self, **fields: Any) -> Event:
        return self.emit(RUN_FINISHED, **fields)

    def failed(self, code: str, message: str) -> Event:
        return self.emit(RUN_FAILED, code=code, message=message)

    # --- timing helpers ---------------------------------------------------------------

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        """Emit ``stage.started`` / ``stage.finished`` around a block, with real elapsed ms.

        The pair and the timing are the two things a hand-written call site gets wrong, and
        a missing ``stage.finished`` leaves the UI showing a spinner that never stops. The
        ``finally`` means a raising stage still closes its own event.
        """
        started = monotonic()
        self.stage_started(name)
        try:
            yield
        finally:
            self.stage_finished(name, round((monotonic() - started) * 1000))

    @contextmanager
    def tool(self, name: str, args_summary: str = "") -> Iterator[list[str]]:
        """Same for a tool call. Yields a list to append minted evidence IDs to."""
        started = monotonic()
        added: list[str] = []
        self.tool_started(name, args_summary)
        try:
            yield added
        finally:
            self.tool_finished(name, round((monotonic() - started) * 1000),
                               evidence_added=added)

    # --- reading back -----------------------------------------------------------------

    def warnings(self) -> list[Event]:
        """Every warning so far — what WI-2.1's snapshot and the UI's alerts render."""
        return [event for event in self.snapshot() if event.type == WARNING]

    def snapshot(self) -> list[Event]:
        """A copy of the log. The list is appended to from the worker thread, so anything
        that iterates it — the HTTP snapshot, the JSONL dump — takes a copy first."""
        with self._lock:
            return list(self.events)

    # --- fan-out to event streams (WI-2.2) --------------------------------------------

    def subscribe(self) -> tuple[list[Event], Subscription]:
        """Join the fan-out and get everything already emitted, atomically (AC8a).

        Call this from the event loop that will read the queue, and always pair it with
        ``unsubscribe`` in a ``finally`` — otherwise a closed stream keeps receiving
        events into a queue nobody drains.
        """
        subscription = Subscription(asyncio.Queue(), asyncio.get_running_loop())
        with self._lock:
            backlog = list(self.events)
            self._subs.add(subscription)
        return backlog, subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        with self._lock:
            self._subs.discard(subscription)

    @property
    def subscribers(self) -> int:
        """How many streams are attached — how a test proves they are cleaned up."""
        with self._lock:
            return len(self._subs)


def read_jsonl(path: str | Path) -> list[Event]:
    """Load a recorded run. WI-2.3 replays these over SSE with a speed multiplier."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [Event.model_validate(json.loads(line)) for line in lines if line.strip()]
