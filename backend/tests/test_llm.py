"""WI-1.6a — the structured call, the catalogue helpers, and LLM #1 / #2 (AC2, AC5, AC9).

Hermetic against `fixtures/llm/*.json`, recorded from real `gemini-3.8-flash` calls made
against the same hermetic store these tests rebuild — so the evidence IDs in the recorded
responses resolve here exactly as they did live.
"""

from __future__ import annotations

import inspect
import io
import pathlib
import re
import zipfile
from typing import Any

import httpx
import pytest

import tests.test_openalex as recorded_openalex
from roia.config import Settings
from roia.evidence import UNRESOLVABLE_EVIDENCE_ID, CitationContext, EvidenceStore
from roia.ingest import DocumentSet, ingest_grant, ingest_profile
from roia.llm import (
    LLM_FAILED,
    LLM_INVALID_OUTPUT,
    QUOTE_UNVERIFIED,
    candidate_directions,
    capabilities,
    grant_brief,
    serialize_catalogue,
    serialize_documents,
    structured,
    verify_quotes,
)
from roia.llm_schemas import CandidateDirection, Capabilities, CitesEvidence, GrantBrief
from roia.openalex import OpenAlexClient

F = pathlib.Path(__file__).resolve().parent.parent / "fixtures"
CRP_URL = "https://www.rgp.gov.sg/nrf-ar/crp"
PROFILE_URL = "https://basurafernando.github.io/"
ZIP_URL = (
    "https://assets.app.optical.gov.sg/rgp/production/published/base/pages/9/"
    "ee9b60cc-1ee9-4444-a2ba-327bd9b7fe56.zip?download="
)
#: What the applicant chose in the pre-flight probe (WI-1.4b).
ANSWERS = (
    "The applicant was asked about ambiguities in the call and answered:\n"
    "- This page lists 2 grant calls. Which one are you applying to?\n"
    "  -> 2026 Frontier CRP — 23 Mar 2026 (9am) to 18 May 2026 (4pm)"
)


class StubGemini:
    """Replays a recorded response and records the prompt it was given.

    ``raises`` and ``text=None`` stand in for the two failures the SDK actually produces:
    an exception, and a response with no text at all.
    """

    def __init__(self, text: str | None = "", *, raises: Exception | None = None) -> None:
        self.prompts: list[str] = []
        self.models = self
        self._text = text
        self._raises = raises

    def generate_content(self, *, model: str, contents: str, config: Any) -> Any:
        self.prompts.append(contents)
        self.schema = config.response_json_schema
        self.model = model
        if self._raises is not None:
            raise self._raises
        return type("Response", (), {"text": self._text})()


def zipped_grant() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("2026 F-CRP Launch Documents/F-CRP Call Information Sheet (2026).pdf",
                         (F / "grant.pdf").read_bytes())
    return buffer.getvalue()


@pytest.fixture
def http() -> httpx.Client:
    routes = {
        CRP_URL: httpx.Response(200, text=(F / "crp-page.html").read_text(),
                                headers={"content-type": "text/html"}),
        PROFILE_URL: httpx.Response(200, text=(F / "profile-page.html").read_text(),
                                    headers={"content-type": "text/html"}),
        ZIP_URL: httpx.Response(200, content=zipped_grant(),
                                headers={"content-type": "application/zip"}),
        "https://www.rgp.gov.sg/robots.txt": httpx.Response(200, text="User-Agent: *\nAllow: /\n"),
    }
    return httpx.Client(transport=httpx.MockTransport(
        lambda r: routes.get(str(r.url), httpx.Response(404))))


@pytest.fixture
def store() -> EvidenceStore:
    return EvidenceStore()


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, gemini_api_key="test-key")


@pytest.fixture
def warnings() -> list[tuple[str, str]]:
    return []


@pytest.fixture
def warn(warnings):
    return lambda code, message: warnings.append((code, message))


@pytest.fixture
def grant_documents(store, http) -> DocumentSet:
    return ingest_grant(CRP_URL, store, client=http, min_interval_s=0)


@pytest.fixture
def profile_documents(store, grant_documents, http) -> DocumentSet:
    """Ingested **after** the grant, as §5 steps 1 and 2 do it.

    Evidence IDs are sequential, so a recorded LLM response embeds the mint order it was
    recorded under. Ingesting the profile alone here would shift every ID and the recorded
    citations would silently fail to resolve.
    """
    return ingest_profile(PROFILE_URL, store, client=http, min_interval_s=0)


# --- structured() ----------------------------------------------------------------------

def test_structured_returns_a_validated_object(store, settings) -> None:
    stub = StubGemini((F / "llm" / "grant-brief.json").read_text())

    brief = structured(
        "prompt", GrantBrief, model="gemini-3.8-flash", client=stub, settings=settings
    )

    assert isinstance(brief, GrantBrief)
    assert stub.model == "gemini-3.8-flash"
    assert "$defs" in stub.schema, "nested models must reach the API as a real JSON schema"


def test_structured_drops_evidence_ids_that_do_not_resolve(store, settings, warn, warnings) -> None:
    """AC10a end to end: a fabricated ID never reaches the object the report is built from."""
    stub = StubGemini(
        '{"call_title": "X", "objectives": "Y", "requirements": '
        '[{"text": "t", "quote": "q", "evidence_ids": ["e1", "e999"]}], "criteria": []}'
    )
    store.mint(source_type="api_query", url="https://api/x", title="q", http_status=200)

    brief = structured(
        "prompt", GrantBrief, model="m", client=stub, settings=settings,
        context=CitationContext(store=store, warn=warn), warn=warn,
    )

    assert brief.requirements[0].evidence_ids == ["e1"]
    assert UNRESOLVABLE_EVIDENCE_ID in [c for c, _ in warnings]


@pytest.mark.parametrize(
    ("stub", "code"),
    [
        (StubGemini(raises=RuntimeError("upstream refused")), LLM_FAILED),
        (StubGemini(""), LLM_FAILED),
        (StubGemini(None), LLM_FAILED),
        (StubGemini('{"call_title": 3}'), LLM_INVALID_OUTPUT),
        (StubGemini("not json at all"), LLM_INVALID_OUTPUT),
    ],
)
def test_structured_never_raises_at_the_caller(stub, code, settings, warn, warnings) -> None:
    """AC9: a refusal, an empty body or a schema violation must degrade, not crash."""
    assert structured("p", GrantBrief, model="m", client=stub, settings=settings, warn=warn) is None
    assert [c for c, _ in warnings] == [code]


def test_structured_works_without_a_warn_callback(settings) -> None:
    """run.emit does not exist until WI-1.3; warn stays optional."""
    assert structured("p", GrantBrief, model="m", client=StubGemini(""), settings=settings) is None


# --- catalogue helpers ------------------------------------------------------------------

def test_serialize_catalogue_renders_citable_rows_and_skips_unknown_ids(store) -> None:
    query = store.mint(source_type="api_query", url="https://api/works?q=x", title="search",
                       http_status=200, summary="261 works match.")
    paper = store.mint(source_type="paper", url="https://openalex.org/W1", title="A real paper",
                       authors=["Yang Liu", "Guanbin Li"], year=2023,
                       summary="We propose a framework.", derived_from=query)

    rendered = serialize_catalogue([paper, "e999", query], store)

    assert f"[{paper}] paper (2023) — A real paper. Yang Liu, Guanbin Li" in rendered
    assert "We propose a framework." in rendered
    assert "e999" not in rendered, "an id we cannot resolve must not be offered for citation"


def test_serialize_documents_labels_each_pdf_page_with_its_own_row(
    grant_documents, store
) -> None:
    """The catalogue alone would give the model 400-char summaries; this gives full pages,
    still attributable to a row a reader can open."""
    rendered = serialize_documents(grant_documents, store)

    pdf = next(a for a in grant_documents.artefacts if a.kind == "pdf")
    for evidence_id in pdf.evidence_ids[:3]:
        assert f"[{evidence_id}] {store.get(evidence_id).title}" in rendered
    assert "conceptual novelty, originality and creativity of ideas" in rendered
    assert "23 Mar 2026" in rendered, "the page layer must survive into the prompt too"


def test_serialize_documents_is_empty_for_an_empty_document_set(store) -> None:
    assert serialize_documents(DocumentSet(source="x", policy="grant"), store) == ""


# --- quote verification (demo-spec §4: exact substring, log, never drop) ----------------

def test_verify_quotes_accepts_a_verbatim_quote_across_line_breaks() -> None:
    source = "Proposals will be assessed\non their conceptual novelty,\noriginality and creativity."

    assert verify_quotes([("q", "assessed on their conceptual novelty, originality")], source) == []


def test_verify_quotes_ignores_markup_we_added_ourselves() -> None:
    """pymupdf4llm emits **bold**; that markup was never in the document, so comparing a
    quote against it failed 7 of 16 real quotes on the demo call for no good reason."""
    source = "between a period of **3 to 5 years** . A stage-gated review"

    assert verify_quotes([("q", "between a period of 3 to 5 years")], source) == []


def test_verify_quotes_reports_a_stitched_quote_but_keeps_it(warn, warnings) -> None:
    """Log failures, never drop — removing the quote would hide the problem."""
    source = "Institutions should fulfil the following:\n- item one\n- item two"

    failed = verify_quotes([("req", "Institutions should fulfil the following: item one item two")],
                           source, warn=warn)

    assert failed == ["req"]
    assert [c for c, _ in warnings] == [QUOTE_UNVERIFIED]


# --- LLM #1 ------------------------------------------------------------------------------

def test_grant_brief_extracts_requirements_and_criteria_with_resolving_ids(
    grant_documents, store, settings, warn
) -> None:
    stub = StubGemini((F / "llm" / "grant-brief.json").read_text())

    brief = grant_brief(grant_documents, store, answers=ANSWERS, warn=warn,
                        client=stub, settings=settings)

    assert brief is not None
    assert len(brief.criteria) == 4 and len(brief.requirements) >= 8
    assert all(c.quote and c.evidence_ids for c in brief.criteria)
    for item in [*brief.requirements, *brief.criteria]:
        for evidence_id in item.evidence_ids:
            assert store.get(evidence_id).source_type == "grant_doc"


def test_ac14_the_applicants_chosen_call_reaches_the_grant_brief(
    grant_documents, store, settings
) -> None:
    """The demo page carries two calls with two different deadlines. Without the answers
    block the brief describes both; with it, LLM #1 locked onto the one the applicant chose."""
    stub = StubGemini((F / "llm" / "grant-brief.json").read_text())

    brief = grant_brief(grant_documents, store, answers=ANSWERS, client=stub, settings=settings)

    assert ANSWERS in stub.prompts[0], "the answers never reached the prompt"
    assert "Frontier" in brief.call_title
    assert "23 Mar 2026" in brief.call_period
    assert "CRP36" not in brief.call_period and "14 Sep 2026" not in brief.call_period


def test_grant_brief_reports_quotes_that_are_not_verbatim(
    grant_documents, store, settings, warn, warnings
) -> None:
    """The recorded response really does stitch three bullet lists into single quotes."""
    stub = StubGemini((F / "llm" / "grant-brief.json").read_text())

    brief = grant_brief(grant_documents, store, warn=warn, client=stub, settings=settings)

    unverified = [m for c, m in warnings if c == QUOTE_UNVERIFIED]
    assert len(unverified) == 3, "16 quotes, 3 stitched — reported, and still on the object"
    assert len(brief.requirements) + len(brief.criteria) == 16, "none were dropped"


def test_grant_brief_skips_the_call_when_nothing_was_ingested(store, settings, warn, warnings):
    stub = StubGemini("{}")

    assert grant_brief(DocumentSet(source="x", policy="grant"), store, warn=warn,
                       client=stub, settings=settings) is None
    assert stub.prompts == [], "a call with no documents is money spent on nothing"
    assert [c for c, _ in warnings] == [LLM_FAILED]


# --- LLM #2 ------------------------------------------------------------------------------

def test_capabilities_cites_the_profile_and_is_told_it_has_not_read_the_papers(
    profile_documents, store, settings, http
) -> None:
    openalex = OpenAlexClient(
        store, client=httpx.Client(transport=httpx.MockTransport(recorded_openalex.route)),
        settings=Settings(_env_file=None, openalex_api_key="k"), min_interval_s=0,
    )
    works = openalex.fetch_author_works("A5090467618", limit=40)
    stub = StubGemini((F / "llm" / "capabilities.json").read_text())

    caps = capabilities(profile_documents, works, store, client=stub, settings=settings)

    assert caps.researcher == "Basura Fernando"
    assert caps.methods and caps.domains
    assert all(e.evidence_ids for e in caps.expertise), "an ungrounded capability is a guess"
    for entry in caps.expertise:
        assert store.get(entry.evidence_ids[0]).source_type == "webpage"

    prompt = stub.prompts[0]
    assert "titles and years only" in prompt and "not read those papers" in prompt

    # The works section must be exactly one line per work — titles, years and citation
    # counts. fetch_author_works returns WorkRefs, which carry no abstract, and the prompt
    # must not imply otherwise.
    listing = [
        line for line in prompt.split("=========================================")[-1].splitlines()
        if line.strip()
    ]
    assert len(listing) == len(works)
    assert all(line.startswith("- ") and line.endswith("citations)") for line in listing)


def test_capabilities_skips_the_call_when_the_profile_was_unreachable(store, settings, warn):
    stub = StubGemini("{}")

    assert capabilities(DocumentSet(source="x", policy="profile"), [], store,
                        warn=warn, client=stub, settings=settings) is None
    assert stub.prompts == []


# --- live ---------------------------------------------------------------------------------

@pytest.mark.live
def test_live_grant_brief_and_capabilities_return_validated_objects(store) -> None:
    """The Done line: both calls return validated objects against the real inputs."""
    grant = ingest_grant(CRP_URL, store)
    profile = ingest_profile(PROFILE_URL, store)

    brief = grant_brief(grant, store, answers=ANSWERS)
    caps = capabilities(profile, [], store)

    assert isinstance(brief, GrantBrief) and isinstance(caps, Capabilities)
    assert brief.criteria and brief.requirements
    assert "23 Mar 2026" in brief.call_period, "AC14: the chosen call must win"
    assert all(store.get(i) for c in brief.criteria for i in c.evidence_ids)
    assert caps.researcher and caps.domains


# --- LLM #3: candidates only, no literature (WI-1.6b) -----------------------------------
#
# The single most important ordering constraint in the build. Call #3 must not see
# literature; call #4 must. Reversing it produces gaps asserted with nothing behind them.

#: Phrases that assert something about the state of a field. LLM #3 has been shown no
#: papers, so any of these in its output is a claim it cannot support.
#:
#: Word boundaries matter more than they look: a plain substring test for "gap" matches
#: **Singapore**, and this is a Singapore call, so every rationale mentions it. That false
#: positive cost a live test failure before it was spotted — the model was behaving.
LITERATURE_CLAIMS = (
    r"\bgaps?\b", r"under[- ]?explored", r"\bunexplored\b", r"no one has", r"nobody has",
    r"little work", r"has not been", r"remains open", r"emerging field", r"lack of research",
    r"few studies", r"\bliterature\b", r"prior work", r"state of the art", r"has yet to be",
)


def literature_claims_in(text: str) -> list[str]:
    return [pattern for pattern in LITERATURE_CLAIMS if re.search(pattern, text, re.I)]


@pytest.fixture
def brief_and_caps(store, grant_documents, profile_documents):
    context = CitationContext(store=store)
    return (
        GrantBrief.model_validate_json((F / "llm" / "grant-brief.json").read_text(),
                                       context=context),
        Capabilities.model_validate_json((F / "llm" / "capabilities.json").read_text(),
                                         context=context),
    )


def test_candidate_directions_returns_three_directions_and_nine_queries(
    brief_and_caps, settings
) -> None:
    brief, caps = brief_and_caps
    stub = StubGemini((F / "llm" / "candidates.json").read_text())

    candidates = candidate_directions(brief, caps, client=stub, settings=settings)

    assert len(candidates.directions) == 3
    assert sum(len(d.queries) for d in candidates.directions) == 9
    assert all(d.title and d.rationale for d in candidates.directions)
    assert len({d.title for d in candidates.directions}) == 3, "three phrasings of one is not three"


def test_rule3_no_literature_can_reach_the_prompt(brief_and_caps, store, settings) -> None:
    """Structural, not hopeful: there is no parameter through which papers could arrive.

    The store is full of papers and search results at this point in a real run, and none of
    it appears in the prompt, because the function cannot see the store at all.
    """
    brief, caps = brief_and_caps
    query = store.mint(source_type="api_query", url="https://api.openalex.org/works?q=x",
                       title="OpenAlex works search: causal video question answering",
                       http_status=200, summary="261 works match.")
    store.mint(source_type="paper", url="https://openalex.org/W4379929708",
               title="Cross-Modal Causal Relational Reasoning", derived_from=query,
               summary="Existing visual question answering methods suffer from spurious...")
    stub = StubGemini((F / "llm" / "candidates.json").read_text())

    candidate_directions(brief, caps, client=stub, settings=settings)

    prompt = stub.prompts[0]
    for row in [*store.of_type("paper"), *store.of_type("api_query")]:
        assert row.title not in prompt, f"{row.id} reached LLM #3"
        assert row.id not in prompt, f"{row.id} reached LLM #3"
        assert row.summary not in prompt
    assert "openalex.org" not in prompt

    parameters = set(inspect.signature(candidate_directions).parameters)
    assert parameters == {"brief", "caps", "warn", "client", "settings"}, (
        "a new parameter here is how literature gets into call #3 by accident"
    )


def test_rule3_the_schema_has_nowhere_to_put_a_claim_about_the_field() -> None:
    """No gap field, and nothing to cite — because nothing has been retrieved yet."""
    assert set(CandidateDirection.model_fields) == {"title", "rationale", "queries"}
    assert not issubclass(CandidateDirection, CitesEvidence), (
        "citing evidence here would mean there was evidence to cite, and there is not"
    )


def test_rule3_the_prompt_forbids_claims_about_the_field(brief_and_caps, settings) -> None:
    brief, caps = brief_and_caps
    stub = StubGemini((F / "llm" / "candidates.json").read_text())

    candidate_directions(brief, caps, client=stub, settings=settings)

    # The template wraps, so compare on squashed whitespace rather than raw text.
    prompt = re.sub(r"\s+", " ", stub.prompts[0].lower())
    assert "do not claim anything about the state of the literature" in prompt
    assert "you have not been shown any papers" in prompt
    assert "do not write that something is under-explored" in prompt


def test_rule3_the_recorded_response_makes_no_claim_about_the_field(
    brief_and_caps, settings
) -> None:
    """What the instruction is actually for. If a prompt change makes the model start
    asserting gaps here, this fails before the report ships one."""
    brief, caps = brief_and_caps
    stub = StubGemini((F / "llm" / "candidates.json").read_text())

    candidates = candidate_directions(brief, caps, client=stub, settings=settings)

    prose = " ".join(f"{d.title} {d.rationale}" for d in candidates.directions)
    assert literature_claims_in(prose) == []


def test_the_literature_claim_matcher_does_not_fire_on_singapore() -> None:
    """The demo call is a Singapore call, and "Singapore" contains "gap".

    A substring matcher here reports a violation on every single direction, which is both a
    false alarm and — worse — indistinguishable from the real thing.
    """
    assert literature_claims_in("Research of relevance to Singapore") == []
    assert literature_claims_in("This addresses a clear gap in the field") == [r"\bgaps?\b"]
    assert literature_claims_in("The literature has not been surveyed") == [
        r"has not been", r"\bliterature\b"
    ]


def test_queries_are_short_enough_to_return_results(brief_and_caps, settings) -> None:
    """OpenAlex title_and_abstract.search is conjunctive: "embodied AI assistant human
    action anticipation robot" returns zero works, "intent prediction human robot
    collaboration" returns 66. All nine recorded queries return a full page of 15."""
    brief, caps = brief_and_caps
    stub = StubGemini((F / "llm" / "candidates.json").read_text())

    candidates = candidate_directions(brief, caps, client=stub, settings=settings)

    for direction in candidates.directions:
        for query in direction.queries:
            assert 2 <= len(query.split()) <= 6, f"{query!r} will match nothing"
            assert not {"AND", "OR", "NOT"} & set(query.split())
            assert '"' not in query


def test_the_schema_requires_exactly_three_directions_with_three_queries_each(
    brief_and_caps, settings, warn, warnings
) -> None:
    """AC2 is 'exactly 3'. Two directions is a failed call, not a smaller report."""
    brief, caps = brief_and_caps
    stub = StubGemini(
        '{"directions": [{"title": "a", "rationale": "b", "queries": ["q1", "q2", "q3"]},'
        ' {"title": "c", "rationale": "d", "queries": ["q4", "q5", "q6"]}]}'
    )

    assert candidate_directions(brief, caps, warn=warn, client=stub, settings=settings) is None
    assert [c for c, _ in warnings] == [LLM_INVALID_OUTPUT]


@pytest.mark.live
def test_live_candidate_directions_returns_three_with_nine_queries(store, http) -> None:
    context = CitationContext(store=store)
    ingest_grant(CRP_URL, store, client=http, min_interval_s=0)
    ingest_profile(PROFILE_URL, store, client=http, min_interval_s=0)
    brief = GrantBrief.model_validate_json((F / "llm" / "grant-brief.json").read_text(),
                                           context=context)
    caps = Capabilities.model_validate_json((F / "llm" / "capabilities.json").read_text(),
                                            context=context)

    candidates = candidate_directions(brief, caps)

    assert candidates is not None
    assert len(candidates.directions) == 3
    assert sum(len(d.queries) for d in candidates.directions) == 9
    prose = " ".join(f"{d.title} {d.rationale}" for d in candidates.directions)
    assert literature_claims_in(prose) == [], "call #3 asserted something about the field"
