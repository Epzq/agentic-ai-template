"""Orchestration — ``demo-spec.md`` §5, steps 1 to 8, in order.

The ordering constraint that matters more than any other: **LLM #3 does not see the
literature and LLM #4 does.** Call #3 proposes directions and queries from the call and the
applicant alone; Python then runs those queries, fetches the most-cited works and measures
the field; only then does call #4 write the gaps, with the catalogue in front of it.
Reversed, the system asserts gaps with nothing behind them.

There is no tool-calling loop. Control flow is a plain function, so every step boundary
emits an event trivially and a failure is a `warning` rather than a dead run (AC9).

**Steps 9 and 10 — `compute_ranking` and the `report.md` render — belong to WI-1.7.** They
are pure Python over what this returns; the seam is `PipelineResult`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date

import httpx
from google import genai
from pydantic import BaseModel

import roia.ingest as ingest_module
import roia.openalex as openalex_module
from roia.config import Settings, get_settings
from roia.events import Run
from roia.evidence import EvidenceStore
from roia.ingest import (
    DocumentSet,
    ProbeResult,
    answers_brief,
    extract_identity,
    ingest_grant,
    ingest_profile,
    resolve_answers,
)
from roia.llm import (
    DirectionEvidence,
    assess_directions,
    candidate_directions,
    capabilities,
    grant_brief,
)
from roia.llm_schemas import Candidates, Capabilities, DirectionDraft, GrantBrief
from roia.openalex import AuthorMatch, Measure, OpenAlexClient, WorkRef
from roia.report import Report, ReportInputs, build_report, render_markdown

#: Fixed, not derived from today's date. The recorded cassette is keyed on the request URL,
#: so a moving window would miss every entry the moment the year rolls over.
SEARCH_FROM_YEAR = 2022
#: Wide enough to show a curve rather than a single point (AC12).
TREND_FROM_YEAR = 2019
CITING_SINCE = date(2023, 1, 1)

AUTHOR_WORKS_LIMIT = 40
PAPERS_PER_DIRECTION = 4

#: The politeness intervals each module chose for itself. Tests pass 0 for both.
INGEST_INTERVAL_S = ingest_module.REQUEST_INTERVAL_S
OPENALEX_INTERVAL_S = openalex_module.MIN_INTERVAL_S

#: warning codes owned by the pipeline itself
STAGE_FAILED = "stage_failed"
NO_CANDIDATES = "no_candidates"
NO_ASSESSMENT = "no_assessment"


class RunInputs(BaseModel):
    """What the user gave us. ``answers`` come from the pre-flight probe (WI-1.4b)."""

    grant_src: str
    profile_url: str
    answers: dict[str, str] = {}


@dataclass
class PipelineResult:
    """Everything steps 1-8 produced. WI-1.7 ranks and renders from this."""

    store: EvidenceStore
    grant: DocumentSet | None = None
    profile: DocumentSet | None = None
    identity: AuthorMatch | None = None
    brief: GrantBrief | None = None
    capabilities: Capabilities | None = None
    directions: list[DirectionDraft] = field(default_factory=list)
    catalogues: list[DirectionEvidence] = field(default_factory=list)
    #: One pair per direction, in the same order — AC12 wants a number for every direction.
    trends: list[Measure] = field(default_factory=list)
    citings: list[Measure] = field(default_factory=list)
    #: §5 steps 9 and 10. Both pure Python; no model sees either.
    report: Report | None = None
    markdown: str = ""


@contextmanager
def _tool(run: Run, store: EvidenceStore, name: str, args: str = "") -> Iterator[None]:
    """Run a retrieval step, then announce every row it minted.

    ``EvidenceStore.all()`` is in mint order, so the rows added since the mark are exactly
    this tool's. Emitting in a ``finally`` means a step that failed half-way still reports
    what it managed to store.
    """
    mark = len(store)
    with run.tool(name, args) as added:
        try:
            yield
        finally:
            for row in store.all()[mark:]:
                added.append(row.id)
                run.evidence_added(row)


@contextmanager
def _stage(run: Run, name: str) -> Iterator[None]:
    """A stage that reports its own failure and lets the run continue (AC9).

    One unreachable page or one refused model call should cost a section of the report, not
    the four minutes already spent.
    """
    try:
        with run.stage(name):
            yield
    except Exception as exc:  # noqa: BLE001 - the whole point is that nothing escapes
        run.warning(STAGE_FAILED, f"stage {name!r} failed: {type(exc).__name__}: {exc}")


def run_pipeline(
    inputs: RunInputs,
    run: Run,
    *,
    probe: ProbeResult | None = None,
    store: EvidenceStore | None = None,
    #: One client for every HTTP call in the run — pages *and* OpenAlex. A transport that
    #: routes on host serves both, and a test that could not intercept OpenAlex would be
    #: hitting the live API without saying so.
    http: httpx.Client | None = None,
    gemini: genai.Client | None = None,
    settings: Settings | None = None,
    min_interval_s: float | None = None,
) -> PipelineResult:
    """Execute §5 steps 1-8 and return what they produced. Never raises.

    Pass ``probe`` **and** the ``store`` it minted into: the probe already ingested both
    inputs, and re-doing that costs ~17 s of the AC1 budget and doubles the evidence. The
    store has to come with it, or the IDs the probe already showed the user in its questions
    would point at nothing.
    """
    active = settings or get_settings()
    result = PipelineResult(store=store or EvidenceStore())
    run.started(grant_src=inputs.grant_src, profile_url=inputs.profile_url,
                answers=inputs.answers)

    openalex: OpenAlexClient | None = None
    try:
        _ingest(inputs, run, result, probe, http, min_interval_s)
        openalex = OpenAlexClient(
            result.store, warn=run.warning, emit=run.emit, settings=active, client=http,
            min_interval_s=OPENALEX_INTERVAL_S if min_interval_s is None else min_interval_s,
        )
        _identity(run, result, openalex)
        works = _author_works(run, result, openalex)
        _brief(inputs, run, result, probe, gemini, active)
        _capabilities(run, result, works, gemini, active)
        candidates = _candidates(run, result, gemini, active)
        if candidates:
            _literature(run, result, openalex, candidates)
            _assessment(run, result, gemini, active)
        _rank_and_render(inputs, run, result)
        run.finished(
            directions=len(result.directions),
            evidence=len(result.store),
            papers=len(result.store.of_type("paper")),
        )
    except Exception as exc:  # noqa: BLE001 - a run reports its own death
        run.failed(type(exc).__name__, str(exc))
    finally:
        if openalex is not None:
            openalex.close()
    return result


# --- steps 1 and 2: ingestion ----------------------------------------------------------

def _ingest(
    inputs: RunInputs,
    run: Run,
    result: PipelineResult,
    probe: ProbeResult | None,
    http: httpx.Client | None,
    min_interval_s: float | None,
) -> None:
    if probe is not None and probe.grant is not None and probe.profile is not None:
        result.grant, result.profile = probe.grant, probe.profile
        with _stage(run, "ingest"), run.tool(
            "reuse_probe_documents", f"{len(result.store)} rows already minted"
        ) as added:
            # The probe minted these before the run began, so they are not "since the mark".
            for row in result.store.all():
                added.append(row.id)
                run.evidence_added(row)
        return

    interval = INGEST_INTERVAL_S if min_interval_s is None else min_interval_s
    with _stage(run, "ingest"):
        with _tool(run, result.store, "ingest_grant", inputs.grant_src):
            result.grant = ingest_grant(
                inputs.grant_src, result.store, warn=run.warning,
                client=http, min_interval_s=interval,
            )
        with _tool(run, result.store, "ingest_profile", inputs.profile_url):
            result.profile = ingest_profile(
                inputs.profile_url, result.store, warn=run.warning,
                client=http, min_interval_s=interval,
            )


# --- step 2b: identity -----------------------------------------------------------------

def _identity(run: Run, result: PipelineResult, openalex: OpenAlexClient) -> None:
    with _stage(run, "identity"):
        if result.profile is None or not result.profile.seed_html:
            run.warning(STAGE_FAILED, "no profile page to extract a researcher name from")
            return
        name, domain = extract_identity(
            result.profile.seed_html, result.profile.final_url or "", warn=run.warning
        )
        with _tool(run, result.store, "resolve_author", f"{name} @ {domain}"):
            # profile_text carries the 30-point topic-overlap term; without it the ranking
            # is works-count only and a namesake in another field can win.
            result.identity = openalex.resolve_author(
                name, domain, profile_text=result.profile.text
            )


def _author_works(run: Run, result: PipelineResult, openalex: OpenAlexClient) -> list[WorkRef]:
    works: list[WorkRef] = []
    if result.identity is None:
        return works
    with _stage(run, "author_works"), _tool(
        run, result.store, "fetch_author_works", result.identity.author_id
    ):
        works = openalex.fetch_author_works(result.identity.author_id, AUTHOR_WORKS_LIMIT)
    return works


# --- steps 3 and 4: the two extraction calls -------------------------------------------

def _brief(
    inputs: RunInputs,
    run: Run,
    result: PipelineResult,
    probe: ProbeResult | None,
    gemini: genai.Client | None,
    settings: Settings,
) -> None:
    with _stage(run, "grant_brief"):
        if result.grant is None:
            return
        answers = ""
        if probe is not None:
            answers = answers_brief(resolve_answers(probe, inputs.answers))
        with _tool(run, result.store, "llm_grant_brief", settings.model_fast):
            result.brief = grant_brief(
                result.grant, result.store, answers=answers, warn=run.warning,
                client=gemini, settings=settings,
            )


def _capabilities(
    run: Run,
    result: PipelineResult,
    works: list[WorkRef],
    gemini: genai.Client | None,
    settings: Settings,
) -> None:
    with _stage(run, "capabilities"):
        if result.profile is None:
            return
        with _tool(run, result.store, "llm_capabilities", settings.model_fast):
            result.capabilities = capabilities(
                result.profile, works, result.store, warn=run.warning,
                client=gemini, settings=settings,
            )


# --- step 5: candidates, with no literature in context ---------------------------------

def _candidates(
    run: Run, result: PipelineResult, gemini: genai.Client | None, settings: Settings
) -> Candidates | None:
    candidates = None
    with _stage(run, "candidates"):
        if result.brief is None or result.capabilities is None:
            run.warning(NO_CANDIDATES,
                        "cannot propose directions without both the brief and the profile")
            return None
        with _tool(run, result.store, "llm_candidates", settings.model_fast):
            candidates = candidate_directions(
                result.brief, result.capabilities, warn=run.warning,
                client=gemini, settings=settings,
            )
            if candidates is None:
                # The schema demands exactly 3 directions, so a short response loses the
                # whole stage. One Flash retry is ~3 s against a 6-minute budget.
                candidates = candidate_directions(
                    result.brief, result.capabilities, warn=run.warning,
                    client=gemini, settings=settings,
                )
    if candidates is None:
        run.warning(NO_CANDIDATES, "LLM #3 returned no usable directions after one retry")
    return candidates


# --- steps 6, 7a and 7b: the literature ------------------------------------------------

def _literature(
    run: Run, result: PipelineResult, openalex: OpenAlexClient, candidates: Candidates
) -> None:
    grant_ids = result.grant.evidence_ids if result.grant else []
    with _stage(run, "literature"):
        for candidate in candidates.directions:
            own: list[str] = []
            refs: list[WorkRef] = []
            for query in candidate.queries:
                with _tool(run, result.store, "search_literature", query):
                    found = openalex.search_literature(query, SEARCH_FROM_YEAR)
                refs.extend(found)
                own.extend(
                    row.id for row in result.store.all()[-1:] if row.source_type == "api_query"
                )
            with _tool(run, result.store, "fetch_top_works", candidate.title):
                own.extend(openalex.fetch_top_works(refs, n=PAPERS_PER_DIRECTION))

            # AC12: a numeric result for every direction, each with the row behind it.
            with _tool(run, result.store, "topic_trend", candidate.queries[0]):
                trend = openalex.topic_trend(candidate.queries[0], TREND_FROM_YEAR)
            with _tool(run, result.store, "citing_count", candidate.title):
                seed = max(refs, key=lambda r: r.cited_by_count).id if refs else ""
                citing = openalex.citing_count(seed, CITING_SINCE) if seed else Measure(value=0.0)
            result.trends.append(trend)
            result.citings.append(citing)
            own.extend(m.evidence_id for m in (trend, citing) if m.evidence_id)

            result.catalogues.append(
                DirectionEvidence(candidate=candidate, evidence_ids=[*grant_ids, *own])
            )


# --- step 8: the assessment, with the catalogue in context -----------------------------

def _assessment(
    run: Run, result: PipelineResult, gemini: genai.Client | None, settings: Settings
) -> None:
    with _stage(run, "assessment"):
        if not result.catalogues:
            return
        with _tool(run, result.store, "llm_assessment", settings.model_smart):
            result.directions = assess_directions(
                result.catalogues, result.store, warn=run.warning,
                client=gemini, settings=settings,
            )
    if not result.directions:
        run.warning(NO_ASSESSMENT, "LLM #4 produced no assessed directions")


# --- steps 9 and 10: ranking and the render, both without a model ----------------------

def _rank_and_render(inputs: RunInputs, run: Run, result: PipelineResult) -> None:
    """Two more stages, so they appear in the timeline like every other step."""
    grant_docs = [r for r in result.store.of_type("grant_doc") if r.sha256]
    with _stage(run, "ranking"):
        result.report = build_report(
            run.run_id,
            ReportInputs(
                grant_url=inputs.grant_src,
                profile_url=inputs.profile_url,
                grant_document=grant_docs[0].title.split(" — p.")[0] if grant_docs else None,
                grant_sha256=grant_docs[0].sha256 if grant_docs else None,
            ),
            result.directions,
            result.store,
            identity=result.identity,
        )
    with _stage(run, "report"):
        if result.report is not None:
            result.markdown = render_markdown(result.report, run.warnings())
