from __future__ import annotations

import json
import pathlib

import pytest

pytest.importorskip("fastapi")  # the web UI lives in the optional .[web] extra

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402

import agentic_ai.web.app as app_module  # noqa: E402
from agentic_ai.web import MAX_UPLOAD_BYTES, create_app  # noqa: E402
from agentic_ai.web.app import DONE_EVENT, _safe_upload_path, get_model  # noqa: E402
from tests.fakes import ScriptedChatModel  # noqa: E402
from tests.test_analyst import _REPORT  # noqa: E402


@pytest.fixture
def client(settings):
    return TestClient(create_app(settings))


def test_health_reports_the_configured_model(client, settings):
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"ok", "model", "gemini_key"}
    assert body["ok"] is True
    assert body["model"] == settings.model == "claude-sonnet-5"


def test_health_gemini_key_follows_the_environment(client, monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert client.get("/api/health").json()["gemini_key"] is False

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    assert client.get("/api/health").json()["gemini_key"] is True


def test_index_serves_html(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Grant-fit analyst" in response.text


# --- POST /api/upload -------------------------------------------------------


def _upload(client, name: str, content: bytes = b"# Project context\n"):
    return client.post("/api/upload", files={"file": (name, content, "application/octet-stream")})


def test_upload_accepts_a_markdown_file(client, settings):
    response = _upload(client, "context.md")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"run_id", "filename"}
    assert body["filename"] == "context.md"

    stored = pathlib.Path(settings.workdir) / "uploads" / body["run_id"] / "context.md"
    assert stored.read_bytes() == b"# Project context\n"


@pytest.mark.parametrize("name", [".pdf", ".docx", ".txt", ".md", ".markdown", ".rst"])
def test_upload_accepts_every_suffix_load_document_handles(client, name):
    assert _upload(client, f"doc{name}").status_code == 200


def test_upload_rejects_an_unsupported_type(client):
    response = _upload(client, "payload.exe", b"MZ\x90\x00")

    assert response.status_code == 400
    assert ".exe" in response.json()["detail"]


def test_upload_rejects_a_file_with_no_extension(client):
    assert _upload(client, "README").status_code == 400


def test_traversing_filename_lands_inside_the_run_dir(client, settings):
    uploads = pathlib.Path(settings.workdir) / "uploads"
    response = _upload(client, "../../x.md")

    assert response.status_code == 200
    run_id = response.json()["run_id"]
    assert response.json()["filename"] == "x.md"
    # the file is in the run dir, and nothing was written at either level above it
    # ('../../x.md' from <workdir>/uploads/<run_id>/ would resolve to <workdir>/x.md)
    assert (uploads / run_id / "x.md").is_file()
    assert list((uploads / run_id).iterdir()) == [uploads / run_id / "x.md"]
    assert not (pathlib.Path(settings.workdir) / "x.md").exists()
    assert not (uploads / "x.md").exists()


def test_upload_over_the_size_cap_is_rejected_and_leaves_nothing_behind(client, settings):
    uploads = pathlib.Path(settings.workdir) / "uploads"
    response = _upload(client, "huge.md", b"x" * (MAX_UPLOAD_BYTES + 1))

    assert response.status_code == 413
    # the partial write and its run folder are both gone
    assert uploads.is_dir()
    assert list(uploads.iterdir()) == []


def test_run_id_maps_to_the_stored_path_server_side(client, settings):
    body = _upload(client, "context.md").json()

    runs = client.app.state.runs
    assert body["run_id"] in runs
    assert runs[body["run_id"]].name == "context.md"
    # the browser never sees the path
    assert "workdir" not in body and str(settings.workdir) not in str(body)


# The route reduces a filename to its last component before calling the guard, so
# these cases can't arrive over HTTP - test the guard itself rather than leave the
# branches unexercised.


@pytest.mark.parametrize("name", ["..", ".", "", "../", "/"])
def test_safe_upload_path_refuses_a_nameless_filename(tmp_path, name):
    with pytest.raises(HTTPException) as excinfo:
        _safe_upload_path(tmp_path, name)

    assert excinfo.value.status_code == 400


def test_safe_upload_path_keeps_a_good_name_in_the_run_dir(tmp_path):
    assert _safe_upload_path(tmp_path, "../../ctx.md") == tmp_path / "ctx.md"


# --- GET /api/analyse (SSE) -------------------------------------------------


class _RecordingModel(ScriptedChatModel):
    """Remembers the task the agent was given, so a test can prove the query
    parameters actually reached the prompt."""

    seen: list = []

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(str(messages[-1].content) if messages else "")
        return super()._generate(messages, stop, run_manager, **kwargs)


def _analysis_model(document: pathlib.Path):
    responses = [
        AIMessage(
            content="",
            tool_calls=[{"name": "read_context", "args": {"path": str(document)}, "id": "1"}],
        ),
        AIMessage(content="Estimated match: 78%."),
    ]
    return _RecordingModel(responses=responses, structured_response=_REPORT, seen=[])


def _sse_payloads(response) -> list[dict]:
    """Parse `data: {json}` lines out of an event-stream body."""
    return [
        json.loads(line[len("data: ") :])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


@pytest.fixture
def uploaded(client, settings):
    """A run_id with a real document behind it."""
    body = _upload(client, "context.md", b"Project: next-gen battery electrolytes.").json()
    return body["run_id"], client.app.state.runs[body["run_id"]]


def test_analyse_streams_events_in_order_ending_with_report_then_done(client, uploaded):
    run_id, document = uploaded
    client.app.dependency_overrides[get_model] = lambda: _analysis_model(document)

    response = client.get(f"/api/analyse?run_id={run_id}&pi_url=http://pi")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _sse_payloads(response)
    assert [e["type"] for e in events] == [
        "tool_call",
        "tool_output",
        "token",
        "report",
        "done",
    ]
    assert response.text.endswith(DONE_EVENT)  # exact wire format of the terminator
    assert events[0]["name"] == "read_context"
    assert events[3]["report"]["grant_to_pi_match_pct"] == 78
    assert events[3]["report"]["pi"] == "Dr A. Tan"


def test_analyse_passes_the_call_and_pi_url_into_the_prompt(client, uploaded):
    run_id, document = uploaded
    model = _analysis_model(document)
    client.app.dependency_overrides[get_model] = lambda: model

    client.get(f"/api/analyse?run_id={run_id}&pi_url=http://pi/x&call=NRF+CRP")

    task = model.seen[0]
    assert "http://pi/x" in task
    assert "NRF CRP" in task


def test_analyse_404s_on_an_unknown_run_id(client):
    response = client.get("/api/analyse?run_id=nope&pi_url=http://pi")

    assert response.status_code == 404
    assert "nope" in response.json()["detail"]


def test_analyse_turns_a_generator_blow_up_into_an_error_event(client, uploaded, monkeypatch):
    run_id, _ = uploaded

    def boom(*args, **kwargs):
        raise RuntimeError("agent exploded")
        yield  # pragma: no cover - never reached, makes this a generator

    monkeypatch.setattr(app_module, "stream_analysis", boom)

    response = client.get(f"/api/analyse?run_id={run_id}&pi_url=http://pi")

    assert response.status_code == 200  # headers were already sent; not a 500
    events = _sse_payloads(response)
    assert [e["type"] for e in events] == ["error", "done"]
    assert "agent exploded" in events[0]["text"]
