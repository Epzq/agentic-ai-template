"""WI-1.6c — LLM #4: gaps and scores written **with** the evidence (AC3, AC11, claim C3).

Replays a recorded literature stage from `fixtures/openalex/cassette/`, so the evidence
store is byte-identical to the one the assessment in `fixtures/llm/assessment.json` was
recorded against and its cited IDs resolve exactly as they did live.
"""

from __future__ import annotations

import hashlib
import io
import json
import pathlib
import zipfile
from datetime import date

import httpx
import pytest

from roia.config import Settings
from roia.evidence import THIN_EVIDENCE, CitationContext, EvidenceStore
from roia.llm import (
    ASSESSMENT_THINKING,
    CRITERIA_NEEDING_RANGE,
    CRITERION_RANGE_MIN,
    LLM_INVALID_OUTPUT,
    MIN_RERANKING_CRITERIA,
    RUBRICS,
    SPREAD_MIN,
    DirectionEvidence,
    assess_directions,
    check_spread,
    reranking_criteria,
    rubric_text,
)
from roia.llm_schemas import (
    CRITERIA,
    NOT_ASSESSED,
    SCORED_CRITERIA,
    Assessment,
    Candidates,
    CriterionScore,
    DirectionDraft,
)
from roia.openalex import OpenAlexClient

F = pathlib.Path(__file__).resolve().parent.parent / "fixtures"
CASSETTE = F / "openalex" / "cassette"
CRP = "https://www.rgp.gov.sg/nrf-ar/crp"
PROFILE = "https://basurafernando.github.io/"
ZIP_URL = (
    "https://assets.app.optical.gov.sg/rgp/production/published/base/pages/9/"
    "ee9b60cc-1ee9-4444-a2ba-327bd9b7fe56.zip?download="
)


def cassette_key(url: str) -> str:
    """Keyed on host + path + sorted params, minus the API key."""
    parsed = httpx.URL(url)
    params = "&".join(f"{k}={v}" for k, v in sorted(parsed.params.items()) if k != "api_key")
    return hashlib.sha256(f"{parsed.host}{parsed.path}?{params}".encode()).hexdigest()[:16]


def replay_openalex(request: httpx.Request) -> httpx.Response:
    path = CASSETTE / f"{cassette_key(str(request.url))}.json"
    assert path.exists(), f"no cassette entry for {request.url} — re-record if the query changed"
    recorded = json.loads(path.read_text())
    return httpx.Response(recorded["status"], json=recorded["json"])


def replay_pages(request: httpx.Request) -> httpx.Response:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("2026 F-CRP Launch Documents/F-CRP Call Information Sheet (2026).pdf",
                         (F / "grant.pdf").read_bytes())
    routes = {
        CRP: httpx.Response(200, text=(F / "crp-page.html").read_text(),
                            headers={"content-type": "text/html"}),
        PROFILE: httpx.Response(200, text=(F / "profile-page.html").read_text(),
                                headers={"content-type": "text/html"}),
        ZIP_URL: httpx.Response(200, content=buffer.getvalue(),
                                headers={"content-type": "application/zip"}),
        "https://www.rgp.gov.sg/robots.txt": httpx.Response(200, text="User-Agent: *\nAllow: /\n"),
    }
    return routes.get(str(request.url), httpx.Response(404))


class StubGemini:
    """Replays a recorded assessment; ``texts`` lets the fallback path get its own bodies."""

    def __init__(self, *texts: str | None, raises: Exception | None = None) -> None:
        self.prompts: list[str] = []
        self.models = self
        self._texts = list(texts)
        self._raises = raises

    def generate_content(self, *, model: str, contents: str, config: object) -> object:
        self.prompts.append(contents)
        if self._raises is not None:
            raise self._raises
        text = self._texts[min(len(self.prompts) - 1, len(self._texts) - 1)]
        return type("Response", (), {"text": text})()


@pytest.fixture(scope="module")
def run() -> tuple[EvidenceStore, list[DirectionEvidence]]:
    """The store and per-direction catalogues, rebuilt from the recorded run."""
    from roia.ingest import ingest_grant, ingest_profile

    pages = httpx.Client(transport=httpx.MockTransport(replay_pages))
    store = EvidenceStore()
    grant = ingest_grant(CRP, store, client=pages, min_interval_s=0)
    ingest_profile(PROFILE, store, client=pages, min_interval_s=0)

    openalex = OpenAlexClient(
        store, client=httpx.Client(transport=httpx.MockTransport(replay_openalex)),
        settings=Settings(_env_file=None, openalex_api_key="k"), min_interval_s=0,
    )
    # Steps 2b and 2b' come before the literature in the real pipeline and mint two
    # api_query rows. Evidence IDs are sequential, so skipping them here shifts every
    # literature ID by two and the recorded assessment's citations stop resolving.
    identity = openalex.resolve_author("Basura Fernando", "basurafernando.github.io")
    openalex.fetch_author_works(identity.author_id, 40)

    candidates = Candidates.model_validate_json((F / "llm" / "candidates.json").read_text())
    items: list[DirectionEvidence] = []
    for candidate in candidates.directions:
        ids: list[str] = []
        refs = []
        for query in candidate.queries:
            refs.extend(openalex.search_literature(query, 2022))
            ids.append(store.of_type("api_query")[-1].id)
        ids.extend(openalex.fetch_top_works(refs, n=4))
        trend = openalex.topic_trend(candidate.queries[0], 2019)
        if trend.evidence_id:
            ids.append(trend.evidence_id)
        citing = openalex.citing_count(
            max(refs, key=lambda r: r.cited_by_count).id, date(2023, 1, 1)
        )
        if citing.evidence_id:
            ids.append(citing.evidence_id)
        items.append(DirectionEvidence(candidate=candidate,
                                       evidence_ids=[*grant.evidence_ids, *ids]))
    openalex.close()
    return store, items


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, gemini_api_key="test-key")


@pytest.fixture
def recorded() -> str:
    return (F / "llm" / "assessment.json").read_text()


@pytest.fixture
def drafts(run, recorded, settings) -> list[DirectionDraft]:
    store, items = run
    return assess_directions(items, store, client=StubGemini(recorded), settings=settings)


# --- the recorded run is what the ACs are checked against --------------------------------

def test_the_recorded_run_produced_twelve_papers_and_three_catalogues(run) -> None:
    """Guards every test below: if the cassette stops yielding 12 papers, AC11 is not
    really being exercised here."""
    store, items = run

    assert len(store.of_type("paper")) == 12, "AC11's 3 x 4 papers"
    assert len(items) == 3
    assert all(len(i.evidence_ids) == 31 for i in items)


# --- AC3 / AC11 --------------------------------------------------------------------------

def test_ac3_every_direction_cites_at_least_two_resolvable_ids(drafts, run) -> None:
    store, _ = run

    assert len(drafts) == 3
    for draft in drafts:
        assert len(draft.evidence_ids) >= 2, draft.title
        assert all(store.get(eid) is not None for eid in draft.evidence_ids)


def test_ac11_every_direction_cites_a_paper_and_a_grant_document(drafts, run) -> None:
    """Without this, a run that fetched zero papers satisfies every other criterion —
    two quotes from the call would be enough."""
    store, _ = run

    for draft in drafts:
        kinds = {store.get(eid).source_type for eid in draft.evidence_ids}
        assert "paper" in kinds, f"{draft.title} cites no paper it read"
        assert "grant_doc" in kinds, f"{draft.title} cites nothing from the call"


def test_every_cited_id_belongs_to_that_directions_own_catalogue(drafts, run) -> None:
    """Direction 1 citing direction 3's papers is the failure the per-direction catalogue
    exists to prevent."""
    store, items = run

    for draft, item in zip(drafts, items, strict=True):
        allowed = set(item.evidence_ids)
        stray = [eid for eid in draft.evidence_ids if eid not in allowed]
        assert stray == [], f"{draft.title} cited {stray}, which is not in its catalogue"


def test_each_criterion_score_cites_its_own_evidence(drafts) -> None:
    """plan.md §7.2: a score is never a bare float, so a heatmap cell can click through."""
    for draft in drafts:
        for name in SCORED_CRITERIA:
            score = getattr(draft.scores, name)
            assert score.evidence_ids, f"{draft.title}/{name} is a bare number"
            assert score.rationale.strip()
            assert 0 <= score.value <= 10


def test_the_gap_cites_the_evidence_it_rests_on(drafts, run) -> None:
    store, _ = run

    for draft in drafts:
        ids = draft.evidence_backed_gap.evidence_ids
        assert len(ids) >= 1, f"{draft.title} asserts a gap with nothing behind it"
        assert draft.evidence_backed_gap.text.strip()
        assert all(store.get(eid) is not None for eid in ids)


def test_direction_level_ids_are_the_union_of_what_its_fields_cite(drafts) -> None:
    """Python derives this rather than asking the model twice — the first recorded run left
    it empty on all three directions while citing 3-6 IDs per section."""
    for draft in drafts:
        nested = {
            *draft.problem_statement.evidence_ids,
            *draft.evidence_backed_gap.evidence_ids,
            *(e for c in SCORED_CRITERIA for e in getattr(draft.scores, c).evidence_ids),
        }
        assert nested <= set(draft.evidence_ids)


# --- claim C3: the sliders have to move something ----------------------------------------

def test_score_spread_is_wide_enough_for_the_weight_sliders_to_re_rank(drafts) -> None:
    """The only thing standing between this and sliders that move nothing on stage."""
    spread, wide = check_spread(drafts)

    assert spread >= SPREAD_MIN, f"overall spread {spread} < {SPREAD_MIN}"
    assert len(wide) >= CRITERIA_NEEDING_RANGE, (
        f"only {len(wide)} of {len(SCORED_CRITERIA)} criteria separate the directions by "
        f"{CRITERION_RANGE_MIN}: {wide}"
    )


def test_moving_all_weight_to_one_criterion_changes_the_order(drafts) -> None:
    """The spread numbers are a proxy; this is the property the demo actually shows."""
    base = [d.title for d in sorted(
        drafts, key=lambda d: -sum(getattr(d.scores, c).value for c in SCORED_CRITERIA))]
    flips = [
        c for c in SCORED_CRITERIA
        if [d.title for d in sorted(drafts, key=lambda d: -getattr(d.scores, c).value)] != base
    ]

    assert len(flips) >= 3, f"only {flips} re-rank the cards"


def test_check_spread_measures_compression_rather_than_hiding_it() -> None:
    """A flat assessment must report a flat spread, not be smoothed into looking fine."""
    flat = [_draft(f"D{n}", {c: 7.0 for c in SCORED_CRITERIA}) for n in range(3)]

    spread, wide = check_spread(flat)

    assert (spread, wide) == (0.0, [])
    assert check_spread([])[0] == 0.0, "one direction, or none, is not a spread"


def test_a_compressed_assessment_is_reported_at_runtime(run, settings) -> None:
    """A test catches this in CI; a warning catches it on stage."""
    store, items = run
    flat = {"directions": [
        json.loads(_draft(f"D{n}", {c: 7.0 for c in SCORED_CRITERIA}).model_dump_json())
        for n in range(3)
    ]}
    warnings: list[tuple[str, str]] = []

    assess_directions(items, store, warn=lambda c, m: warnings.append((c, m)),
                      client=StubGemini(json.dumps(flat)), settings=settings)

    assert "compressed_scores" in [c for c, _ in warnings]


def _draft(title: str, values: dict[str, float]) -> DirectionDraft:
    return DirectionDraft(
        title=title,
        problem_statement={"text": "p", "evidence_ids": []},
        evidence_backed_gap={"text": "g", "evidence_ids": []},
        scores={
            c: CriterionScore(value=v, rationale="r", evidence_ids=["e1"])
            for c, v in values.items()
        },
    )


# --- rubrics -----------------------------------------------------------------------------

def test_there_are_twenty_seven_anchored_sentences() -> None:
    assert set(RUBRICS) == set(CRITERIA)
    assert sum(len(anchors) for anchors in RUBRICS.values()) == 27
    for name, anchors in RUBRICS.items():
        assert sorted(anchors) == [2, 5, 8], name
        # Substantive anchors, not placeholders. Word count is a bad proxy — "A
        # single-investigator project with no natural partner." is 7 words and fine.
        assert all(len(sentence) >= 40 for sentence in anchors.values()), name


def test_the_two_unscored_criteria_are_defined_but_never_sent() -> None:
    """Offering a rubric for a criterion we will not score invites the model to score it."""
    sent = rubric_text()

    for name in NOT_ASSESSED:
        assert name in RUBRICS
        assert name not in sent
    for name in SCORED_CRITERIA:
        assert name in sent and RUBRICS[name][8] in sent


def test_the_prompt_carries_each_directions_own_catalogue_and_nothing_else(
    run, recorded, settings
) -> None:
    store, items = run
    stub = StubGemini(recorded)

    assess_directions(items, store, client=stub, settings=settings)

    prompt = stub.prompts[0]
    assert prompt.count("Evidence catalogue for DIRECTION") == 3
    for index, item in enumerate(items, start=1):
        block = prompt.split(f"DIRECTION {index}:")[1].split("\nDIRECTION ")[0]
        cited = {line.split("]")[0][1:] for line in block.splitlines() if line.startswith("[e")}
        assert cited <= set(item.evidence_ids)
    assert "Finding nothing means" in prompt


# --- the fallback -------------------------------------------------------------------------

def test_the_combined_call_failing_falls_back_to_one_call_per_direction(
    run, recorded, settings
) -> None:
    """Decided in advance rather than at 9 pm. It loses cross-direction calibration, which
    is why it is a fallback and not the design."""
    store, items = run
    single = json.dumps(json.loads(recorded)["directions"][0])
    stub = StubGemini("not valid json", single, single, single)
    warnings: list[tuple[str, str]] = []

    drafts = assess_directions(items, store, warn=lambda c, m: warnings.append((c, m)),
                               client=stub, settings=settings)

    assert len(stub.prompts) == 4, "one combined attempt, then one call per direction"
    assert len(drafts) == 3
    assert stub.prompts[1].count("Evidence catalogue for DIRECTION") == 1
    assert LLM_INVALID_OUTPUT in [c for c, _ in warnings]


def test_a_total_failure_returns_nothing_rather_than_raising(run, settings) -> None:
    store, items = run

    drafts = assess_directions(items, store, client=StubGemini(raises=RuntimeError("down")),
                               settings=settings)

    assert drafts == []


def test_uses_the_smart_model_at_the_measured_thinking_level(
    run, recorded, settings, monkeypatch
) -> None:
    """Pro for the one call that scores across directions — WI-0.1's decision — but at
    `ASSESSMENT_THINKING`, not `high`.

    This test used to assert `HIGH` and so pinned the bug in place: the constant was added
    with the measurement that justified it (`high` ran 84 s, 233 s and 411 s on the same
    prompt, against AC1's 360 s for the entire run) and then applied only to the
    per-direction fallback. Asserting the constant rather than a literal means the next
    measurement moves both together.
    """
    store, items = run
    seen: dict[str, object] = {}

    class Recording(StubGemini):
        def generate_content(self, *, model, contents, config):
            seen["model"] = model
            seen["thinking"] = config.thinking_config.thinking_level
            seen["max_output_tokens"] = config.max_output_tokens
            return super().generate_content(model=model, contents=contents, config=config)

    assess_directions(items, store, client=Recording(recorded), settings=settings)

    assert seen["model"] == settings.model_smart == "gemini-3.1-pro-preview"
    assert str(seen["thinking"]).endswith(ASSESSMENT_THINKING.upper())
    assert seen["max_output_tokens"] >= 16_000


# --- the frozen contract -------------------------------------------------------------------

def test_the_wi_1_0_fixture_still_validates_against_these_models() -> None:
    """`fixtures/report-sample.json` is the shape WI-2.5 renders. If the models and the
    fixture disagree, one of them is wrong and it is usually the models."""
    report = json.loads((F / "report-sample.json").read_text())
    store = EvidenceStore()
    for row in report["evidence"]:
        fields = {k: v for k, v in row.items() if k != "id"}
        store.mint(**fields)

    for direction in report["directions"]:
        draft = DirectionDraft.model_validate(
            {
                "title": direction["title"],
                "problem_statement": direction["problem_statement"],
                "evidence_backed_gap": direction["evidence_backed_gap"],
                "key_strengths": direction["key_strengths"],
                "key_weaknesses": direction["key_weaknesses"],
                "evidence_ids": direction["evidence_ids"],
                "scores": {c: direction["scores"][c] for c in SCORED_CRITERIA},
            },
            context=CitationContext(store=store),
        )
        assert draft.evidence_ids
        assert all(getattr(draft.scores, c).provenance == "judged" for c in SCORED_CRITERIA)
        assert all(direction["scores"][c] is None for c in NOT_ASSESSED)


def test_a_criterion_score_needs_only_one_id_but_a_direction_needs_two() -> None:
    """WI-1.2's floor is per model. Leaving CriterionScore at the default 2 would flag
    every score in the report as thin_evidence."""
    assert CriterionScore.evidence_floor == 1
    assert DirectionDraft.evidence_floor == 2


def test_thin_evidence_is_not_something_the_model_can_claim_about_itself() -> None:
    assert "thin_evidence" not in DirectionDraft.model_fields
    assert THIN_EVIDENCE  # Python sets it, from call_with_evidence_floor's verdict


def test_no_score_field_can_carry_a_fabricated_source() -> None:
    """AC5 again, at the schema that has the most fields."""
    for model in (DirectionDraft, CriterionScore, Assessment):
        assert not {"url", "source_title", "link"} & set(model.model_fields)


# --- AC10b in the pipeline, not just in a unit test ----------------------------------------

def test_ac10b_a_direction_left_under_its_floor_triggers_exactly_one_retry(
    run, recorded, settings
) -> None:
    """Unresolvable IDs are dropped during validation; if that leaves a direction under two
    resolvable IDs, the call gets one more attempt and the better result wins."""
    store, items = run
    stripped = json.loads(recorded)
    for direction in stripped["directions"]:
        direction["evidence_ids"] = ["e9999"]
        direction["problem_statement"]["evidence_ids"] = []
        direction["evidence_backed_gap"]["evidence_ids"] = ["e9999"]
        for name in SCORED_CRITERIA:
            direction["scores"][name]["evidence_ids"] = []
    stub = StubGemini(json.dumps(stripped), recorded)
    warnings: list[tuple[str, str]] = []

    drafts = assess_directions(items, store, warn=lambda c, m: warnings.append((c, m)),
                               client=stub, settings=settings)

    assert len(stub.prompts) == 2, "one retry, not zero and not a loop"
    assert all(len(d.evidence_ids) >= 2 for d in drafts), "the better attempt won"
    assert THIN_EVIDENCE not in [c for c, _ in warnings]


def test_ac10b_a_direction_still_thin_after_the_retry_is_reported(
    run, recorded, settings
) -> None:
    store, items = run
    stripped = json.loads(recorded)
    for direction in stripped["directions"]:
        direction["evidence_ids"] = []
        direction["problem_statement"]["evidence_ids"] = []
        direction["evidence_backed_gap"]["evidence_ids"] = []
        for name in SCORED_CRITERIA:
            direction["scores"][name]["evidence_ids"] = []
    stub = StubGemini(json.dumps(stripped))
    warnings: list[tuple[str, str]] = []

    assess_directions(items, store, warn=lambda c, m: warnings.append((c, m)),
                      client=stub, settings=settings)

    assert len(stub.prompts) == 2
    assert THIN_EVIDENCE in [c for c, _ in warnings]


def test_a_clean_assessment_costs_no_second_call(run, recorded, settings) -> None:
    """This call is 84 s on Pro. A needless retry is 84 s of the AC1 budget."""
    store, items = run
    stub = StubGemini(recorded)

    assess_directions(items, store, client=stub, settings=settings)

    assert len(stub.prompts) == 1


@pytest.mark.live
def test_live_the_assessment_produces_three_scored_directions_that_spread() -> None:
    """The riskiest call in the build, against the real API. ~85 s on Pro with thinking=high;
    `-m live` is opt-in for exactly that reason."""
    from roia.ingest import ingest_grant, ingest_profile

    pages = httpx.Client(transport=httpx.MockTransport(replay_pages))
    store = EvidenceStore()
    grant = ingest_grant(CRP, store, client=pages, min_interval_s=0)
    ingest_profile(PROFILE, store, client=pages, min_interval_s=0)
    openalex = OpenAlexClient(
        store, client=httpx.Client(transport=httpx.MockTransport(replay_openalex)),
        settings=Settings(_env_file=None, openalex_api_key="k"), min_interval_s=0,
    )
    candidates = Candidates.model_validate_json((F / "llm" / "candidates.json").read_text())
    items = []
    for candidate in candidates.directions:
        ids, refs = [], []
        for query in candidate.queries:
            refs.extend(openalex.search_literature(query, 2022))
            ids.append(store.of_type("api_query")[-1].id)
        ids.extend(openalex.fetch_top_works(refs, n=4))
        items.append(DirectionEvidence(candidate=candidate,
                                       evidence_ids=[*grant.evidence_ids, *ids]))
    openalex.close()

    drafts = assess_directions(items, store)

    assert len(drafts) == 3
    spread, wide = check_spread(drafts)
    assert spread >= SPREAD_MIN, f"spread {spread}"
    assert len(wide) >= CRITERIA_NEEDING_RANGE, f"{wide}"
    for draft in drafts:
        kinds = {store.get(e).source_type for e in draft.evidence_ids}
        assert {"paper", "grant_doc"} <= kinds, f"{draft.title}: {kinds}"


def test_a_small_overall_spread_is_not_reported_when_the_sliders_still_re_rank() -> None:
    """A live run scored a spread of 0.71 — under the compression floor — while six of
    seven criteria re-ranked the cards, because the winner rotated across criteria and the
    means cancelled. The directions were genuinely close on a flat weighting and the
    sliders were doing exactly their job."""
    rotating = [
        _draft("A", dict(zip(SCORED_CRITERIA, [8, 8, 5, 2, 2, 8, 2], strict=True))),
        _draft("B", dict(zip(SCORED_CRITERIA, [2, 5, 8, 5, 8, 2, 5], strict=True))),
        _draft("C", dict(zip(SCORED_CRITERIA, [5, 2, 2, 3, 5, 5, 8], strict=True))),
    ]

    spread, wide = check_spread(rotating)
    flips = reranking_criteria(rotating)

    assert spread < SPREAD_MIN, "the means really are close"
    assert len(wide) >= CRITERIA_NEEDING_RANGE and len(flips) >= MIN_RERANKING_CRITERIA


def test_reranking_criteria_finds_nothing_when_one_direction_dominates() -> None:
    """If the same direction wins every criterion, no slider changes anything."""
    dominant = [
        _draft("A", dict.fromkeys(SCORED_CRITERIA, 9.0)),
        _draft("B", dict.fromkeys(SCORED_CRITERIA, 5.0)),
        _draft("C", dict.fromkeys(SCORED_CRITERIA, 2.0)),
    ]

    assert reranking_criteria(dominant) == []
    assert reranking_criteria([]) == []
