"""Optional real-browser checks: install playwright and its Chromium to enable."""

from __future__ import annotations

import json

import pytest

from agentic_ai.demo import run_rehearsal
from agentic_ai.renderer import save_presentation

playwright = pytest.importorskip("playwright.sync_api")


@pytest.fixture
def page(tmp_path):
    summary, plan = run_rehearsal()
    target = save_presentation(summary, plan, tmp_path / "index.html", fictional=True)
    with playwright.sync_playwright() as driver:
        try:
            browser = driver.chromium.launch()
        except playwright.Error as exc:
            pytest.skip(f"Chromium unavailable: {exc}")
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(error))
        page.goto(target.as_uri())
        yield page
        browser.close()
        assert not errors


def test_simulator_preserves_baseline_and_export(page):
    assert page.locator("#scenario-score").inner_text() == "82"
    page.locator("#sim-competition_risk").fill("80")
    page.locator("#sim-competition_risk").dispatch_event("input")
    assert page.locator("#scenario-score").inner_text() == "76"
    assert page.locator(".score-ring strong").inner_text() == "82"
    with page.expect_download() as download:
        page.locator("#download").click()
    with open(download.value.path(), encoding="utf-8") as stream:
        exported = json.load(stream)
    assert exported["scores"]["competition_risk"] == 38
    assert exported["overall_score"] == 82
    page.locator("#reset-scenario").click()
    assert page.locator("#scenario-score").inner_text() == "82"


def test_presenter_navigation_keyboard_and_evidence(page):
    page.locator("#present").click()
    assert page.locator(".scene:visible").count() == 1
    page.keyboard.press("ArrowRight")
    assert page.locator("#strategy").is_visible()
    page.locator("#notes").click()
    assert page.locator("#strategy .speaker-note").is_visible()
    page.keyboard.press("Escape")
    assert page.locator(".scene:visible").count() == 3
    page.locator(".strength details summary").first.click()
    page.locator(".strength .citation").first.click()
    assert page.locator("#evidence").get_attribute("open") is not None
    assert page.locator("#source-pi_strengths_and_track_record").get_attribute("open") is not None


def test_presenter_does_not_steal_slider_arrow_keys(page):
    page.locator("#present").click()
    page.locator("#sim-novelty").focus()
    page.keyboard.press("ArrowRight")
    assert page.locator("#sim-novelty").input_value() == "82"
    assert page.locator("#scorecard").is_visible()


@pytest.mark.parametrize("width", [390, 768, 1440])
def test_responsive_layout_has_no_horizontal_overflow(page, width):
    page.set_viewport_size({"width": width, "height": 900})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_print_reveals_all_scenes(page):
    page.locator("#present").click()
    page.emulate_media(media="print")
    assert page.locator(".scene:visible").count() == 3