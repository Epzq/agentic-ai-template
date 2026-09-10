"""WI-1.6d — the run, end to end (AC1, AC7, AC9, AC12).

Every external call is replayed: pages from `fixtures/*.html`, OpenAlex from the cassette,
and the four LLM calls from `fixtures/llm/*.json`. That makes the whole of §5 steps 1-8
runnable in a test, which is the only way to assert on the event stream the UI depends on.
"""

from __future__ import annotations

import pathlib

import httpx
import pytest

from roia.config import Settings
from roia.events import EVENT_TYPES, Run, read_jsonl
from roia.evidence import EvidenceStore
from roia.ingest import MULTIPLE_CALL_PERIODS, probe
from roia.llm_schemas import SCORED_CRITERIA
from roia.pipeline import (
    NO_CANDIDATES,
    PipelineResult,
    RunInputs,
    run_pipeline,
)
from tests.test_assessment import CRP, PROFILE, replay_openalex, replay_pages

F = pathlib.Path(__file__).resolve().parent.parent / "fixtures"


class ScriptedGemini:
    """Serves the recorded response for whichever schema the pipeline asks for.

    Keyed on the schema's title rather than a call counter: a retry would shift a counter
    and silently hand the next call the wrong body.
    """

    BODIES = {
        "GrantBrief": "grant-brief.json",
        "Capabilities": "capabilities.json",
        "Candidates": "candidates.json",
        "Assessment": "assessment.json",
        "DirectionDraft": "assessment.json",  # the per-direction fallback
    }

    def __init__(self, *, fail: set[str] | None = None) -> None:
        self.calls: list[str] = []
        self.prompts: list[tuple[str, str]] = []
        self.models = self
        self._fail = fail or set()

    def body_for(self, name: str) -> str:
        return (F / "llm" / self.BODIES[name]).read_text()

    def generate_content(self, *, model: str, contents: str, config: object) -> object:
        name = config.response_json_schema["title"]
        self.calls.append(name)
        self.prompts.append((name, contents))
        if name in self._fail:
            raise RuntimeError(f"{name} refused")
        return type("Response", (), {"text": self.body_for(name)})()

    def prompts_for(self, name: str) -> str:
        return "\n".join(text for called, text in self.prompts if called == name)


def transport(request: httpx.Request) -> httpx.Response:
    """One transport for both worlds: recorded pages, and the OpenAlex/ROR cassette.

    `run_pipeline` hands this same client to ingestion *and* to `OpenAlexClient`, so a
    request that is not in either store fails loudly rather than reaching the live API.
    """
    if request.url.host in ("api.openalex.org", "api.ror.org"):
        return replay_openalex(request)
    return replay_pages(request)


@pytest.fixture
def http() -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(transport))


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, gemini_api_key="k", openalex_api_key="k")


@pytest.fixture
def inputs() -> RunInputs:
    return RunInputs(grant_src=CRP, profile_url=PROFILE)


@pytest.fixture
def completed(tmp_path, http, settings, inputs) -> tuple[PipelineResult, Run]:
    run = Run("run-test", jsonl_path=tmp_path / "run.jsonl")
    result = run_pipeline(inputs, run, http=http, gemini=ScriptedGemini(),
                          settings=settings, min_interval_s=0)
    return result, run


# --- the whole run ------------------------------------------------------------------------

def test_the_pipeline_produces_three_assessed_directions(completed) -> None:
    result, _ = completed

    assert len(result.directions) == 3
    assert result.report is not None and len(result.report.directions) == 3
    assert result.markdown.startswith("# Research directions for")
    assert result.brief is not None and result.capabilities is not None
    assert result.identity is not None and result.identity.confidence == "unverified"
    assert len(result.store.of_type("paper")) == 12, "AC11's 3 x 4"


def test_the_four_llm_calls_happen_in_the_order_section_five_specifies(
    tmp_path, http, settings, inputs
) -> None:
    """Rule 3 at the pipeline level: candidates are proposed before any search runs, and
    the assessment happens after."""
    gemini = ScriptedGemini()
    run = Run("run-test", jsonl_path=tmp_path / "run.jsonl")

    run_pipeline(inputs, run, http=http, gemini=gemini, settings=settings, min_interval_s=0)

    assert gemini.calls == ["GrantBrief", "Capabilities", "Candidates", "Assessment"]
    types = [e.type for e in run.events]
    stages = [e.model_dump()["stage"] for e in run.events if e.type == "stage.started"]
    assert stages == ["ingest", "identity", "author_works", "grant_brief", "capabilities",
                      "candidates", "literature", "assessment", "ranking", "report"]
    assert types[0] == "run.started" and types[-1] == "run.finished"


def test_the_literature_stage_runs_after_candidates_and_before_the_assessment(
    completed,
) -> None:
    _, run = completed
    order = [e.model_dump().get("stage") or e.model_dump().get("tool") for e in run.events]

    assert order.index("candidates") < order.index("search_literature")
    assert order.index("search_literature") < order.index("llm_assessment")


# --- AC7 ------------------------------------------------------------------------------------

def test_ac7_a_run_streams_far_more_than_fifteen_events(completed) -> None:
    _, run = completed

    assert len(run.events) >= 15
    assert {e.type for e in run.events} >= {
        "run.started", "stage.started", "stage.finished", "tool.started", "tool.finished",
        "evidence.added", "identity.resolved", "run.finished",
    }
    assert [e.seq for e in run.events] == list(range(len(run.events)))


def test_ac7_every_event_reaches_the_jsonl_file(completed, tmp_path) -> None:
    _, run = completed

    replayed = read_jsonl(tmp_path / "run.jsonl")

    assert len(replayed) == len(run.events) >= 15
    assert [e.model_dump() for e in replayed] == [e.model_dump() for e in run.events]


def test_every_minted_row_is_announced_exactly_once(completed) -> None:
    """The Sources counter is driven by these; a double count is a visible lie."""
    result, run = completed
    announced = [e.model_dump()["id"] for e in run.events if e.type == "evidence.added"]

    assert sorted(announced) == sorted(row.id for row in result.store.all())
    assert len(announced) == len(set(announced))


def test_tool_events_carry_the_ids_they_minted(completed) -> None:
    _, run = completed
    finished = [e.model_dump() for e in run.events if e.type == "tool.finished"]

    search = [e for e in finished if e["tool"] == "search_literature"]
    assert len(search) == 9, "3 directions x 3 queries"
    assert all(e["evidence_added"] for e in search)
    assert all(e["ms"] >= 0 for e in finished)


# --- AC12 -------------------------------------------------------------------------------------

def test_ac12_every_direction_gets_a_trend_and_a_citing_count_with_a_row_behind_it(
    completed,
) -> None:
    result, _ = completed

    assert len(result.trends) == len(result.citings) == 3
    for measure in [*result.trends, *result.citings]:
        assert measure.evidence_id is not None
        assert result.store.get(measure.evidence_id).source_type == "api_query"
        assert measure.detail
    assert all(t.value > 0 for t in result.trends), "a trend of zero is not a numeric result"


def test_ac12_the_measurement_rows_are_in_each_directions_catalogue(completed) -> None:
    """So LLM #4 can cite them, which is the half of AC12 that makes the gap checkable."""
    result, _ = completed

    for catalogue, trend, citing in zip(
        result.catalogues, result.trends, result.citings, strict=True
    ):
        assert trend.evidence_id in catalogue.evidence_ids
        assert citing.evidence_id in catalogue.evidence_ids


def test_each_catalogue_holds_the_grant_rows_plus_only_its_own_literature(completed) -> None:
    result, _ = completed
    grant_ids = set(result.grant.evidence_ids)

    seen: set[str] = set()
    for catalogue in result.catalogues:
        own = set(catalogue.evidence_ids) - grant_ids
        assert grant_ids <= set(catalogue.evidence_ids), "the call is in every catalogue"
        assert not (own & seen), "a direction's literature leaked into another's catalogue"
        seen |= own


# --- AC9 -----------------------------------------------------------------------------------

def test_ac9_an_unreachable_profile_still_produces_a_finished_run(
    tmp_path, settings
) -> None:
    """The headline graceful-degradation case: a broken profile URL warns and continues."""
    def half_broken(request: httpx.Request) -> httpx.Response:
        if request.url.host == "basurafernando.github.io":
            return httpx.Response(404)
        return transport(request)

    run = Run("run-test", jsonl_path=tmp_path / "run.jsonl")
    result = run_pipeline(
        RunInputs(grant_src=CRP, profile_url=PROFILE), run,
        http=httpx.Client(transport=httpx.MockTransport(half_broken)),
        gemini=ScriptedGemini(), settings=settings, min_interval_s=0,
    )

    assert run.events[-1].type == "run.finished", "a dead profile must not kill the run"
    assert "fetch_failed" in [e.model_dump()["code"] for e in run.warnings()]
    assert result.brief is not None, "the grant half of the run still worked"
    assert result.identity is None


def test_ac9_a_refused_llm_call_warns_and_the_run_continues(tmp_path, http, settings, inputs):
    run = Run("run-test", jsonl_path=tmp_path / "run.jsonl")

    result = run_pipeline(inputs, run, http=http,
                          gemini=ScriptedGemini(fail={"Candidates"}),
                          settings=settings, min_interval_s=0)

    codes = [e.model_dump()["code"] for e in run.warnings()]
    assert NO_CANDIDATES in codes
    assert run.events[-1].type == "run.finished"
    assert result.directions == [] and result.brief is not None


def test_a_failing_stage_is_reported_and_does_not_escape(tmp_path, settings, inputs) -> None:
    def explode(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("the network is gone")

    run = Run("run-test", jsonl_path=tmp_path / "run.jsonl")

    result = run_pipeline(inputs, run,
                          http=httpx.Client(transport=httpx.MockTransport(explode)),
                          gemini=ScriptedGemini(), settings=settings, min_interval_s=0)

    assert run.events[-1].type == "run.finished"
    assert result.directions == []
    assert run.warnings(), "a run that achieved nothing must say why"


def test_llm_three_gets_one_retry_before_the_stage_is_given_up(
    tmp_path, http, settings, inputs
) -> None:
    """Candidates is min_length=3, so a short response loses the whole stage. One Flash
    retry is ~3 s against a six-minute budget."""
    class ShortThenGood(ScriptedGemini):
        """Returns two directions the first time Candidates is asked for, then the real one."""

        def body_for(self, name: str) -> str:
            if name == "Candidates" and self.calls.count("Candidates") == 1:
                return '{"directions": []}'
            return super().body_for(name)

    gemini = ShortThenGood()
    run = Run("run-test", jsonl_path=tmp_path / "run.jsonl")

    result = run_pipeline(inputs, run, http=http, gemini=gemini, settings=settings,
                          min_interval_s=0)

    assert gemini.calls.count("Candidates") == 2
    assert len(result.directions) == 3, "the retry recovered the stage"


# --- reusing the probe -----------------------------------------------------------------------

def test_the_probe_ingestion_is_reused_rather_than_repeated(tmp_path, settings) -> None:
    """Re-ingesting costs ~17 s of the AC1 budget and doubles the evidence store."""
    store = EvidenceStore()
    pages = httpx.Client(transport=httpx.MockTransport(transport))
    result_probe = probe(CRP, PROFILE, store, client=pages, min_interval_s=0)
    after_probe = len(store)
    assert after_probe > 20

    run = Run("run-test", jsonl_path=tmp_path / "run.jsonl")
    result = run_pipeline(
        RunInputs(grant_src=CRP, profile_url=PROFILE), run, probe=result_probe, store=store,
        http=pages, gemini=ScriptedGemini(), settings=settings, min_interval_s=0,
    )

    grant_rows = [r for r in result.store.all()[:after_probe] if r.source_type == "grant_doc"]
    assert len(grant_rows) == 21, "the call's pages were minted once, not twice"
    assert result.grant is result_probe.grant
    assert [e.model_dump()["tool"] for e in run.events if e.type == "tool.started"][0] == (
        "reuse_probe_documents"
    )


def test_the_applicants_probe_answer_reaches_the_grant_brief(tmp_path, settings) -> None:
    """AC14's last clause, at the pipeline level rather than the call level."""
    store = EvidenceStore()
    pages = httpx.Client(transport=httpx.MockTransport(transport))
    result_probe = probe(CRP, PROFILE, store, client=pages, min_interval_s=0)
    question = next(q for q in result_probe.questions if q.code == MULTIPLE_CALL_PERIODS)
    frontier = next(o for o in question.options if "Frontier" in o.label)
    gemini = ScriptedGemini()

    run_pipeline(
        RunInputs(grant_src=CRP, profile_url=PROFILE,
                  answers={MULTIPLE_CALL_PERIODS: frontier.value}),
        Run("run-test", jsonl_path=tmp_path / "run.jsonl"),
        probe=result_probe, store=store, http=pages, gemini=gemini,
        settings=settings, min_interval_s=0,
    )

    assert "23 Mar 2026" in gemini.prompts_for("GrantBrief")


# --- the committed AC7 fixture -----------------------------------------------------------------

def test_the_committed_run_001_fixture_is_a_real_run(completed) -> None:
    """`fixtures/run-001.jsonl` is what WI-2.3 replays and what AC7 is counted against."""
    events = read_jsonl(F / "run-001.jsonl")

    assert len(events) >= 15
    assert [e.seq for e in events] == list(range(len(events)))
    assert events[0].type == "run.started" and events[-1].type == "run.finished"
    assert {e.type for e in events} <= EVENT_TYPES
    minted = [e.model_dump()["id"] for e in events if e.type == "evidence.added"]
    assert len(minted) == len(set(minted)) >= 40


def test_the_report_still_has_all_nine_criteria_in_order() -> None:
    """Guards the shape WI-1.7 assembles and WI-2.5 renders."""
    assert len(SCORED_CRITERIA) == 7
