from __future__ import annotations

import pathlib

import pytest

pytest.importorskip("fastapi")  # the web UI lives in the optional .[web] extra

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from agentic_ai.web import MAX_UPLOAD_BYTES, create_app  # noqa: E402
from agentic_ai.web.app import _safe_upload_path  # noqa: E402


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
