"""WI-2.4a — serving the built frontend at the same origin.

These are hermetic: they build a fake `dist/` on disk rather than running Vite, because what
is being tested is the routing rule, not the bundler.

The rule that matters: **`/runs/{id}` is a client-side route.** There is no such file, so a
deep-linked reload has to be handed `index.html` for React Router to resolve — and that is
half of AC8b. The other half is that this must not swallow `/api`.
"""

from __future__ import annotations

import pathlib

import pytest
from fastapi.testclient import TestClient

import roia.api as api
from roia.api import create_app
from roia.config import Settings


@pytest.fixture
def dist(tmp_path) -> pathlib.Path:
    """A stand-in for what `npm run build` writes."""
    built = tmp_path / "frontend" / "dist"
    (built / "assets").mkdir(parents=True)
    (built / "index.html").write_text("<!doctype html><title>ROIA</title><div id=root></div>")
    (built / "assets" / "index-abc123.js").write_text("console.log('bundle')")
    return built


@pytest.fixture
def served(dist, tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setattr(api, "FRONTEND_DIST", dist)
    app = create_app(Settings(_env_file=None), runs_dir=tmp_path / "runs")
    with TestClient(app) as client:
        yield client


def test_the_api_boots_with_no_build_on_disk(tmp_path, monkeypatch) -> None:
    """The normal development state, and the one that must never break: nobody has run
    `npm run build` yet, Vite owns the UI on :5173, and the API still has to come up."""
    monkeypatch.setattr(api, "FRONTEND_DIST", tmp_path / "does-not-exist")
    app = create_app(Settings(_env_file=None), runs_dir=tmp_path / "runs")

    with TestClient(app) as client:
        assert client.get("/api/runs/nope").status_code == 404
        assert client.get("/").status_code == 404, "nothing to serve, and it says so"


def test_the_index_is_served_at_the_root(served) -> None:
    response = served.get("/")

    assert response.status_code == 200
    assert "<div id=root>" in response.text


def test_a_client_route_is_handed_the_index_so_a_deep_link_reloads(served) -> None:
    """AC8b's server half. `/runs/{id}` is not a file; without this a refresh mid-run 404s
    and the run is lost, which is precisely what AC8b says must not happen."""
    response = served.get("/runs/run-001-1b51a29207db")

    assert response.status_code == 200
    assert "<div id=root>" in response.text


def test_a_real_asset_is_served_as_itself_not_as_the_index(served) -> None:
    response = served.get("/assets/index-abc123.js")

    assert response.status_code == 200
    assert response.text == "console.log('bundle')"


def test_an_unknown_api_path_is_still_a_404(served) -> None:
    """The catch-all must not swallow the API. A client that mistypes an endpoint has to
    see a 404, not a 200 full of HTML it will then fail to parse as JSON."""
    response = served.get("/api/does-not-exist")

    assert response.status_code == 404
    assert "<div id=root>" not in response.text


def test_the_api_still_answers_with_the_catch_all_mounted(served) -> None:
    """Registration order is load-bearing: the SPA route is added last, after every /api
    route, so it can never shadow one."""
    snapshot = served.get("/api/runs/anything?fixture=run-001")

    assert snapshot.status_code == 200
    assert snapshot.json()["status"] == "finished"


def test_a_traversing_path_cannot_escape_the_build_directory(served, tmp_path) -> None:
    """`/{spa_path:path}` is user input joined onto a filesystem path.

    ⚠️ **The traversal must be percent-encoded.** A literal `GET /../secret.txt` never tests
    anything: httpx resolves dot segments client-side, so the server only ever sees
    `/secret.txt` and the assertion passes with the guard deleted. `%2e%2e` survives the
    client and is decoded by Starlette *after* routing, which is the case that reaches the
    handler — verified by removing `target.is_relative_to(root)` and watching this fail.
    """
    (tmp_path / "secret.txt").write_text("not for the browser")

    escapes = (
        "%2e%2e/secret.txt",
        "%2e%2e/%2e%2e/secret.txt",
        "assets/%2e%2e/%2e%2e/secret.txt",
    )
    for path in escapes:
        response = served.get(f"/{path}")
        assert "not for the browser" not in response.text, path
        # It falls through to the SPA, which is the right answer for an unknown path.
        assert "<div id=root>" in response.text, path
