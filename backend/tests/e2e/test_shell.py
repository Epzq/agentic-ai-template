"""WI-2.4a — the React shell, in a real browser.

The AC8b test drives the **replayer** (`?fixture=run-001`), so it needs no API keys, no
network and no five-minute run — which is exactly what WI-2.3 was built for.

The form tests intercept `/api/probe` and `/api/runs` at the browser. What is under test
there is the *frontend's* two-step logic — which answers it sends, and when it refuses to
start a run at all. The backend's own probe is already covered by `tests/test_api.py`, and
running it here would add ten seconds of network to every assertion.
"""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

FIXTURE = "run-001"

#: What `POST /api/probe` answers for the CRP call, trimmed to the fields the UI reads.
PROBE_BODY = {
    "probe_id": "pb_1b51a29207db",
    # Mirrors backend/roia/ingest.py's build_questions: `detected` carries LABEL lists and
    # counts, never option objects. A stub of a shape the server does not send is a trap for
    # whoever renders it next.
    "detected": {
        "call_periods": ["Frontier CRP — 23 Mar", "CRP36 — 14 Sep"],
        "schemes": ["F-CRP", "T-CRP"],
        "profile_chars": 412,
        "eligibility_found": False,
        "grant_evidence": 21,
        "profile_evidence": 2,
    },
    "questions": [
        {
            "code": "multiple_call_periods",
            "question": "This page describes 2 call periods. Which one are you applying to?",
            "options": [
                {"value": "call_1", "label": "Frontier CRP — 23 Mar", "evidence_ids": ["e3"]},
                {"value": "call_2", "label": "CRP36 — 14 Sep", "evidence_ids": ["e4"]},
                {"value": "all_calls", "label": "Analyse the whole programme", "evidence_ids": []},
            ],
            "default": "all_calls",
        },
        {
            "code": "thin_profile",
            "question": "That profile page is thin. Do you have a fuller one?",
            "options": [
                {"value": "continue", "label": "Carry on with this page", "evidence_ids": []},
                {"value": "use_different_url", "label": "Different URL", "evidence_ids": []},
            ],
            "default": "continue",
        },
        {
            "code": "no_eligibility_found",
            "question": "No document mentions eligibility. Upload the call PDF?",
            "options": [
                {"value": "continue", "label": "Carry on without it", "evidence_ids": []},
                {"value": "upload_document", "label": "Upload it", "evidence_ids": []},
            ],
            "default": "continue",
        },
    ],
    "warnings": [{"code": "thin_profile", "message": "The profile page yielded 412 characters."}],
}


def fill_the_form(page: Page) -> None:
    page.get_by_test_id("grant-url-input").fill("https://www.rgp.gov.sg/nrf-ar/crp")
    page.get_by_test_id("profile-url-input").fill("https://basurafernando.github.io/")


def stub_probe(page: Page) -> None:
    page.route(
        "**/api/probe",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(PROBE_BODY)
        ),
    )


def capture_runs(page: Page, status: int = 201, body: object | None = None) -> list[dict]:
    """Intercept `POST /api/runs` and record what the browser tried to send."""
    posted: list[dict] = []

    def handler(route) -> None:
        posted.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(
            status=status,
            content_type="application/json",
            body=json.dumps(body if body is not None else {"run_id": "run-007-abc"}),
        )

    page.route("**/api/runs", handler)
    return posted


# --- AC8b -----------------------------------------------------------------------------------

def test_ac8b_a_deep_linked_run_survives_a_browser_refresh(ui: str, page: Page) -> None:
    """The Done line. The run id is in the URL, so a refresh comes back to the same run and
    re-reads the snapshot rather than starting over.

    It also proves the server half: `/runs/{id}` is not a file, so the reload only works
    because FastAPI hands the SPA `index.html` for unknown non-API paths.
    """
    page.goto(f"{ui}/runs/{FIXTURE}?fixture={FIXTURE}&speed=200")

    expect(page.get_by_test_id("run-status")).to_have_text("finished")
    expect(page.get_by_test_id("event-count")).to_have_text("162 events")
    # Since WI-2.5 the report is the real view; three cards is what "the report survived" means.
    expect(page.get_by_test_id("direction-card")).to_have_count(3)
    before = page.get_by_test_id("run-id").text_content()

    page.reload()

    expect(page.get_by_test_id("run-status")).to_have_text("finished")
    expect(page.get_by_test_id("event-count")).to_have_text("162 events")
    assert page.get_by_test_id("run-id").text_content() == before
    assert "?fixture=" in page.url, "the replay parameters survive the reload too"


def test_the_recorded_runs_warnings_reach_the_page(ui: str, page: Page) -> None:
    """The replay carries four real warnings from the recorded run — WI-2.6 styles them,
    but they have to arrive here first.

    Since WI-2.4b the warnings come off the **event stream**, not the snapshot, so they
    appear on the recorded run's own schedule rather than all at once. Wait for the replay
    to finish before counting them.
    """
    page.goto(f"{ui}/runs/{FIXTURE}?fixture={FIXTURE}&speed=200")
    expect(page.get_by_test_id("event-count")).to_have_text("162 events", timeout=30000)

    expect(page.get_by_test_id("run-warning").first).to_be_visible()
    assert page.get_by_test_id("run-warning").count() == 4, (
        "the recorded run carries exactly four: quote_unverified, thin_literature x2, "
        "compressed_scores — a >= assertion would pass if three of them were dropped"
    )


def test_an_unknown_run_reports_the_error_rather_than_a_blank_page(ui: str, page: Page) -> None:
    page.goto(f"{ui}/runs/no-such-run")

    expect(page.get_by_test_id("run-error")).to_contain_text("no run")


# --- AC14: the two-step submit ----------------------------------------------------------------

def test_ac14_analyse_shows_the_questions_with_defaults_preselected(
    ui: str, page: Page
) -> None:
    stub_probe(page)
    page.goto(ui)
    fill_the_form(page)

    page.get_by_test_id("analyse-button").click()

    expect(page.get_by_test_id("clarify-panel")).to_be_visible()
    expect(page.get_by_test_id("probe-question-multiple_call_periods")).to_be_visible()
    expect(page.get_by_test_id("probe-option-multiple_call_periods-all_calls")).to_be_checked()
    expect(page.get_by_test_id("probe-option-thin_profile-continue")).to_be_checked()
    expect(page.get_by_test_id("probe-option-no_eligibility_found-continue")).to_be_checked()
    expect(page.get_by_test_id("probe-option-multiple_call_periods-call_1")).not_to_be_checked()


def test_ac14_an_untouched_question_is_left_for_the_server_to_default(ui: str, page: Page) -> None:
    """A pre-selected default is not a choice, and the backend draws that distinction.

    `resolve_answers` sets `answered=True` when the posted value matches, and `answers_brief`
    then drops its "(not answered; default applied)" qualifier — so echoing the pre-selected
    default back would tell LLM #1 the applicant *chose* "analyse the whole programme" when
    they never touched it. Untouched questions are omitted so the server applies its own
    default and records it honestly.
    """
    stub_probe(page)
    posted = capture_runs(page)
    page.goto(ui)
    fill_the_form(page)
    page.get_by_test_id("analyse-button").click()
    expect(page.get_by_test_id("clarify-panel")).to_be_visible()

    page.get_by_test_id("start-run-button").click()

    page.wait_for_url("**/runs/run-007-abc")
    assert posted[0]["answers"] == {}, "nothing was touched, so nothing was answered"
    assert posted[0]["probe_id"] == "pb_1b51a29207db", "the run reuses the probe's ingestion"


def test_ac14_a_chosen_answer_is_the_one_that_is_sent(ui: str, page: Page) -> None:
    stub_probe(page)
    posted = capture_runs(page)
    page.goto(ui)
    fill_the_form(page)
    page.get_by_test_id("analyse-button").click()
    page.get_by_test_id("probe-option-multiple_call_periods-call_2").check()

    page.get_by_test_id("start-run-button").click()

    page.wait_for_url("**/runs/run-007-abc")
    assert posted[0]["answers"] == {"multiple_call_periods": "call_2"}, (
        "only the question that was actually answered"
    )


def test_ac14_skipping_the_questions_is_always_allowed(ui: str, page: Page) -> None:
    """`Skipping the questions is always allowed and uses the defaults.` Sending `{}` lets
    the server apply its own defaults, which is the single source of truth for them."""
    stub_probe(page)
    posted = capture_runs(page)
    page.goto(ui)
    fill_the_form(page)
    page.get_by_test_id("analyse-button").click()

    page.get_by_test_id("skip-questions-button").click()

    page.wait_for_url("**/runs/run-007-abc")
    assert posted[0]["answers"] == {}


# --- the two answers that are requests, not answers -------------------------------------------

@pytest.mark.parametrize(
    ("code", "value"),
    [("thin_profile", "use_different_url"), ("no_eligibility_found", "upload_document")],
)
def test_an_answer_asking_to_fix_the_input_starts_nothing(
    ui: str, page: Page, code: str, value: str
) -> None:
    """`use_different_url` and `upload_document` are requests to change the input. Starting
    a six-minute run on inputs the applicant has just told you are wrong is the worst
    possible response to them."""
    stub_probe(page)
    posted = capture_runs(page)
    page.goto(ui)
    fill_the_form(page)
    page.get_by_test_id("analyse-button").click()
    page.get_by_test_id(f"probe-option-{code}-{value}").check()

    page.get_by_test_id("start-run-button").click()

    expect(page.get_by_test_id("blocked-alert")).to_be_visible()
    # Back to the form: the clarify panel is gone, not merely disabled.
    expect(page.get_by_test_id("clarify-panel")).to_have_count(0)
    assert posted == [], "no run was started"
    assert "/runs/" not in page.url


# --- error surfaces ---------------------------------------------------------------------------

def test_a_validation_error_reaches_the_user_as_a_sentence(ui: str, page: Page) -> None:
    """FastAPI reports a 422 as `{detail: [{msg, loc}]}`. Rendered naively that reaches the
    user as `[object Object]`, and a 422 is the most likely error anyone actually sees."""
    stub_probe(page)
    capture_runs(
        page,
        status=422,
        body={
            "detail": [
                {"loc": ["body"], "msg": "one of grant_url or grant_upload_id is required"}
            ]
        },
    )
    page.goto(ui)
    fill_the_form(page)
    page.get_by_test_id("analyse-button").click()

    page.get_by_test_id("start-run-button").click()

    expect(page.get_by_test_id("form-error")).to_contain_text("grant_url")
    assert "object Object" not in (page.get_by_test_id("form-error").text_content() or "")


def test_analyse_is_refused_until_both_inputs_are_present(ui: str, page: Page) -> None:
    page.goto(ui)

    expect(page.get_by_test_id("analyse-button")).to_be_disabled()
    page.get_by_test_id("grant-url-input").fill("https://www.rgp.gov.sg/nrf-ar/crp")
    expect(page.get_by_test_id("analyse-button")).to_be_disabled()
    page.get_by_test_id("profile-url-input").fill("https://basurafernando.github.io/")
    expect(page.get_by_test_id("analyse-button")).to_be_enabled()


# --- two bugs found by review, and the tests that would have caught them -----------------------

def test_editing_the_inputs_after_analyse_invalidates_the_probe(ui: str, page: Page) -> None:
    """The nastiest bug in this item, and it was silent.

    The URL fields stay editable while the questions are on screen. Change them and press
    Start, and the browser was sending the **new** URLs with the **old** `probe_id` — so the
    run reused the previous probe's documents and evidence store while recording the new
    URLs as its inputs. That is a report naming one call and citing evidence from another,
    on a product whose entire claim is that its citations are real.
    """
    stub_probe(page)
    posted = capture_runs(page)
    page.goto(ui)
    fill_the_form(page)
    page.get_by_test_id("analyse-button").click()
    expect(page.get_by_test_id("clarify-panel")).to_be_visible()

    page.get_by_test_id("grant-url-input").fill("https://a-completely-different.example/call")

    expect(page.get_by_test_id("stale-probe")).to_be_visible()
    expect(page.get_by_test_id("clarify-panel")).to_have_count(0)
    assert posted == [], "nothing can be started while the probe does not match the inputs"


def test_re_analysing_after_an_edit_starts_against_the_new_inputs(
    ui: str, page: Page
) -> None:
    """The other half: recovering from stale is just pressing Analyse again."""
    stub_probe(page)
    posted = capture_runs(page)
    page.goto(ui)
    fill_the_form(page)
    page.get_by_test_id("analyse-button").click()
    expect(page.get_by_test_id("clarify-panel")).to_be_visible()

    page.get_by_test_id("grant-url-input").fill("https://a-completely-different.example/call")
    page.get_by_test_id("analyse-button").click()
    expect(page.get_by_test_id("stale-probe")).to_have_count(0)
    page.get_by_test_id("start-run-button").click()

    page.wait_for_url("**/runs/run-007-abc")
    assert posted[0]["grant_url"] == "https://a-completely-different.example/call"


def test_start_cannot_be_double_clicked_into_two_runs(ui: str, page: Page) -> None:
    """`disabled` only takes effect on the next render, so a fast double-click fires the
    handler twice — and each extra run is a real five-minute pipeline and real model spend."""
    stub_probe(page)
    posted = capture_runs(page)
    page.goto(ui)
    fill_the_form(page)
    page.get_by_test_id("analyse-button").click()
    expect(page.get_by_test_id("clarify-panel")).to_be_visible()

    # All three in ONE javascript turn, which is what a double-click actually is: React has
    # no chance to re-render and apply `disabled` in between. Three separate Playwright
    # clicks would not reproduce it — the first navigates and unmounts the button.
    page.evaluate(
        """() => {
            const b = document.querySelector('[data-testid=start-run-button]')
            b.click(); b.click(); b.click()
        }"""
    )

    page.wait_for_url("**/runs/run-007-abc")
    assert len(posted) == 1, f"one press, one run — got {len(posted)}"


def test_start_is_dead_while_a_re_analyse_is_in_flight(ui: str, page: Page) -> None:
    """Pressing Analyse again while the questions are up refuses to start a run until the
    new probe lands — so the button must look refused, not merely behave that way."""
    stub_probe(page)
    page.goto(ui)
    fill_the_form(page)
    page.get_by_test_id("analyse-button").click()
    expect(page.get_by_test_id("clarify-panel")).to_be_visible()

    # Hold the second probe open so the in-flight state is observable.
    page.route("**/api/probe", lambda route: None)
    page.get_by_test_id("analyse-button").click()

    expect(page.get_by_test_id("start-run-button")).to_be_disabled()
    expect(page.get_by_test_id("analyse-button")).to_be_disabled()


def test_a_running_run_renders_without_a_report(ui: str, page: Page) -> None:
    """Every other test drives `?fixture=`, which is always `finished`. Nothing exercised
    the in-flight branch — the `status` chip's `running` colour, or the guard that keeps the
    report block off the page while `report` is still null."""
    page.route(
        "**/api/runs/run-live*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "run_id": "run-live",
                "status": "running",
                "inputs": {"grant_src": "https://x.example/call", "profile_url": "https://x.example/me",
                           "answers": {}},
                "warnings": [],
                "events": [{"seq": 0, "ts": "2026-09-06T00:00:00Z", "type": "run.started"}],
                "report": None,
            }),
        ),
    )
    page.goto(f"{ui}/runs/run-live")

    expect(page.get_by_test_id("run-status")).to_have_text("running")
    expect(page.get_by_test_id("event-count")).to_have_text("1 events")
    # No report while the run is in flight: `report` is null until status flips.
    expect(page.get_by_test_id("direction-card")).to_have_count(0)


def test_an_uploaded_pdf_is_sent_as_grant_upload_id_not_a_url(ui: str, page: Page) -> None:
    """The PLUS drop zone. Send both and the backend silently prefers `grant_url`, so the
    upload would be ignored; send an empty `grant_url` and it is a 422."""
    page.route(
        "**/api/uploads",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"upload_id": "0123456789abcdef", "sha256": "0" * 64}),
        ),
    )
    stub_probe(page)
    posted = capture_runs(page)
    page.goto(ui)

    page.get_by_test_id("grant-file-input").set_input_files(
        files=[{"name": "call.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-1.7 fake"}]
    )
    expect(page.get_by_test_id("grant-upload-chip")).to_contain_text("call.pdf")
    page.get_by_test_id("profile-url-input").fill("https://basurafernando.github.io/")
    page.get_by_test_id("analyse-button").click()
    page.get_by_test_id("start-run-button").click()

    page.wait_for_url("**/runs/run-007-abc")
    assert posted[0]["grant_upload_id"] == "0123456789abcdef"
    assert "grant_url" not in posted[0], "sending both lets the backend silently ignore the upload"


def test_the_same_pdf_can_be_chosen_again_after_removing_it(ui: str, page: Page) -> None:
    """A file input keeps its previous value, so re-picking the SAME file fires no `change`
    event and the click does nothing — with no error to explain why."""
    uploads: list[int] = []
    page.route(
        "**/api/uploads",
        lambda route: (
            uploads.append(1),
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"upload_id": "0123456789abcdef", "sha256": "0" * 64}),
            ),
        )[-1],
    )
    page.goto(ui)
    pdf = {"name": "call.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-1.7 fake"}

    page.get_by_test_id("grant-file-input").set_input_files(files=[pdf])
    expect(page.get_by_test_id("grant-upload-chip")).to_be_visible()
    page.get_by_test_id("grant-upload-remove").click()
    expect(page.get_by_test_id("grant-upload-chip")).to_have_count(0)
    # Removing must not bubble to the drop zone and re-open the picker behind the scenes.
    expect(page.get_by_test_id("grant-drop-zone")).to_contain_text("Drop the call PDF here")

    page.get_by_test_id("grant-file-input").set_input_files(files=[pdf])

    expect(page.get_by_test_id("grant-upload-chip")).to_be_visible()
    assert len(uploads) == 2, "the second pick never reached the server"


def test_a_file_dropped_outside_the_zone_does_not_navigate_away(ui: str, page: Page) -> None:
    """The browser's default for a dropped file is to open it, discarding the form — or,
    mid-demo, the whole app."""
    page.goto(ui)

    prevented = page.evaluate(
        """() => {
            const over = new DragEvent('dragover', {bubbles: true, cancelable: true})
            document.body.dispatchEvent(over)
            const drop = new DragEvent('drop', {bubbles: true, cancelable: true})
            document.body.dispatchEvent(drop)
            return {over: over.defaultPrevented, drop: drop.defaultPrevented}
        }"""
    )

    assert prevented == {"over": True, "drop": True}
