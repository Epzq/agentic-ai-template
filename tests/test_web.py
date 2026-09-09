from __future__ import annotations

import pytest

pytest.importorskip("fastapi")  # the web UI lives in the optional .[web] extra

from fastapi.testclient import TestClient  # noqa: E402

from agentic_ai.web import create_app  # noqa: E402


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
