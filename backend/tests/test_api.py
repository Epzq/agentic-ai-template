"""WI-2.1 — the HTTP contract (`demo-spec.md` §6.2).

The pipeline is monkeypatched to the replayed one from `tests/test_pipeline.py`, so a run
started over HTTP does the same work it does in production without touching the network.
"""

from __future__ import annotations

import io
import pathlib
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from roia.api import MAX_UPLOAD_BYTES, create_app
from roia.config import Settings
from roia.events import read_jsonl
from tests.test_assessment import CRP, PROFILE
from tests.test_pipeline import ScriptedGemini, transport

F = pathlib.Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
def replayed(monkeypatch):
    """Every external call replayed, for both the probe and the run."""
    import roia.api as api

    client = httpx.Client(transport=httpx.MockTransport(transport))
    real_pipeline = api.run_pipeline
    real_probe = api.probe

    monkeypatch.setattr(
        api, "run_pipeline",
        lambda inputs, run, **kw: real_pipeline(
            inputs, run, http=client, gemini=ScriptedGemini(), min_interval_s=0, **kw
        ),
    )
    monkeypatch.setattr(
        api, "probe",
        lambda grant, profile, store, **kw: real_probe(
            grant, profile, store, client=client, min_interval_s=0, **kw
        ),
    )
    return client


@pytest.fixture
def client(tmp_path, replayed) -> TestClient:
    app = create_app(Settings(_env_file=None, dev=True), runs_dir=tmp_path / "runs")
    with TestClient(app) as test_client:
        yield test_client


def finished(client: TestClient, run_id: str, timeout: float = 240) -> dict:
    """Poll the snapshot until the run stops running — what the curl recipe does by hand."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = client.get(f"/api/runs/{run_id}").json()
        if snapshot["status"] == "failed":
            record = client.app.state.roia.runs[run_id]
            raise AssertionError(f"{run_id} failed: {record.error or 'see run.failed event'}")
        if snapshot["status"] != "running":
            return snapshot
        time.sleep(0.05)
    raise AssertionError(f"{run_id} still running after {timeout}s")


# --- POST /api/runs -----------------------------------------------------------------------

def test_posting_a_run_returns_an_id_and_the_run_completes(client) -> None:
    created = client.post("/api/runs", json={"grant_url": CRP, "profile_url": PROFILE})

    assert created.status_code == 201
    run_id = created.json()["run_id"]

    snapshot = finished(client, run_id)
    assert snapshot["status"] == "finished"
    assert len(snapshot["events"]) >= 15, "AC7"
    assert snapshot["report"] is not None
    assert len(snapshot["report"]["directions"]) == 3


def test_422_when_neither_grant_source_is_present(client) -> None:
    """§6.2: either a URL or an upload, and the API says so rather than guessing."""
    response = client.post("/api/runs", json={"profile_url": PROFILE})

    assert response.status_code == 422
    assert "grant_url" in response.text


def test_422_on_probe_without_a_grant_source(client) -> None:
    assert client.post("/api/probe", json={"profile_url": PROFILE}).status_code == 422


def test_the_snapshot_carries_status_warnings_events_and_the_report(client) -> None:
    """WI-2.5 has no other source for the report."""
    run_id = client.post(
        "/api/runs", json={"grant_url": CRP, "profile_url": PROFILE}
    ).json()["run_id"]

    snapshot = finished(client, run_id)

    assert set(snapshot) == {"run_id", "status", "inputs", "warnings", "events", "report"}
    assert all(w["type"] == "warning" for w in snapshot["warnings"])
    assert snapshot["inputs"]["grant_src"] == CRP
    report = snapshot["report"]
    assert report["evidence"] and report["weights"]
    assert all(len(d["evidence_ids"]) >= 2 for d in report["directions"]), "AC3"


def test_two_runs_from_one_probe_do_not_share_an_evidence_store(client) -> None:
    """The probe caches its ingestion so a run does not re-fetch seven PDFs. It used to
    cache the `EvidenceStore` **object**, and hand the same one to every run quoting that
    `probe_id` — so pressing Analyse twice made run 2 open holding run 1's rows, mint on
    top, and publish a report listing (and able to cite) another run's evidence."""
    probe = client.post(
        "/api/probe", json={"grant_url": CRP, "profile_url": PROFILE}
    ).json()

    reports = []
    for _ in range(2):
        run_id = client.post("/api/runs", json={
            "grant_url": CRP, "profile_url": PROFILE, "probe_id": probe["probe_id"],
        }).json()["run_id"]
        reports.append(finished(client, run_id)["report"])

    first, second = (len(r["evidence"]) for r in reports)
    assert first == second, (
        f"the second run holds {second} rows against the first run's {first} — "
        "the probe's store is being shared and mutated"
    )
    ids = [{row["id"] for row in r["evidence"]} for r in reports]
    assert ids[0] == ids[1], "both runs must number their own evidence identically"


def test_a_probe_id_from_different_inputs_is_refused(client) -> None:
    """`probe_id` decides which documents the run actually analyses. Accepting one minted
    for other inputs means the run reads grant A while its inputs, its report header and
    its archived events all say grant B."""
    probe = client.post(
        "/api/probe", json={"grant_url": CRP, "profile_url": PROFILE}
    ).json()

    response = client.post("/api/runs", json={
        "grant_url": CRP,
        "profile_url": "https://example.edu/someone-else",
        "probe_id": probe["probe_id"],
    })

    assert response.status_code == 422, response.status_code
    assert "different inputs" in response.text


def test_an_unknown_run_is_a_404(client) -> None:
    assert client.get("/api/runs/run-nope").status_code == 404


# --- GET /api/runs/{id}/report.md ------------------------------------------------------------

def test_the_report_is_downloadable_as_markdown(client) -> None:
    """§6.2 lists this endpoint. It was written into the CLI and never onto the app, so the
    one artefact a reviewer forwards to a colleague could not be got out of the server."""
    run_id = client.post(
        "/api/runs", json={"grant_url": CRP, "profile_url": PROFILE}
    ).json()["run_id"]
    finished(client, run_id)

    response = client.get(f"/api/runs/{run_id}/report.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    body = response.text
    assert body.startswith("#"), "markdown, not JSON"
    snapshot = client.get(f"/api/runs/{run_id}").json()
    for direction in snapshot["report"]["directions"]:
        assert direction["title"] in body


def test_markdown_carries_no_link_that_is_not_in_the_evidence_store(client) -> None:
    """AC13 through the new route as well: the renderer resolves ids against the report's
    own evidence, so a URL can only be in the markdown if Python minted the row."""
    import re

    run_id = client.post(
        "/api/runs", json={"grant_url": CRP, "profile_url": PROFILE}
    ).json()["run_id"]
    snapshot = finished(client, run_id)

    body = client.get(f"/api/runs/{run_id}/report.md").text

    minted = {row["url"] for row in snapshot["report"]["evidence"] if row["url"]}
    linked = set(re.findall(r"\]\((https?://[^)]+)\)", body))
    assert linked <= minted, f"markdown links nothing minted: {linked - minted}"


def test_markdown_carries_the_same_warnings_the_snapshot_does(client) -> None:
    """The browser reads warnings from the snapshot and shows them at the top; the markdown
    is the copy that leaves the building. If the two ever disagree, the exported file is
    quietly the more confident of the pair — which is backwards."""
    run_id = client.post(
        "/api/runs", json={"grant_url": CRP, "profile_url": PROFILE}
    ).json()["run_id"]
    snapshot = finished(client, run_id)

    body = client.get(f"/api/runs/{run_id}/report.md").text

    warnings = snapshot["warnings"]
    if not warnings:
        assert "unsure about" not in body
        return
    assert "## ⚠️ What this run is unsure about" in body
    for warning in warnings:
        assert warning["code"] in body, f"{warning['code']} is in the snapshot, not the file"


def test_markdown_for_a_run_with_no_report_yet_is_409_not_404(client) -> None:
    """The run exists and the URL is right; there is just nothing to render. A client that
    cannot tell that from "no such run" retries the wrong one."""
    run_id = client.post(
        "/api/runs", json={"grant_url": CRP, "profile_url": PROFILE}
    ).json()["run_id"]

    early = client.get(f"/api/runs/{run_id}/report.md")

    assert early.status_code in (200, 409), early.status_code
    finished(client, run_id)
    assert client.get(f"/api/runs/{run_id}/report.md").status_code == 200


def test_markdown_for_an_unknown_run_is_a_404(client) -> None:
    assert client.get("/api/runs/run-nope/report.md").status_code == 404


def test_markdown_renders_a_replay_fixture_too(client) -> None:
    """`?fixture=` works on the other two run routes; a demo-day fallback that can show the
    report but not export it would be a strange half-measure."""
    response = client.get("/api/runs/run-001/report.md?fixture=run-001")

    assert response.status_code == 200
    assert response.text.startswith("#")


def test_the_snapshot_is_available_while_the_run_is_still_going(client) -> None:
    """The UI polls this from the moment it navigates; it cannot wait for the report."""
    run_id = client.post(
        "/api/runs", json={"grant_url": CRP, "profile_url": PROFILE}
    ).json()["run_id"]

    early = client.get(f"/api/runs/{run_id}").json()

    assert early["status"] in ("running", "finished")
    assert early["report"] is None or early["status"] == "finished"
    finished(client, run_id)


# --- POST /api/probe ------------------------------------------------------------------------

def test_the_probe_returns_questions_without_any_document_text(client) -> None:
    """`grant`/`profile` are `Field(exclude=True)`, so ~100k chars never reach the browser."""
    response = client.post("/api/probe", json={"grant_url": CRP, "profile_url": PROFILE})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"probe_id", "detected", "questions", "warnings"}
    assert len(body["detected"]["call_periods"]) == 2, "AC14"
    assert len(response.content) < 20_000, "the document text must not be serialised"


def test_the_probe_is_cached_by_input_hash(client, monkeypatch) -> None:
    """Pressing Analyse twice must not re-fetch seven PDFs."""
    import roia.api as api

    calls: list[str] = []
    inner = api.probe
    monkeypatch.setattr(api, "probe", lambda *a, **k: (calls.append(a[0]), inner(*a, **k))[1])

    first = client.post("/api/probe", json={"grant_url": CRP, "profile_url": PROFILE}).json()
    second = client.post("/api/probe", json={"grant_url": CRP, "profile_url": PROFILE}).json()

    assert first["probe_id"] == second["probe_id"]
    assert len(calls) == 1, "the second Analyse hit the cache"


def test_a_run_reuses_the_probes_ingestion_and_its_store(client) -> None:
    """The probe already minted the call's pages; re-ingesting doubles the evidence."""
    probe_id = client.post(
        "/api/probe", json={"grant_url": CRP, "profile_url": PROFILE}
    ).json()["probe_id"]

    run_id = client.post("/api/runs", json={
        "grant_url": CRP, "profile_url": PROFILE, "probe_id": probe_id,
    }).json()["run_id"]

    snapshot = finished(client, run_id)
    pages = [e for e in snapshot["report"]["evidence"] if e["source_type"] == "grant_doc"]
    assert len(pages) == 21, "the call's 21 pages, minted once"
    first_tool = next(e for e in snapshot["events"] if e["type"] == "tool.started")
    assert first_tool["tool"] == "reuse_probe_documents"


def test_an_answer_given_at_run_time_reaches_the_pipeline(client) -> None:
    probe_body = client.post(
        "/api/probe", json={"grant_url": CRP, "profile_url": PROFILE}
    ).json()
    question = next(q for q in probe_body["questions"] if q["code"] == "multiple_call_periods")
    frontier = next(o for o in question["options"] if "Frontier" in o["label"])

    run_id = client.post("/api/runs", json={
        "grant_url": CRP, "profile_url": PROFILE, "probe_id": probe_body["probe_id"],
        "answers": {"multiple_call_periods": frontier["value"]},
    }).json()["run_id"]

    snapshot = finished(client, run_id)
    # §6.3 specifies run.started {inputs}, so the payload nests under that key.
    started = next(e for e in snapshot["events"] if e["type"] == "run.started")
    assert started["inputs"]["answers"] == {"multiple_call_periods": frontier["value"]}


# --- persistence ------------------------------------------------------------------------------

def test_a_finished_run_is_written_to_disk(client, tmp_path) -> None:
    run_id = client.post(
        "/api/runs", json={"grant_url": CRP, "profile_url": PROFILE}
    ).json()["run_id"]
    finished(client, run_id)

    directory = tmp_path / "runs" / run_id
    assert (directory / "report.json").is_file()
    assert (directory / "inputs.json").is_file()
    assert len(read_jsonl(directory / "events.jsonl")) >= 15


def test_a_restart_does_not_lose_a_finished_run(client, tmp_path, replayed) -> None:
    """The Done line. A server restart mid-demo must not throw away the report."""
    run_id = client.post(
        "/api/runs", json={"grant_url": CRP, "profile_url": PROFILE}
    ).json()["run_id"]
    before = finished(client, run_id)

    restarted = create_app(Settings(_env_file=None), runs_dir=tmp_path / "runs")
    with TestClient(restarted) as fresh:
        after = fresh.get(f"/api/runs/{run_id}").json()

    assert after["status"] == "finished"
    assert after["report"]["directions"] == before["report"]["directions"]
    assert len(after["events"]) == len(before["events"])


def test_an_unreadable_run_directory_does_not_stop_the_server_starting(tmp_path) -> None:
    broken = tmp_path / "runs" / "run-broken"
    broken.mkdir(parents=True)
    (broken / "events.jsonl").write_text("not json\n")
    (broken / "inputs.json").write_text("{}")

    app = create_app(Settings(_env_file=None), runs_dir=tmp_path / "runs")
    with TestClient(app) as fresh:
        assert fresh.get("/api/runs/run-broken").status_code == 404


# --- uploads (PLUS) ----------------------------------------------------------------------------

def test_an_uploaded_pdf_can_be_used_as_the_grant_source(client) -> None:
    pdf = (F / "grant.pdf").read_bytes()

    created = client.post(
        "/api/uploads",
        files={"file": ("call.pdf", io.BytesIO(pdf), "application/pdf")},
    )

    assert created.status_code == 200
    body = created.json()
    assert len(body["sha256"]) == 64

    run_id = client.post("/api/runs", json={
        "grant_upload_id": body["upload_id"], "profile_url": PROFILE,
    }).json()["run_id"]
    snapshot = finished(client, run_id)
    assert snapshot["status"] == "finished"
    pages = [e for e in snapshot["report"]["evidence"] if e["source_type"] == "grant_doc"]
    assert len(pages) == 21


def test_a_non_pdf_upload_is_refused_by_its_bytes_not_its_name(client) -> None:
    """The same rule ingestion uses: content, never the filename."""
    response = client.post(
        "/api/uploads",
        files={"file": ("call.pdf", io.BytesIO(b"<html>not a pdf</html>"), "application/pdf")},
    )

    assert response.status_code == 415


def test_an_oversized_upload_is_refused_at_the_door(client) -> None:
    """Better than discovering it four minutes into a run."""
    body = b"%PDF" + b"\0" * MAX_UPLOAD_BYTES

    response = client.post("/api/uploads", files={"file": ("big.pdf", io.BytesIO(body))})

    assert response.status_code == 413


def test_an_unknown_upload_id_is_a_404(client) -> None:
    response = client.post(
        "/api/runs", json={"grant_upload_id": "nope", "profile_url": PROFILE}
    )

    assert response.status_code == 404


# --- CORS and state ------------------------------------------------------------------------------

def test_cors_is_open_for_the_vite_dev_server_only_when_dev_is_set(tmp_path, replayed) -> None:
    headers = {"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"}

    with TestClient(create_app(Settings(_env_file=None, dev=True), runs_dir=tmp_path / "a")) as dev:
        assert dev.options("/api/runs", headers=headers).headers.get(
            "access-control-allow-origin"
        ) == "http://localhost:5173"

    prod_app = create_app(Settings(_env_file=None, dev=False), runs_dir=tmp_path / "b")
    with TestClient(prod_app) as prod:
        response = prod.options("/api/runs", headers=headers)
        assert "access-control-allow-origin" not in response.headers


def test_two_apps_do_not_share_runs(tmp_path, replayed) -> None:
    """`no module-level mutable state` — a leak here would be invisible until it mattered."""
    first = create_app(Settings(_env_file=None), runs_dir=tmp_path / "one")
    second = create_app(Settings(_env_file=None), runs_dir=tmp_path / "two")

    with TestClient(first) as a, TestClient(second) as b:
        started = a.post("/api/runs", json={"grant_url": CRP, "profile_url": PROFILE})
        run_id = started.json()["run_id"]
        assert b.get(f"/api/runs/{run_id}").status_code == 404
        finished(a, run_id)


def test_the_pipeline_runs_off_the_event_loop(client) -> None:
    """`run_pipeline` blocks for minutes. On the loop it would stall the event stream that
    is the entire point of watching a run."""
    import inspect

    import roia.api as api

    source = inspect.getsource(api._execute)
    assert "asyncio.to_thread" in source
    assert "run_pipeline" in source


def test_status_never_says_finished_before_the_report_is_attached() -> None:
    """`run_pipeline` emits run.finished from inside the worker thread, *before* it returns.

    Deriving status from that event alone leaves a window where the snapshot claims to be
    finished with no report — and the UI navigates to a page that has nothing on it. This
    was a real intermittent failure before the task, rather than the event, became the
    authority on whether a run is done.
    """
    import asyncio

    from roia.api import RunRecord
    from roia.events import Run
    from roia.pipeline import RunInputs

    run = Run("run-x")
    run.finished()  # the pipeline said so from inside the thread
    inputs = RunInputs(grant_src="u", profile_url="p")

    async def check() -> None:
        pending: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        task = asyncio.ensure_future(pending)
        record = RunRecord(run=run, inputs=inputs, task=task)
        assert record.status == "running", "the report is not attached until the task returns"

        pending.set_result(None)
        await asyncio.sleep(0)
        assert record.status == "finished"

    asyncio.run(check())

    # A rehydrated run has no task and finished before this process started.
    assert RunRecord(run=run, inputs=inputs, task=None).status == "finished"


# --- WI-2.6: a probe the server no longer holds ---------------------------------------------

def test_a_run_naming_an_unknown_probe_is_refused(client) -> None:
    """🔴 Starting anyway would silently drop the applicant's answers.

    `run_pipeline` only reaches `resolve_answers` when a probe is in hand, so a run given a
    `probe_id` the server has forgotten would brief LLM #1 on the whole programme instead of
    the call period the applicant chose — a four-minute run against the wrong deadline, with
    nothing logged. Restarting the server with a tab open is all it takes to get here.
    """
    response = client.post(
        "/api/runs",
        json={
            "grant_url": CRP,
            "profile_url": PROFILE,
            "probe_id": "pb_forgotten123",
            "answers": {"multiple_call_periods": "call_1"},
        },
    )

    assert response.status_code == 404
    assert "Analyse again" in response.json()["detail"]
    assert client.app.state.roia.runs == {}, "nothing was started"


def test_answers_without_a_probe_are_refused_rather_than_dropped(client) -> None:
    """Same hole, reached without a `probe_id` at all: the answers have nothing to resolve
    against, so `answers_brief` would be empty and the choice would vanish."""
    response = client.post(
        "/api/runs",
        json={"grant_url": CRP, "profile_url": PROFILE, "answers": {"x": "y"}},
    )

    assert response.status_code == 422
    assert client.app.state.roia.runs == {}


def test_a_run_with_no_probe_and_no_answers_still_starts(client) -> None:
    """The direct path stays open — a run that was never probed has nothing to lose."""
    created = client.post("/api/runs", json={"grant_url": CRP, "profile_url": PROFILE})

    assert created.status_code == 201
    finished(client, created.json()["run_id"])
