"""The HTTP surface — `demo-spec.md` §6.2.

Two things here are load-bearing and easy to get wrong.

**The pipeline is synchronous and slow.** `run_pipeline` blocks for minutes on HTTP and
model calls, so it runs in a worker thread (`asyncio.to_thread`) inside a task. Calling it
directly on the event loop would freeze every other request — including the SSE stream that
is the whole point of watching a run.

**No module-level mutable state.** Runs and probes live on `app.state`, created per
application in the lifespan handler, so two apps in one test process cannot see each other's
runs and nothing survives an import.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, model_validator
from sse_starlette.sse import EventSourceResponse

from roia.config import Settings, get_settings
from roia.events import (
    RUN_FAILED,
    RUN_FINISHED,
    RUN_STARTED,
    WARNING,
    Event,
    Run,
    Subscription,
    read_jsonl,
)
from roia.evidence import EvidenceStore
from roia.ingest import ProbeResult, probe, probe_id_for
from roia.paths import FRONTEND_DIST, RUNS_DIR
from roia.pipeline import RunInputs, run_pipeline
from roia.replay import (
    DEFAULT_SPEED,
    MAX_SPEED,
    Fixture,
    available_fixtures,
    load_fixture,
    replay_events,
)
from roia.report import Report, render_markdown

#: Where finished runs are kept so a restart does not lose them.
#: The Vite dev server. CORS is only opened when ROIA_DEV is set.
DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

#: PLUS: the upload endpoint. A grant PDF that is not a PDF, or is enormous, is a mistake
#: worth refusing at the door rather than four minutes into a run.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
PDF_MAGIC = b"%PDF"

#: The two events after which there is nothing more to stream.
TERMINAL_EVENTS = frozenset({RUN_FINISHED, RUN_FAILED})
#: Seconds between comment-only keep-alives on an idle stream. Proxies and load balancers
#: close a connection that has been silent too long, and a stage can take minutes.
SSE_PING_SECONDS = 15
#: How often an otherwise-idle stream re-checks whether its run is still alive. Only ever
#: reached when a run ends without a terminal event — a cancelled task, or a shutdown.
SSE_IDLE_TICK_SECONDS = 1.0
#: `Cache-Control` is what the spec asks for; `no-store` is sse-starlette's own default and
#: is kept alongside it. `X-Accel-Buffering` is set by sse-starlette itself.
SSE_HEADERS = {"Cache-Control": "no-cache, no-store"}

RunStatus = Literal["running", "finished", "failed"]

#: WI-2.3's replay knobs. The pattern is the same whitelist `roia.replay` enforces, so a
#: name that could escape `fixtures/` is a 422 before any code looks at the filesystem.
Fixtured = Annotated[str | None, Query(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")]
Speed = Annotated[float, Query(gt=0, le=MAX_SPEED)]


@dataclass
class RunRecord:
    """One run's server-side state. `task` is None for a run rehydrated from disk."""

    run: Run
    inputs: RunInputs
    task: asyncio.Task[None] | None = None
    report: Report | None = None
    #: Set when the pipeline itself blew up, which `run_pipeline` should never allow.
    error: str | None = None

    @property
    def status(self) -> RunStatus:
        """`finished` only once the report is actually attached.

        `run_pipeline` emits `run.finished` from inside the worker thread, before it
        returns, so deriving status from the event alone leaves a window where the snapshot
        says finished and `report` is still None — and the UI navigates to a report that is
        not there. The task, not the event, is what says the run is done. A rehydrated run
        has no task and falls back to its events, which is correct because it finished
        before the process started.
        """
        if self.task is not None and not self.task.done():
            return "running"
        types = {event.type for event in self.run.snapshot()}
        if self.error is not None or "run.failed" in types:
            return "failed"
        if "run.finished" in types:
            return "finished"
        return "running"


@dataclass
class AppState:
    """Everything the app remembers. Per-application, never at module scope."""

    runs: dict[str, RunRecord] = field(default_factory=dict)
    #: Probes are cached by input hash so `Analyse` twice does not re-fetch seven PDFs.
    probes: dict[str, tuple[ProbeResult, EvidenceStore]] = field(default_factory=dict)
    uploads: dict[str, Path] = field(default_factory=dict)
    runs_dir: Path = RUNS_DIR


# --- request and response models --------------------------------------------------------

class ProbeRequest(BaseModel):
    grant_url: str | None = None
    grant_upload_id: str | None = None
    profile_url: str

    @model_validator(mode="after")
    def _needs_a_grant(self) -> ProbeRequest:
        if not (self.grant_url or self.grant_upload_id):
            raise ValueError("one of grant_url or grant_upload_id is required")
        return self


class RunRequest(ProbeRequest):
    """`422 if neither grant source is present` — inherited from ProbeRequest's validator."""

    probe_id: str | None = None
    answers: dict[str, str] = {}


class RunCreated(BaseModel):
    run_id: str


class UploadCreated(BaseModel):
    upload_id: str
    sha256: str


class RunSnapshot(BaseModel):
    """What WI-2.5 renders. The report lives here and nowhere else."""

    run_id: str
    status: RunStatus
    inputs: RunInputs
    warnings: list[Event]
    events: list[Event]
    report: Report | None = None


# --- app --------------------------------------------------------------------------------

def state_of(request: Request) -> AppState:
    state: AppState = request.app.state.roia
    return state


#: FastAPI's modern injection form. `state: AppState = Depends(...)` is the older
#: spelling and trips ruff's B008 for what is, here, exactly the intended behaviour.
State = Annotated[AppState, Depends(state_of)]


def create_app(settings: Settings | None = None, *, runs_dir: Path | None = None) -> FastAPI:
    """Build an application. Called per test as well as by uvicorn, so nothing is shared."""
    active = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.roia = AppState(runs_dir=runs_dir or RUNS_DIR)
        _rehydrate(app.state.roia)
        yield

    app = FastAPI(title="Research Opportunity Intelligence", lifespan=lifespan)
    if active.dev:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=DEV_ORIGINS,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.post("/api/uploads", response_model=UploadCreated)
    async def create_upload(  # PLUS — CORE ships URL-only grant input
        file: UploadFile, state: State
    ) -> UploadCreated:
        body = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(body) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"upload exceeds {MAX_UPLOAD_BYTES // 1024 // 1024} MB")
        if body[:4] != PDF_MAGIC:
            # By magic bytes, not the filename or the declared type — the same rule
            # ingestion uses, and for the same reason.
            raise HTTPException(415, "only PDF uploads are supported")

        digest = hashlib.sha256(body).hexdigest()
        target = state.runs_dir / "uploads" / f"{digest[:16]}.pdf"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        state.uploads[digest[:16]] = target
        return UploadCreated(upload_id=digest[:16], sha256=digest)

    @app.post("/api/probe", response_model=ProbeResult)
    async def create_probe(
        body: ProbeRequest, state: State
    ) -> ProbeResult:
        source = _grant_source(body.grant_url, body.grant_upload_id, state)
        probe_id = probe_id_for(source, body.profile_url)
        if probe_id in state.probes:
            return state.probes[probe_id][0]

        store = EvidenceStore()
        # Blocking: it fetches the call and the profile. Off the event loop it goes.
        result = await asyncio.to_thread(probe, source, body.profile_url, store)
        state.probes[probe_id] = (result, store)
        return result

    @app.post("/api/runs", response_model=RunCreated, status_code=201)
    async def create_run(body: RunRequest, state: State) -> RunCreated:
        source = _grant_source(body.grant_url, body.grant_upload_id, state)
        inputs = RunInputs(
            grant_src=source, profile_url=body.profile_url, answers=body.answers
        )
        run_id = f"run-{len(state.runs) + 1:03d}-{probe_id_for(source, body.profile_url)[3:]}"

        cached = state.probes.get(body.probe_id or "")
        if body.probe_id and cached is None:
            # 🔴 Refusing is the point. `run_pipeline` only reaches `resolve_answers` when a
            # probe is in hand, so starting anyway would drop the applicant's chosen call
            # period on the floor and brief LLM #1 on the whole programme instead — a
            # four-minute run against the wrong deadline, with nothing logged. Restarting
            # the server with a tab open is all it takes to get here.
            raise HTTPException(
                404,
                f"probe {body.probe_id} is no longer held by the server "
                f"(it restarted, or the probe was never made here). Analyse again.",
            )
        if cached is not None and body.probe_id != probe_id_for(source, body.profile_url):
            # A held probe carries the *documents* this run analyses, so one made for other
            # inputs makes the run read grant A while `inputs`, the report header and every
            # archived event say grant B. Checked **after** the branch above, not before: an
            # id the server no longer holds is the restarted-server case and stays a 404,
            # which is the distinction that tells the user to press Analyse rather than to
            # go looking for what they typed wrong.
            raise HTTPException(
                422,
                f"probe {body.probe_id} was made for different inputs than this run "
                f"({probe_id_for(source, body.profile_url)}). Analyse again.",
            )
        if body.answers and cached is None:
            raise HTTPException(
                422, "answers were given without a probe to resolve them against"
            )
        record = RunRecord(run=Run(run_id), inputs=inputs)
        state.runs[run_id] = record
        record.task = asyncio.create_task(_execute(record, cached, state))
        return RunCreated(run_id=run_id)

    @app.get("/api/runs/{run_id}", response_model=RunSnapshot)
    async def get_run(run_id: str, state: State, fixture: Fixtured = None) -> RunSnapshot:
        if fixture is not None:
            return _fixture_snapshot(run_id, _fixture_or_404(fixture))
        record = state.runs.get(run_id)
        if record is None:
            raise HTTPException(404, f"no run {run_id}")
        return RunSnapshot(
            run_id=run_id,
            status=record.status,
            inputs=record.inputs,
            warnings=record.run.warnings(),
            events=record.run.snapshot(),
            report=record.report,
        )

    @app.get("/api/runs/{run_id}/report.md", response_class=PlainTextResponse)
    async def get_run_markdown(
        run_id: str, state: State, fixture: Fixtured = None
    ) -> PlainTextResponse:
        """§6.2's third representation of a run: the report as markdown, no LLM (§5 step 10).

        `render_markdown` already existed and was reachable only from the CLI, so the one
        artefact a reviewer would actually forward — the readable report — could not be got
        out of the running app at all. Same renderer as the CLI, so what you paste into an
        email is byte-for-byte what the run produced.

        `409`, not `404`, while a run is still going: the run exists and the URL is right,
        there is simply no report yet, and a client that cannot tell those apart retries the
        wrong one.
        """
        if fixture is not None:
            recorded = _fixture_or_404(fixture)
            report = recorded.report
            warnings = [e for e in recorded.events if e.type == WARNING]
        else:
            record = state.runs.get(run_id)
            if record is None:
                raise HTTPException(404, f"no run {run_id}")
            report, warnings = record.report, record.run.warnings()
        if report is None:
            raise HTTPException(409, f"run {run_id} has no report yet")
        return PlainTextResponse(
            render_markdown(report, warnings), media_type="text/markdown; charset=utf-8"
        )

    @app.get("/api/runs/{run_id}/events")
    async def stream_run(
        run_id: str, state: State, fixture: Fixtured = None, speed: Speed = DEFAULT_SPEED
    ) -> EventSourceResponse:
        """The activity timeline, live (AC7) — and from seq 0 however late you join (AC8a).

        With `?fixture=run-001` it replays a recorded run instead, at `?speed=` × real time
        and with no API calls (WI-2.3). Same route, same framing, same order — the frontend
        cannot tell the two apart, which is the entire point of having a replayer.

        No `GZipMiddleware` may ever wrap this route: a compressor buffers, and a buffered
        event stream arrives in one lump at the end, which is the opposite of the point.
        The app adds none, and a test asserts it stays that way.
        """
        if fixture is not None:
            return EventSourceResponse(
                _replay_stream(_fixture_or_404(fixture), speed),
                headers=SSE_HEADERS,
                ping=SSE_PING_SECONDS,
            )
        record = state.runs.get(run_id)
        if record is None:
            raise HTTPException(404, f"no run {run_id}")
        return EventSourceResponse(
            _event_stream(record), headers=SSE_HEADERS, ping=SSE_PING_SECONDS
        )

    # Last, so every /api route above wins on registration order.
    _mount_spa(app)
    return app


def _mount_spa(app: FastAPI) -> None:
    """Serve the built frontend at the same origin in prod (WI-2.4a).

    Mounted **only when `frontend/dist/` exists**. In development it does not: the Vite dev
    server owns :5173 and talks to this API cross-origin, which is what `ROIA_DEV`'s CORS is
    for. The API has to boot before anyone has ever run `npm run build`.

    The catch-all exists because `/runs/{id}` is a **client-side** route: there is no such
    file, and the browser must be handed `index.html` so React Router can resolve it. That
    is also why a deep-linked reload works at all, which is half of AC8b.
    """
    if not FRONTEND_DIST.is_dir():
        return

    root = FRONTEND_DIST.resolve()

    @app.get("/{spa_path:path}", include_in_schema=False)
    async def serve_spa(spa_path: str) -> FileResponse:
        if spa_path.startswith("api/"):
            # Registration order already gave the real API routes first pass, so anything
            # still under /api is a genuine 404 — not a client route, and never index.html.
            raise HTTPException(404, "not found")
        target = (root / spa_path).resolve()
        if spa_path and target.is_relative_to(root) and target.is_file():
            return FileResponse(target)
        return FileResponse(root / "index.html")


async def _event_stream(record: RunRecord) -> AsyncIterator[dict[str, str]]:
    """Replay everything, then follow along until the run ends.

    The backlog and the subscription are taken together under the run's lock, so an event
    emitted while this is starting up is either in the backlog or in the queue, never both
    and never neither. `id:` carries the seq, which is also inside the JSON — WI-2.4b
    dedupes on it.

    Nothing sets an `event:` name, deliberately: a named SSE event does not reach
    `EventSource.onmessage`, only an `addEventListener` for that exact name, and the
    timeline switches on the `type` field in the payload instead.
    """
    backlog, subscription = record.run.subscribe()
    try:
        over = False
        for event in backlog:
            yield _sse(event)
            over = over or event.type in TERMINAL_EVENTS

        while not over:
            try:
                event = await asyncio.wait_for(
                    subscription.queue.get(), SSE_IDLE_TICK_SECONDS
                )
            except TimeoutError:
                # Belt and braces. `_execute` turns even a crash into `run.failed`, so the
                # only way to be here is a run that ended without emitting anything — a
                # cancelled task. Without this the browser would hold an open stream for a
                # run that is never going to speak again.
                over = _ended_silently(record, subscription)
                continue
            yield _sse(event)
            over = event.type in TERMINAL_EVENTS
    finally:
        # A disconnected client cancels this generator; without the unsubscribe the run
        # would keep pushing events into a queue nobody reads for the rest of its life.
        record.run.unsubscribe(subscription)


def _sse(event: Event) -> dict[str, str]:
    return {"id": str(event.seq), "data": event.model_dump_json()}


def _fixture_or_404(name: str) -> Fixture:
    try:
        return load_fixture(name)
    except (OSError, ValueError):
        # A demo-day 404 that names the alternatives beats one that only says no.
        raise HTTPException(
            404, f"no fixture {name!r}; have {available_fixtures()}"
        ) from None


async def _replay_stream(fixture: Fixture, speed: float) -> AsyncIterator[dict[str, str]]:
    """A recorded run, paced. Framed by `_sse` — the same function the live stream uses,
    so a replayed frame and a live frame are byte-for-byte the same shape."""
    async for event in replay_events(fixture.events, speed=speed):
        yield _sse(event)


def _fixture_snapshot(run_id: str, fixture: Fixture) -> RunSnapshot:
    """The snapshot half of a replay, so the report view has something to render offline.

    `status` is `finished`: everything a fixture has, it has already. The inputs come from
    the recorded `run.started`, which is what the run was actually given.
    """
    started = next((e for e in fixture.events if e.type == RUN_STARTED), None)
    return RunSnapshot(
        run_id=run_id,
        status="finished",
        inputs=_recorded_inputs(getattr(started, "inputs", None), fixture.name),
        warnings=[event for event in fixture.events if event.type == WARNING],
        events=fixture.events,
        report=fixture.report,
    )


def _recorded_inputs(recorded: object, name: str) -> RunInputs:
    """What the recorded run was given — read leniently, because fixtures outlive schemas.

    `run-000.jsonl` was hand-built in WI-1.3, before `RunInputs` existed, and spells the
    grant `grant_url`; a real run spells it `grant_src`. Validating strictly would turn the
    demo-day fallback into a 500 the first time an old fixture was played.
    """
    fields = recorded if isinstance(recorded, dict) else {}
    answers = fields.get("answers")
    return RunInputs(
        grant_src=str(fields.get("grant_src") or fields.get("grant_url") or f"fixture:{name}"),
        profile_url=str(fields.get("profile_url") or ""),
        answers={str(k): str(v) for k, v in answers.items()} if isinstance(answers, dict) else {},
    )


def _ended_silently(record: RunRecord, subscription: Subscription) -> bool:
    """True when the run's task is finished, nothing is left to drain, and no terminal
    event ever arrived."""
    return (
        record.task is not None
        and record.task.done()
        and subscription.queue.empty()
    )


def _grant_source(url: str | None, upload_id: str | None, state: AppState) -> str:
    if url:
        return url
    path = state.uploads.get(upload_id or "")
    if path is None:
        raise HTTPException(404, f"no upload {upload_id}")
    return str(path)


async def _execute(
    record: RunRecord,
    cached: tuple[ProbeResult, EvidenceStore] | None,
    state: AppState,
) -> None:
    """Run the pipeline in a worker thread and persist what it produced.

    `run_pipeline` is minutes of blocking HTTP and model calls. On the event loop it would
    stall every other request, including the event stream someone is watching it through.
    """
    # `.fork()`, not the cached store itself: it is shared by every run made from this
    # probe, and minting into it directly makes run 2's report contain run 1's evidence.
    probe_result, store = (cached[0], cached[1].fork()) if cached else (None, None)
    try:
        result = await asyncio.to_thread(
            run_pipeline, record.inputs, record.run, probe=probe_result, store=store
        )
        record.report = result.report
    except Exception as exc:  # noqa: BLE001 - a task that dies silently is the worst case
        record.error = f"{type(exc).__name__}: {exc}"
        record.run.failed(type(exc).__name__, str(exc))
    finally:
        _persist(record, state)


def _persist(record: RunRecord, state: AppState) -> None:
    """Write the run to disk so a restart does not lose it. Never raises."""
    directory = state.runs_dir / record.run.run_id
    try:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "events.jsonl").write_text(
            "".join(event.model_dump_json() + "\n" for event in record.run.snapshot())
        )
        (directory / "inputs.json").write_text(record.inputs.model_dump_json(indent=1))
        if record.report is not None:
            (directory / "report.json").write_text(
                json.dumps(record.report.model_dump(mode="json"), indent=1)
            )
    except OSError:
        # Losing the archive is bad; losing the in-flight run because the disk is full
        # would be worse. The snapshot still serves from memory.
        return


def _rehydrate(state: AppState) -> None:
    """Load finished runs from `runs/` on startup. A restart must not lose a report."""
    if not state.runs_dir.is_dir():
        return
    for directory in sorted(state.runs_dir.iterdir()):
        events_file = directory / "events.jsonl"
        inputs_file = directory / "inputs.json"
        if not (directory.is_dir() and events_file.is_file() and inputs_file.is_file()):
            continue
        try:
            run = Run(directory.name)
            run.events = read_jsonl(events_file)
            record = RunRecord(run=run, inputs=RunInputs.model_validate_json(
                inputs_file.read_text()
            ))
            report_file = directory / "report.json"
            if report_file.is_file():
                record.report = Report.model_validate_json(report_file.read_text())
            state.runs[directory.name] = record
        except (OSError, ValueError):
            # One unreadable directory must not stop the server from starting.
            continue


def app_factory() -> FastAPI:
    """`uvicorn roia.api:app_factory --factory`."""
    return create_app()

