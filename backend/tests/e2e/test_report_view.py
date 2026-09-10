"""WI-2.5 — the report view (AC2, AC3, AC6, AC11).

Driven against `?fixture=run-001`, which serves `fixtures/run-001.report.json` — a real run,
85 evidence rows, 12 papers. That is the fixture the demo falls back to, so it is the one
worth asserting against.

⚠️ The replay must be allowed to **finish** before AC6 is measured. The event stream is a
network request, and a timeline still filling in the background would make "zero network
requests on slider move" unprovable.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

F = pathlib.Path(__file__).resolve().parent.parent.parent / "fixtures"
FIXTURE = "run-001"
REPORT = json.loads((F / "run-001.report.json").read_text())

CRITERIA = [
    "grant_alignment", "scientific_novelty", "importance", "applicant_fit", "feasibility",
    "competitive_differentiation", "collaboration_potential", "impact_potential",
    "evidence_strength",
]


def open_report(page: Page, ui: str, query: str = "") -> None:
    """Load the report and wait for the replay to finish, so the network goes quiet."""
    page.goto(f"{ui}/runs/{FIXTURE}?fixture={FIXTURE}&speed=1000{query}")
    expect(page.get_by_test_id("event-count")).to_have_text("162 events", timeout=30000)
    expect(page.get_by_test_id("stream-live")).to_have_count(0)
    expect(page.get_by_test_id("direction-card").first).to_be_visible()


def card_titles(page: Page) -> list[str]:
    return page.get_by_test_id("direction-title").all_text_contents()


# --- AC2 ---------------------------------------------------------------------------------------

def test_ac2_exactly_three_directions_each_with_a_problem_and_a_gap(ui: str, page: Page) -> None:
    open_report(page, ui)

    cards = page.get_by_test_id("direction-card")
    assert cards.count() == 3, "AC2 says exactly three"
    assert page.get_by_test_id("direction-problem").count() == 3
    assert page.get_by_test_id("direction-gap").count() == 3

    for index in range(3):
        problem = page.get_by_test_id("direction-problem").nth(index).text_content() or ""
        gap = page.get_by_test_id("direction-gap").nth(index).text_content() or ""
        assert len(problem) > 80, f"card {index} has no problem statement"
        assert len(gap) > 80, f"card {index} has no evidence-backed gap"


# --- AC3 and AC11 ------------------------------------------------------------------------------

def test_ac3_every_direction_cites_at_least_two_resolvable_ids(ui: str, page: Page) -> None:
    open_report(page, ui)

    assert page.get_by_test_id("evidence-chip-missing").count() == 0, (
        "an id that does not resolve is rendered as broken on purpose — one appeared"
    )
    for index in range(3):
        card = page.get_by_test_id("direction-card").nth(index)
        chips = card.get_by_test_id("evidence-chip")
        assert chips.count() >= 2, f"AC3 wants >= 2, card {index} shows {chips.count()}"


def test_ac11_every_direction_cites_a_paper_and_a_grant_document(ui: str, page: Page) -> None:
    """`Each direction cites >= 1 paper and >= 1 grant_doc; the store holds >= 12 papers.`"""
    open_report(page, ui)

    expect(page.get_by_test_id("paper-count")).to_have_text("12 papers")

    for index in range(3):
        card = page.get_by_test_id("direction-card").nth(index)
        papers = card.locator('[data-testid=evidence-chip][data-source-type=paper]')
        grant = card.locator('[data-testid=evidence-chip][data-source-type=grant_doc]')
        assert papers.count() >= 1, f"card {index} cites no paper"
        assert grant.count() >= 1, f"card {index} cites no grant document"


def test_a_chip_opens_a_panel_with_a_real_link(ui: str, page: Page) -> None:
    """AC3's second half, made clickable: every id resolves to a stored record, and the
    record's address is one Python fetched — no model ever had a field to put one in."""
    open_report(page, ui)

    paper = page.locator('[data-testid=evidence-chip][data-source-type=paper]').first
    paper.click()

    panel = page.get_by_test_id("evidence-panel")
    expect(panel).to_be_visible()
    expect(page.get_by_test_id("panel-source-type")).to_have_text("paper")
    assert (page.get_by_test_id("panel-title").text_content() or "").strip()

    href = page.get_by_test_id("panel-link").get_attribute("href")
    assert href and href.startswith("https://"), f"not a real link: {href}"
    stored = {record["url"] for record in REPORT["evidence"] if record["url"]}
    assert href in stored, "the panel showed a URL that is not in the store (AC4/AC13)"


def test_a_grant_document_chip_shows_its_page_rather_than_a_dead_link(ui: str, page: Page) -> None:
    """A `grant_doc` row legitimately has no URL of its own — it names a page of a document."""
    open_report(page, ui)

    page.locator('[data-testid=evidence-chip][data-source-type=grant_doc]').first.click()

    expect(page.get_by_test_id("evidence-panel")).to_be_visible()
    expect(page.get_by_test_id("panel-provenance")).to_contain_text("sha256")


# --- AC6 ---------------------------------------------------------------------------------------

def test_ac6_moving_a_slider_reorders_with_zero_network_requests(ui: str, page: Page) -> None:
    """`Moving any weight slider re-orders the directions in < 100 ms with zero network
    requests.`

    Weighting `scientific_novelty` alone genuinely flips the order: the third-ranked
    direction scores 6.0 on it against the leader's 5.0. `End` and `Home` are MUI Slider's
    jump-to-max and jump-to-min, so nine key presses express "only novelty matters".
    """
    open_report(page, ui)
    before = card_titles(page)

    requests: list[str] = []
    page.on("request", lambda request: requests.append(request.url))

    page.get_by_test_id("weight-input-scientific_novelty").press("End")
    for criterion in CRITERIA:
        if criterion != "scientific_novelty":
            page.get_by_test_id(f"weight-input-{criterion}").press("Home")

    page.wait_for_timeout(100)  # AC6's budget; a slower render fails here
    after = card_titles(page)

    assert requests == [], f"the sliders triggered network calls: {requests}"
    assert after != before, "novelty-only weighting must re-order these three directions"
    assert after[0] == before[2], "the direction that scores highest on novelty leads"


def test_the_browser_reproduces_the_backends_overall_exactly(ui: str, page: Page) -> None:
    """The reason AC6 can be honest at all: the browser recomputes with the same formula the
    backend used, so a slider is not an approximation of a re-run. If the two copies of
    `compute_ranking` ever drift, this fails rather than the sliders quietly lying."""
    open_report(page, ui)

    shown = page.get_by_test_id("direction-overall").all_text_contents()
    in_rank_order = sorted(REPORT["directions"], key=lambda d: d["rank"])
    expected = [f"{d['overall']:.2f}" for d in in_rank_order]

    assert shown == expected, "the recomputed overall differs from the one in report.json"


def test_the_score_matrix_reorders_with_the_cards(ui: str, page: Page) -> None:
    """The matrix and the cards are the same three directions side by side, and the whole
    point of the screen is comparing them. The matrix used to be handed `report.directions`
    — the backend's order, labelled with the backend's `rank` — while the cards used the
    rank recomputed in the browser. One slider move and the column headed "#1" sat above a
    card headed "#1" that was a different direction.
    """
    open_report(page, ui)

    page.get_by_test_id("weight-input-scientific_novelty").press("End")
    for criterion in CRITERIA:
        if criterion != "scientific_novelty":
            page.get_by_test_id(f"weight-input-{criterion}").press("Home")
    page.wait_for_timeout(100)

    columns = page.locator('[data-testid=score-matrix] span[title]').all()
    matrix = [(c.text_content(), c.get_attribute("title")) for c in columns]
    cards = list(zip(
        page.get_by_test_id("direction-rank").all_text_contents(),
        card_titles(page),
        strict=True,
    ))

    assert matrix == cards, (
        f"the matrix reads {matrix} while the cards below read {cards}"
    )


def test_the_browser_agrees_with_the_backend_at_weights_a_slider_can_reach(
    ui: str, page: Page
) -> None:
    """The test above compares the two copies of `compute_ranking` only at the **default**
    weights — the one setting a slider is never in. That gap hid a real divergence: the
    backend rounded with Python's builtin `round()` (half-to-even) and the browser with
    `Math.round` (half-up), so a raw 5.625 was 5.62 in `report.json` and 5.63 on the card
    above it. It disagreed on 1.2% of weight vectors and every existing test passed.

    These eight vectors are ones that actually diverged before `_round_half_up` landed.
    """
    from roia.llm_schemas import CriterionScore
    from roia.ranking import compute_ranking

    # Each of these is a vector where the old `round()` and the browser disagreed **on this
    # fixture's scores** — 3.2% of random vectors did. Vectors that diverge on some other
    # report would leave this test green and prove nothing.
    diverged_before_the_fix = [
        "10,3,4,6,4,8,4,8,5", "2,5,10,7,1,1,8,2,5", "7,4,4,7,4,8,2,9,5",
        "1,10,5,10,6,9,3,5,3", "9,8,3,7,0,6,4,10,3", "8,10,4,3,2,4,9,1,4",
        "8,3,6,5,5,4,9,2,3", "8,6,2,10,5,8,1,4,5",
    ]

    for vector in diverged_before_the_fix:
        weights = dict(zip(CRITERIA, (float(n) for n in vector.split(",")), strict=True))
        page.goto(f"{ui}/runs/{FIXTURE}?fixture={FIXTURE}&speed=1000&w={vector}")
        expect(page.get_by_test_id("direction-card").first).to_be_visible()
        expect(page.get_by_test_id("direction-overall")).to_have_count(3)

        shown = dict(zip(
            page.get_by_test_id("direction-title").all_text_contents(),
            page.get_by_test_id("direction-overall").all_text_contents(),
            strict=True,
        ))
        for direction in REPORT["directions"]:
            scores = {
                name: (CriterionScore(**raw) if raw else None)
                for name, raw in (
                    (name, direction["scores"].get(name)) for name in CRITERIA
                )
            }
            expected = f"{compute_ranking(scores, weights):.2f}"
            assert shown[direction["title"]] == expected, (
                f"w={vector}: the browser shows {shown[direction['title']]} where the "
                f"backend computes {expected} for {direction['title']!r}"
            )


def test_the_weights_are_in_the_url_and_reset_puts_them_back(ui: str, page: Page) -> None:
    open_report(page, ui)
    assert "w=" not in page.url, "default weights should not clutter the URL"
    expect(page.get_by_test_id("reset-weights")).to_be_disabled()

    page.get_by_test_id("weight-input-scientific_novelty").press("End")

    assert "w=" in page.url
    expect(page.get_by_test_id("weight-value-scientific_novelty")).to_have_text("10")
    expect(page.get_by_test_id("reset-weights")).to_be_enabled()

    page.get_by_test_id("reset-weights").click()

    assert "w=" not in page.url
    expect(page.get_by_test_id("weight-value-scientific_novelty")).to_have_text("5")


def test_a_weighted_url_is_shareable(ui: str, page: Page) -> None:
    """The point of putting the weights in the URL: "look at it with novelty turned up" is
    one link, and it has to survive being pasted."""
    open_report(page, ui, query="&w=0,10,0,0,0,0,0,0,0")

    expect(page.get_by_test_id("weight-value-scientific_novelty")).to_have_text("10")
    expect(page.get_by_test_id("weight-value-grant_alignment")).to_have_text("0")
    titles = card_titles(page)
    default_order = [d["title"] for d in sorted(REPORT["directions"], key=lambda d: d["rank"])]
    assert titles[0] == default_order[2], "novelty-only ranking leads with the third direction"


def test_a_corrupt_weights_parameter_falls_back_rather_than_blanking_the_report(
    ui: str, page: Page
) -> None:
    """A URL is user input. `?w=` truncated or hand-edited must not produce NaN weights and
    an empty page — the report is the whole product."""
    open_report(page, ui, query="&w=nonsense,,,")

    assert page.get_by_test_id("direction-card").count() == 3
    expect(page.get_by_test_id("weight-value-scientific_novelty")).to_have_text("5")


# --- the two criteria that are never scored ----------------------------------------------------

def test_the_unassessed_criteria_are_shown_as_such_not_as_zero(ui: str, page: Page) -> None:
    """§4 makes the competitor and collaborator stage a non-goal, and §6.4 says those two
    render "not assessed" and are excluded from the sum. Rendering them as 0.0 would drag
    every overall down by two-ninths and look like a real judgement."""
    open_report(page, ui)

    for criterion in ("competitive_differentiation", "collaboration_potential"):
        cells = page.locator(f'[data-testid=matrix-cell][data-criterion={criterion}]')
        assert cells.count() == 3
        assert cells.evaluate_all("nodes => nodes.every(n => n.dataset.assessed === 'false')")

    # 3 directions x 9 criteria = 27 cells, two columns of which are "not assessed".
    assert page.get_by_test_id("matrix-cell").count() == 27
    assert page.get_by_test_id("criterion-not-assessed").count() == 6


def test_the_identity_banner_says_unverified(ui: str, page: Page) -> None:
    """Disambiguation is a non-goal, and demo-spec §8.5 makes saying so part of the demo."""
    open_report(page, ui)

    banner = page.get_by_test_id("identity-banner")
    expect(banner).to_be_visible()
    expect(banner).to_contain_text(REPORT["identity"]["display_name"])
    expect(page.get_by_test_id("identity-confidence")).to_have_text("unverified")


# --- the markdown pipeline ---------------------------------------------------------------------

def test_raw_html_in_model_prose_is_not_rendered(ui: str, page: Page) -> None:
    """`react-markdown` + `remark-gfm` + `rehype-sanitize`, and **no `rehype-raw`**.

    This prose is written by a model that was handed the contents of fetched web pages and
    PDFs, so page markup reaching the report is a real path rather than a hypothetical. With
    `rehype-raw` the img below would render and fire its onerror handler; without it the tags
    are inert text. Markdown itself must still work, which is why the bold survives.
    """
    poisoned = json.loads(json.dumps(REPORT))
    poisoned["directions"][0]["problem_statement"]["text"] = (
        "**Real markdown** and <img src=x onerror=\'window.__pwned=1\'> "
        "<script>window.__pwned=1</script> plus <b>bold html</b>."
    )
    snapshot = {
        "run_id": "run-md", "status": "finished",
        "inputs": {"grant_src": "x", "profile_url": "y", "answers": {}},
        "warnings": [], "events": [], "report": poisoned,
    }
    page.route(
        "**/api/runs/run-md?**",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(snapshot)
        ),
    )
    page.route("**/api/runs/run-md/events*", lambda route: route.abort())

    page.goto(f"{ui}/runs/run-md?fixture={FIXTURE}")
    expect(page.get_by_test_id("direction-card").first).to_be_visible()

    problem = page.get_by_test_id("direction-problem").first
    assert problem.locator("img").count() == 0, "rehype-raw would have rendered this"
    assert problem.locator("script").count() == 0
    assert problem.locator("b").count() == 0, "raw <b> must stay inert text"
    assert page.evaluate("() => window.__pwned") is None, "something executed"
    # Markdown still works: ** ** became a real <strong>.
    assert problem.locator("strong").count() >= 1
    # `rehype-sanitize` strips the elements and keeps their text, so the script's body is on
    # the page as inert characters. Visible but never executed is exactly the right outcome.
    assert "window.__pwned=1" in (problem.text_content() or "")
