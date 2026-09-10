"""WI-1.7 — ranking, the report render and the CLI (AC2, AC6, AC13).

The second half promotes WI-1.0's hand-run invariant checks into real tests, with
`fixtures/report-sample.json` as the golden input — that file is the frozen contract and it
should fail loudly if the models drift away from it.
"""

from __future__ import annotations

import json
import pathlib
import re

import httpx
import pytest

from roia.evidence import EVIDENCE_FLOOR, CitationContext, EvidenceStore
from roia.llm_schemas import CRITERIA, NOT_ASSESSED, SCORED_CRITERIA, CriterionScore, DirectionDraft
from roia.ranking import DEFAULT_WEIGHTS, PLACES, compute_ranking, confidence_for
from roia.report import (
    Direction,
    Report,
    ReportInputs,
    build_report,
    render_markdown,
)

F = pathlib.Path(__file__).resolve().parent.parent / "fixtures"
GOLDEN = json.loads((F / "report-sample.json").read_text())


@pytest.fixture(scope="module")
def golden() -> tuple[EvidenceStore, list[DirectionDraft], dict]:
    """The frozen contract, rebuilt as a store plus the LLM-authored half of each direction."""
    store = EvidenceStore()
    for row in GOLDEN["evidence"]:
        store.mint(**{k: v for k, v in row.items() if k != "id"})
    context = CitationContext(store=store)
    drafts = [
        DirectionDraft.model_validate(
            {
                "title": d["title"],
                "problem_statement": d["problem_statement"],
                "evidence_backed_gap": d["evidence_backed_gap"],
                "key_strengths": d["key_strengths"],
                "key_weaknesses": d["key_weaknesses"],
                "evidence_ids": d["evidence_ids"],
                "scores": {c: d["scores"][c] for c in SCORED_CRITERIA},
            },
            context=context,
        )
        for d in GOLDEN["directions"]
    ]
    return store, drafts, GOLDEN


@pytest.fixture
def report(golden) -> Report:
    store, drafts, raw = golden
    return build_report(
        "run-000",
        ReportInputs(grant_url=raw["inputs"]["grant_url"],
                     profile_url=raw["inputs"]["profile_url"]),
        drafts, store,
    )


# --- compute_ranking ---------------------------------------------------------------------

def test_compute_ranking_reproduces_the_frozen_fixture_exactly(golden) -> None:
    """The fixture's `overall` values were computed by hand in WI-1.0. If the formula and
    the fixture ever disagree, one of them is wrong."""
    _, drafts, raw = golden

    for draft, expected in zip(drafts, raw["directions"], strict=True):
        scores = {c: (getattr(draft.scores, c) if c not in NOT_ASSESSED else None)
                  for c in CRITERIA}
        assert compute_ranking(scores, raw["weights"]) == expected["overall"]


# --- confidence, derived rather than asserted -------------------------------------------------

def strength(value: float | None) -> dict[str, CriterionScore | None]:
    if value is None:
        return {"evidence_strength": None}
    return {
        "evidence_strength": CriterionScore(
            evidence_ids=["e1"], value=value, rationale="r", provenance="judged"
        )
    }


def test_confidence_follows_the_evidence_strength_rubrics_own_anchors() -> None:
    """8, 5 and 2 are not thresholds chosen to taste — they are the anchors the model scores
    `evidence_strength` against in `llm.py`'s RUBRICS. `high` is the 8-anchor ("multiple
    papers' abstracts were retrieved, and a trend and a citing count agree"), `medium`
    the 5-anchor ("several records, but none read beyond their titles")."""
    assert confidence_for(strength(10.0)) == "high"
    assert confidence_for(strength(8.0)) == "high"
    assert confidence_for(strength(7.9)) == "medium"
    assert confidence_for(strength(5.0)) == "medium"
    assert confidence_for(strength(4.9)) == "low"
    assert confidence_for(strength(0.0)) == "low"


def test_a_direction_below_the_citation_floor_is_never_confident() -> None:
    """`thin_evidence` is a fact the per-criterion score cannot see: a model can score
    `evidence_strength` 8 on citations that later fail to resolve, and the direction ends up
    below the floor. Confidence has to follow the direction, not the criterion."""
    assert confidence_for(strength(10.0), thin_evidence=True) == "low"
    assert confidence_for(strength(10.0), thin_evidence=False) == "high"


def test_an_unscored_evidence_strength_is_low_not_a_crash() -> None:
    assert confidence_for(strength(None)) == "low"
    assert confidence_for({}) == "low"


def test_the_derived_confidence_reproduces_both_recorded_runs(golden) -> None:
    """The claim that made this change safe to ship: deriving confidence changes **nothing**
    the model actually said. All six directions across both recorded runs come out identical,
    so this bought a guarantee rather than different answers.

    If a future rubric change moves a threshold, this is where it surfaces.
    """
    for name in ("report-sample.json", "run-001.report.json"):
        raw = json.loads((F / name).read_text())
        for direction in raw["directions"]:
            scores = {
                criterion: (
                    CriterionScore.model_validate(direction["scores"][criterion])
                    if direction["scores"].get(criterion) is not None
                    else None
                )
                for criterion in CRITERIA
            }
            derived = confidence_for(
                scores, thin_evidence=len(direction["evidence_ids"]) < EVIDENCE_FLOOR
            )
            assert derived == direction["confidence"], (
                f"{name} rank {direction['rank']}: model said {direction['confidence']!r}, "
                f"the rubric derives {derived!r}"
            )


def test_the_model_has_no_confidence_field_to_fill_in() -> None:
    """A tripwire. Putting `confidence` back on `DirectionDraft` would quietly return the one
    field in the report that the model asserted about its own output with nothing behind it —
    and every other test would still pass."""
    assert "confidence" not in DirectionDraft.model_fields
    assert "confidence" in Direction.model_fields, "the report still carries it, derived"


def test_flat_weights_give_the_plain_mean_of_the_scored_seven() -> None:
    """Renormalising over the scored subset is the whole point: without it, flat weights
    would give five-ninths of the mean and every direction would look mediocre."""
    scores = {c: (None if c in NOT_ASSESSED else CriterionScore(
        value=v, rationale="r", evidence_ids=["e1"]))
        # In CRITERIA order; the two zeros sit on the non-goals and are never read.
        for c, v in zip(CRITERIA, [8, 8, 7, 9, 6, 0, 0, 7, 8], strict=True)}

    expected = round((8 + 8 + 7 + 9 + 6 + 7 + 8) / 7, PLACES)
    assert compute_ranking(scores, DEFAULT_WEIGHTS) == expected


def test_moving_all_weight_onto_one_criterion_returns_that_score() -> None:
    """What the slider does at its extreme, and the property AC6 rests on."""
    scores = {c: (None if c in NOT_ASSESSED else CriterionScore(
        value=3.0, rationale="r", evidence_ids=["e1"])) for c in CRITERIA}
    scores["feasibility"] = CriterionScore(value=9.0, rationale="r", evidence_ids=["e1"])

    weights = dict.fromkeys(CRITERIA, 0.0)
    weights["feasibility"] = 1.0

    assert compute_ranking(scores, weights) == 9.0


def test_weight_on_an_unassessed_criterion_is_ignored_not_counted_as_zero() -> None:
    """"Not assessed" must not drag a direction down; it is excluded, not scored 0."""
    scores = {c: (None if c in NOT_ASSESSED else CriterionScore(
        value=8.0, rationale="r", evidence_ids=["e1"])) for c in CRITERIA}

    weights = dict.fromkeys(CRITERIA, 0.0)
    weights["collaboration_potential"] = 1.0

    assert compute_ranking(scores, weights) == 0.0, "nothing scored carries weight"
    assert compute_ranking(scores, DEFAULT_WEIGHTS) == 8.0


def test_a_direction_with_nothing_scored_is_zero_not_a_division_by_zero() -> None:
    assert compute_ranking(dict.fromkeys(CRITERIA), DEFAULT_WEIGHTS) == 0.0


def test_a_value_landing_exactly_on_a_half_rounds_up_the_way_the_browser_does() -> None:
    """The tripwire under AC6. `ranking.ts` rounds with `Math.round`, which is half-**up**;
    the builtin `round()` is half-to-**even**. Nothing caught the difference because the one
    test comparing the two copies (`test_the_browser_reproduces_the_backends_overall_exactly`)
    only ever compared them at the **default** weights — and the default weights are the one
    setting a slider is not in. Against the real `run-004` report the two disagreed on 1.2% of
    weight vectors, each one a card showing 5.63 above a `report.json` saying 5.62.

    5.5 and 5.75 average to exactly 5.625, so `round()` gives 5.62 and the browser gives 5.63.
    If this file ever goes back to `round(..., PLACES)` this fails on the first run.
    """
    scores: dict[str, CriterionScore | None] = dict.fromkeys(CRITERIA)
    scores["grant_alignment"] = CriterionScore(value=5.5, rationale="r", evidence_ids=["e1"])
    scores["importance"] = CriterionScore(value=5.75, rationale="r", evidence_ids=["e1"])

    weights = dict.fromkeys(CRITERIA, 0.0)
    weights["grant_alignment"] = weights["importance"] = 1.0

    assert compute_ranking(scores, weights) == 5.63
    assert round(5.625, PLACES) == 5.62, "the builtin is still half-to-even; that is the point"


def test_the_arithmetic_matches_the_browsers_across_the_whole_weight_space(golden) -> None:
    """The stronger form of the test above, and the one that matters.

    Pinning a single half-value catches the *rounding* difference. It does not catch the
    second divergence that was hiding behind it: `ranking.py` used to divide each term by
    `total` before summing, while `ranking.ts` sums `weight * value` and divides once at the
    end. Algebraically identical, numerically not — after the rounding was fixed the two
    still disagreed on 0.08% of weight vectors, because they were rounding different floats.

    So this re-implements `computeOverall` operation for operation and sweeps the space a
    slider can actually reach. Either divergence reappearing fails here.
    """
    import math
    import random

    def as_the_browser_does(scores, weights) -> float:
        total = 0.0
        weighted = 0.0
        for name, score in scores.items():
            weight = weights.get(name, 0)
            if score is None or weight <= 0:
                continue
            total += weight
            weighted += weight * score.value
        if total <= 0:
            return 0.0
        return math.floor((weighted / total) * 100 + 0.5) / 100  # Math.round(x*100)/100

    _, drafts, _ = golden
    every = [
        {c: (getattr(draft.scores, c) if c not in NOT_ASSESSED else None) for c in CRITERIA}
        for draft in drafts
    ]

    random.seed(0)  # fixed, so a failure is reproducible rather than a flake
    for _ in range(3000):
        weights = {c: float(random.randint(0, 10)) for c in CRITERIA}
        for scores in every:
            assert compute_ranking(scores, weights) == as_the_browser_does(scores, weights), (
                f"backend and browser disagree at w={[weights[c] for c in CRITERIA]}"
            )


# --- report assembly -----------------------------------------------------------------------

def test_python_owns_rank_overall_and_thin_evidence(report, golden) -> None:
    """Rule 2: none of these three may come from the model."""
    _, drafts, _ = golden

    assert [d.rank for d in report.directions] == [1, 2, 3]
    assert [d.overall for d in report.directions] == sorted(
        (d.overall for d in report.directions), reverse=True
    )
    assert all(not d.thin_evidence for d in report.directions)
    for field in ("rank", "overall", "thin_evidence"):
        assert field not in DirectionDraft.model_fields, f"{field} must not be an LLM field"


def test_every_direction_carries_all_nine_criteria_with_the_two_non_goals_null(report) -> None:
    for direction in report.directions:
        assert list(direction.scores) == list(CRITERIA), "order matters — the matrix is 3x9"
        assert all(direction.scores[c] is None for c in NOT_ASSESSED)
        assert all(direction.scores[c] is not None for c in SCORED_CRITERIA)


def test_the_assembled_report_matches_the_frozen_fixtures_shape(report) -> None:
    dumped = report.model_dump(mode="json")

    assert set(dumped) >= {"run_id", "generated_at", "inputs", "weights", "directions",
                           "evidence"}
    assert set(dumped["directions"][0]) == set(GOLDEN["directions"][0])
    assert set(dumped["weights"]) == set(GOLDEN["weights"])


def test_thin_evidence_is_set_from_the_floor_rather_than_asserted(golden) -> None:
    store, drafts, raw = golden
    thin = drafts[0].model_copy(deep=True)
    thin.evidence_ids = ["e1"]

    built = build_report("r", ReportInputs(grant_url="u", profile_url="p"), [thin], store)

    assert built.directions[0].thin_evidence is True


# --- AC13 -------------------------------------------------------------------------------------

def test_ac13_every_link_in_the_markdown_resolves_to_a_stored_evidence_url(report) -> None:
    """No URL in the file may have originated from a model response."""
    markdown = render_markdown(report)
    stored = {row.url for row in report.evidence if row.url}

    links = re.findall(r"\]\((https?://[^)]+)\)", markdown)
    assert links, "a report with no links is not evidence of anything"
    assert set(links) <= stored
    for url in set(links):
        assert any(row.url == url for row in report.evidence)


def test_ac13_the_markdown_contains_no_url_the_model_could_have_written(report) -> None:
    """Every http(s) string in the file must be a stored evidence URL, link or not."""
    markdown = render_markdown(report)
    stored = {row.url for row in report.evidence if row.url}
    stored.add(report.inputs.grant_url)
    stored.add(report.inputs.profile_url)

    for url in re.findall(r"https?://[^\s)|]+", markdown):
        assert url in stored, f"{url} is in the report but not in the evidence store"


def test_ac13_holds_when_the_model_actually_writes_a_url(golden) -> None:
    """The two AC13 tests above assert the right thing but prove nothing on their own: the
    golden fixture's prose contains no URLs, so they pass whether or not anything is
    stopping one. This feeds a draft that *does* contain URLs — a markdown link, a bare
    one, and one in a `list[str]` — all the way through `build_report` and
    `render_markdown`, which is the path a real leak would take.
    """
    store, drafts, raw = golden
    original = drafts[0]

    leaky = DirectionDraft.model_validate(
        {
            **original.model_dump(),
            "problem_statement": {
                "text": "As [Chen 2024](https://nature.test/fake) shows, and per "
                        "https://arxiv.test/abs/1, the field is stuck.",
                "evidence_ids": original.problem_statement.evidence_ids,
            },
            "key_strengths": ["The group's page at www.fabricated-lab.test says so."],
        },
        context=CitationContext(store=store),
    )

    markdown = render_markdown(
        build_report("run-leak", ReportInputs(grant_url=raw["inputs"]["grant_url"],
                                              profile_url=raw["inputs"]["profile_url"]),
                     [leaky], store)
    )

    allowed = {row.url for row in store.all() if row.url}
    allowed |= {raw["inputs"]["grant_url"], raw["inputs"]["profile_url"]}
    for url in re.findall(r"https?://[^\s)|]+", markdown):
        assert url in allowed, f"{url} reached report.md from model prose (AC13)"
    assert "nature.test" not in markdown
    assert "fabricated-lab.test" not in markdown
    assert "Chen 2024" in markdown, "only the link is removed; the sentence stays"


def test_the_markdown_renders_every_direction_and_its_scores(report) -> None:
    markdown = render_markdown(report)

    for direction in report.directions:
        assert f"## {direction.rank}. {direction.title}" in markdown
        assert direction.evidence_backed_gap.text in markdown
    assert markdown.count("not assessed in this build") == 3 * len(NOT_ASSESSED)
    for name in SCORED_CRITERIA:
        assert f"| {name} |" in markdown


def test_the_markdown_carries_the_runs_warnings(report) -> None:
    """AC9 in the artefact people actually forward.

    The browser shows the warnings as dismissible alerts at the top of the run. The
    markdown — the file you paste into an email — used to show none of them, so the one
    view of a run that leaves the building was the one view that hid where the tool was
    unsure. On the recorded demo run that meant two `quote_unverified` warnings vanished.
    """
    from roia.events import Run

    run = Run("run-000")
    run.warning("quote_unverified", "criterion 'Team Composition': \"Stage 1\" is not verbatim")
    run.warning("thin_literature", '"niche query" returned 3 works since 2022')

    markdown = render_markdown(report, run.warnings())

    assert "## ⚠️ What this run is unsure about" in markdown
    assert "2 warnings were recorded." in markdown
    for warning in run.warnings():
        assert warning.code in markdown
        assert warning.message in markdown
    # Ahead of the directions: a warning you have to scroll past is not a warning.
    assert markdown.index("unsure about") < markdown.index("## 1. ")


def test_the_markdown_grows_no_warning_section_when_there_were_none(report) -> None:
    """The common case must stay clean — an empty "nothing went wrong" heading trains
    people to skip the section on the run where it matters."""
    markdown = render_markdown(report)

    assert "unsure about" not in markdown
    assert "warning" not in markdown.lower().split("## 1. ")[0]


def test_a_warning_missing_its_fields_still_renders(report) -> None:
    """`Event` is `extra="allow"`, so a warning emitted with the wrong keyword would have
    no `.code`. Losing the whole report four minutes into a run over that would be a poor
    trade — it degrades to a visible row instead."""
    class Bare:
        pass

    markdown = render_markdown(report, [Bare()])

    assert "**warning**" in markdown, "an unlabelled warning must still be visible"


def test_the_score_table_stays_one_row_per_criterion(report) -> None:
    """A wrapped template line emits a real newline and silently breaks the table."""
    markdown = render_markdown(report)
    rows = [line for line in markdown.splitlines() if line.startswith("| grant_alignment |")]

    assert len(rows) == 3
    assert all(row.count("|") == 5 for row in rows)


def test_the_identity_banner_says_unverified_when_there_is_one(golden) -> None:
    from roia.openalex import AuthorMatch

    store, drafts, _ = golden
    built = build_report(
        "r", ReportInputs(grant_url="u", profile_url="p"), drafts, store,
        identity=AuthorMatch(author_id="A1", display_name="Someone",
                             institution="Somewhere", margin=0.0),
    )

    markdown = render_markdown(built)
    assert "**Someone**" in markdown and "unverified" in markdown
    assert "not cross-checked" in markdown


# --- WI-1.0's invariants, promoted from a hand-run script -------------------------------------

def test_ac3_every_direction_in_the_golden_fixture_cites_two_resolvable_ids(golden) -> None:
    store, _, raw = golden

    for direction in raw["directions"]:
        assert len(direction["evidence_ids"]) >= 2
        assert all(store.get(i) is not None for i in direction["evidence_ids"])


def test_ac4_the_golden_fixture_carries_provenance_for_every_source_type(golden) -> None:
    store, _, _ = golden

    for row in store.all():
        assert row.retrieved_at is not None
        if row.source_type == "grant_doc":
            assert row.page is not None and row.sha256
        elif row.source_type == "webpage":
            assert row.url and row.http_status == 200
        elif row.source_type == "api_query":
            assert row.url and row.http_status is not None
        elif row.source_type == "paper":
            parent = store.get(row.derived_from or "")
            assert parent is not None and parent.source_type == "api_query"
            assert parent.http_status == 200


def test_ac11_every_golden_direction_cites_a_paper_and_a_grant_document(golden) -> None:
    store, _, raw = golden

    for direction in raw["directions"]:
        kinds = {store.get(i).source_type for i in direction["evidence_ids"]}
        assert "paper" in kinds and "grant_doc" in kinds


def test_ac12_every_golden_gap_cites_its_own_trend_and_citing_rows(golden) -> None:
    store, _, raw = golden

    for direction in raw["directions"]:
        gap_ids = direction["evidence_backed_gap"]["evidence_ids"]
        titles = [store.get(i).title.lower() for i in gap_ids]
        assert any("topic trend" in t for t in titles), direction["title"]
        assert any("citing count" in t for t in titles), direction["title"]


def test_no_golden_direction_cites_another_directions_literature(golden) -> None:
    _, _, raw = golden
    shared = {"e1", "e2", "e3", "e4", "e5"}
    owned = [set(f"e{n}" for n in block) for block in
             (range(6, 11), range(11, 16), range(16, 21))]

    for direction, allowed in zip(raw["directions"], owned, strict=True):
        cited = set(direction["evidence_ids"])
        for score in direction["scores"].values():
            if score:
                cited |= set(score["evidence_ids"])
        cited |= set(direction["evidence_backed_gap"]["evidence_ids"])
        assert cited <= allowed | shared, direction["title"]


def test_no_url_appears_anywhere_inside_the_golden_directions_block() -> None:
    """Rule 1, at the level of the artefact: the model authored this half and it has no
    business containing a link."""
    assert re.findall(r"https?://\S+", json.dumps(GOLDEN["directions"])) == []


def test_every_golden_summary_respects_the_four_hundred_char_cap(golden) -> None:
    store, _, _ = golden

    assert all(len(row.summary) <= 400 for row in store.all())


# --- the CLI, end to end -----------------------------------------------------------------------

def test_the_cli_writes_a_report_from_a_full_hermetic_run(tmp_path, monkeypatch) -> None:
    """Phase 1's deliverable. Every external call is replayed, so this is the same run the
    demo does, minus the network."""
    import roia.__main__ as cli
    from tests.test_assessment import CRP, PROFILE
    from tests.test_pipeline import ScriptedGemini, transport

    client = httpx.Client(transport=httpx.MockTransport(transport))
    gemini = ScriptedGemini()
    monkeypatch.setattr(cli, "run_probe", lambda *a, **k: None)

    real_pipeline = cli.run_pipeline
    monkeypatch.setattr(
        cli, "run_pipeline",
        lambda inputs, run, **kw: real_pipeline(
            inputs, run, http=client, gemini=gemini, min_interval_s=0,
            **{k: v for k, v in kw.items() if k not in ("http", "gemini")},
        ),
    )

    code = cli.main([
        "run", "--grant", CRP, "--profile", PROFILE,
        "--out", str(tmp_path), "--events", str(tmp_path / "events.jsonl"),
        "--skip-probe",
    ])

    assert code == 0
    report = json.loads((tmp_path / "report.json").read_text())
    assert len(report["directions"]) == 3
    assert all(len(d["evidence_ids"]) >= 2 for d in report["directions"])
    assert [d["rank"] for d in report["directions"]] == [1, 2, 3]

    markdown = (tmp_path / "report.md").read_text()
    stored = {row["url"] for row in report["evidence"] if row["url"]}
    links = re.findall(r"\]\((https?://[^)]+)\)", markdown)
    assert links and set(links) <= stored, "AC13, on a real run rather than the fixture"

    from roia.events import read_jsonl
    assert len(read_jsonl(tmp_path / "events.jsonl")) >= 15, "AC7"


def test_the_cli_exits_non_zero_when_a_run_produces_no_directions(tmp_path, monkeypatch):
    """A run that finished but found nothing did not do its job, whatever else it managed."""
    import roia.__main__ as cli
    from tests.test_assessment import CRP, PROFILE
    from tests.test_pipeline import ScriptedGemini, transport

    client = httpx.Client(transport=httpx.MockTransport(transport))
    real_pipeline = cli.run_pipeline
    monkeypatch.setattr(
        cli, "run_pipeline",
        lambda inputs, run, **kw: real_pipeline(
            inputs, run, http=client, gemini=ScriptedGemini(fail={"Candidates"}),
            min_interval_s=0, **{k: v for k, v in kw.items() if k not in ("http", "gemini")},
        ),
    )

    code = cli.main(["run", "--grant", CRP, "--profile", PROFILE, "--out", str(tmp_path),
                     "--events", str(tmp_path / "events.jsonl"), "--skip-probe"])

    assert code == 1


def test_the_cli_refuses_to_run_without_a_profile(monkeypatch, capsys) -> None:
    import roia.__main__ as cli
    from roia.config import Settings
    monkeypatch.setattr(cli, "get_settings", lambda: Settings(_env_file=None))

    assert cli.main(["run", "--grant", "https://example.org/call"]) == 2
    assert "ROIA_DEMO_PROFILE_URL" in capsys.readouterr().err
