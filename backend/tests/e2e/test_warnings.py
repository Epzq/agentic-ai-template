"""WI-2.6 — warnings in the browser (AC9).

`test_ac9_an_unreachable_profile_still_produces_a_finished_run` in `tests/test_pipeline.py`
already proves the *pipeline* survives a dead profile. What it cannot show is the half AC9
is actually about — that the person looking at the screen is **told**. This drives the whole
stack in a browser: form, probe, run, event stream, warnings, report.

Everything external is replayed, so a full run takes about a second and costs nothing.
"""

from __future__ import annotations

import threading
import time

import httpx
import pytest
import uvicorn
from playwright.sync_api import Page, expect

import roia.api as api
from roia.api import create_app
from roia.config import Settings
from tests.conftest import free_port
from tests.test_assessment import CRP
from tests.test_pipeline import ScriptedGemini, transport

pytestmark = pytest.mark.e2e

#: A profile URL that resolves to nothing. The grant half of the run is untouched, which is
#: what makes this graceful degradation rather than a total failure.
DEAD_PROFILE = "https://basurafernando.github.io/"


@pytest.fixture
def broken_profile_ui(built_frontend, tmp_path, monkeypatch):
    """A real server whose profile fetches 404 and whose model calls are scripted."""
    def half_broken(request: httpx.Request) -> httpx.Response:
        if request.url.host == "basurafernando.github.io":
            return httpx.Response(404)
        return transport(request)

    client = httpx.Client(transport=httpx.MockTransport(half_broken))
    real_pipeline, real_probe = api.run_pipeline, api.probe
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

    app = create_app(Settings(_env_file=None, dev=False), runs_dir=tmp_path / "runs")
    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        assert time.monotonic() < deadline, "uvicorn did not start"
        time.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_ac9_a_broken_profile_url_completes_with_a_visible_warning(
    broken_profile_ui: str, page: Page
) -> None:
    """`If the profile URL is unreachable, the run completes with a visible warning rather
    than crashing.` Driven end to end — nothing is stubbed at the browser.

    The dead profile surfaces on the **probe**, not on the run, and that is correct: a run
    given a `probe_id` reuses the probe's ingestion rather than fetching everything twice
    (WI-2.1). It also means the applicant is told before a minute of work is spent, which is
    better than the AC asks for. `tests/test_pipeline.py` covers the other path — a run with
    no probe, which does its own fetching and warns `fetch_failed` itself.
    """
    page.goto(broken_profile_ui)
    page.get_by_test_id("grant-url-input").fill(CRP)
    page.get_by_test_id("profile-url-input").fill(DEAD_PROFILE)
    page.get_by_test_id("analyse-button").click()

    expect(page.get_by_test_id("clarify-panel")).to_be_visible(timeout=60000)
    warned = page.get_by_test_id("probe-warning")
    expect(warned.first).to_be_visible()
    assert any(
        DEAD_PROFILE in text for text in warned.all_text_contents()
    ), f"nothing named the dead profile: {warned.all_text_contents()}"
    # The detector fired too: an empty profile is a question, not a silent assumption.
    expect(page.get_by_test_id("probe-question-thin_profile")).to_be_visible()

    page.get_by_test_id("start-run-button").click()
    page.wait_for_url("**/runs/**", timeout=30000)

    expect(page.get_by_test_id("run-status")).to_have_text("finished", timeout=120000)
    expect(page.get_by_test_id("run-error")).to_have_count(0)
    expect(page.get_by_test_id("run-warning").first).to_be_visible()


def test_ac9_the_run_finishes_and_keeps_its_timeline(broken_profile_ui: str, page: Page) -> None:
    """`completes` is the load-bearing word — a warning on a blank page is a crash with
    better manners.

    Deliberately **not** asserting that a report appears: with no profile there is nothing to
    match the call against, and how much a real model salvages from that is not something a
    scripted fixture can honestly stand in for. What must hold is that the run reaches
    `finished`, keeps its activity log, and says why.
    """
    page.goto(broken_profile_ui)
    page.get_by_test_id("grant-url-input").fill(CRP)
    page.get_by_test_id("profile-url-input").fill(DEAD_PROFILE)
    page.get_by_test_id("analyse-button").click()
    expect(page.get_by_test_id("clarify-panel")).to_be_visible(timeout=60000)
    page.get_by_test_id("start-run-button").click()
    page.wait_for_url("**/runs/**", timeout=30000)
    expect(page.get_by_test_id("run-status")).to_have_text("finished", timeout=120000)

    expect(page.get_by_test_id("timeline")).to_be_visible()
    assert page.get_by_test_id("timeline-event").count() >= 15, "AC7 still holds"
    assert page.get_by_test_id("run-warning").count() >= 1


# --- dismissible ------------------------------------------------------------------------------

FIXTURE = "run-001"


def replayed(ui: str) -> str:
    return f"{ui}/runs/{FIXTURE}?fixture={FIXTURE}&speed=1000"


def test_a_warning_can_be_dismissed_and_brought_back(ui: str, page: Page) -> None:
    """Dismissed, never deleted.

    A warning is the honest half of the report — "the profile page yielded 412 characters",
    "only 3 papers came back". A run that could hide them for good would be claiming more
    than it retrieved, so dismissal is per-view and reversible.
    """
    page.goto(replayed(ui))
    expect(page.get_by_test_id("event-count")).to_have_text("162 events", timeout=30000)
    expect(page.get_by_test_id("run-warning")).to_have_count(4)

    page.get_by_test_id("dismiss-warning").first.click()

    expect(page.get_by_test_id("run-warning")).to_have_count(3)
    expect(page.get_by_test_id("restore-warnings")).to_contain_text("1 dismissed warning")

    page.get_by_test_id("restore-warnings").click()

    expect(page.get_by_test_id("run-warning")).to_have_count(4)
    expect(page.get_by_test_id("restore-warnings")).to_have_count(0)


def test_dismissing_one_warning_leaves_its_twin(ui: str, page: Page) -> None:
    """Keyed by `seq`, not by `code`. The recorded run carries **two** `thin_literature`
    warnings; keying on the code would collapse them and dismiss both at once."""
    page.goto(replayed(ui))
    expect(page.get_by_test_id("event-count")).to_have_text("162 events", timeout=30000)
    thin = page.locator('[data-testid=run-warning][data-code=thin_literature]')
    assert thin.count() == 2

    thin.first.get_by_test_id("dismiss-warning").click()

    expect(page.locator('[data-testid=run-warning][data-code=thin_literature]')).to_have_count(1)
