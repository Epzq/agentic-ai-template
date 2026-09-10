"""WI-1.5 — author resolution, literature retrieval, and the two measurements (AC4, AC11, AC12).

Hermetic against `fixtures/openalex/*.json`, recorded live on 2026-09-05. The routing key is
the request path plus its `filter`, so a test fails loudly if the client changes the query
it sends rather than silently matching the wrong fixture.
"""

from __future__ import annotations

import json
import pathlib
from datetime import date

import httpx
import pytest

from roia.config import Settings
from roia.evidence import EvidenceStore
from roia.openalex import (
    AUTHOR_UNRESOLVED,
    OPENALEX_FAILED,
    THIN_LITERATURE,
    OpenAlexClient,
    WorkRef,
    _abstract,
)

OA = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "openalex"
PROFILE_TEXT = (
    "Basura Fernando. Research interests: visual reasoning, action prediction, action "
    "recognition, transfer learning, embodied AI. Multimodal machine learning applications."
)


def load(name: str) -> dict:
    return json.loads((OA / f"{name}.json").read_text())


def route(request: httpx.Request) -> httpx.Response:
    """Serve a recorded payload for the query this request actually asks for."""
    url = request.url
    path = url.path
    filt = url.params.get("filter", "")

    if url.host == "api.ror.org":
        return httpx.Response(200, json={"number_of_results": 0, "items": []})
    if path.startswith("/works/"):
        name = f"work-{path.rsplit('/', 1)[-1]}"
        if (OA / f"{name}.json").exists():
            return httpx.Response(200, json=load(name))
        return httpx.Response(404, json={"error": "not found"})
    if path == "/authors":
        if "Zzqx" in filt or "Nobody" in filt:
            return httpx.Response(200, json=load("authors-empty"))
        return httpx.Response(200, json=load("authors-search"))
    if path == "/works":
        if "group_by" in dict(url.params):
            return httpx.Response(200, json=load("trend-group-by-year"))
        if filt.startswith("cites:"):
            return httpx.Response(200, json=load("citing-count"))
        if filt.startswith("author.id:"):
            return httpx.Response(200, json=load("author-works"))
        if "qzzxwv" in filt:
            return httpx.Response(200, json=load("works-empty"))
        if "knowledge graph grounded" in filt:
            return httpx.Response(200, json=load("works-search-thin"))
        return httpx.Response(200, json=load("works-search"))
    return httpx.Response(404, json={"error": f"unrouted {path}"})


@pytest.fixture
def warnings() -> list[tuple[str, str]]:
    return []


@pytest.fixture
def events() -> list[tuple[str, dict]]:
    return []


@pytest.fixture
def store() -> EvidenceStore:
    return EvidenceStore()


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, openalex_api_key="test-key", openalex_mailto="t@example.org")


@pytest.fixture
def client(store, warnings, events, settings) -> OpenAlexClient:
    return OpenAlexClient(
        store,
        warn=lambda c, m: warnings.append((c, m)),
        emit=lambda t, p: events.append((t, p)),
        client=httpx.Client(transport=httpx.MockTransport(route)),
        settings=settings,
        min_interval_s=0,
    )


# --- AC4: provenance ------------------------------------------------------------------

def test_every_call_mints_an_api_query_row_carrying_url_and_status(client, store) -> None:
    client.search_literature("causal video question answering", 2022)
    client.topic_trend("causal video question answering", 2019)
    client.citing_count("W4379929708", date(2023, 1, 1))

    rows = store.of_type("api_query")
    assert len(rows) == 3
    for row in rows:
        assert row.url.startswith("https://api.openalex.org/")
        assert row.http_status == 200


def test_a_failed_request_is_not_minted_as_a_measurement_of_zero(store, settings, warnings) -> None:
    """The project's rule is that finding nothing means *don't know*, never *nobody has done
    this*. Every summary here was computed from `payload or {}`, so a 404 or a timeout minted
    an evidence row reading "0 works match", "No works matched", "0 works … cite W123" — and
    LLM #4 is handed those as citable numbers about the state of the field.
    """
    dead = OpenAlexClient(
        store,
        warn=lambda code, message: warnings.append((code, message)),
        client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404))),
        settings=settings,
        min_interval_s=0,
    )
    try:
        dead.search_literature("some topic", 2022)
        trend = dead.topic_trend("some topic", 2019)
        citing = dead.citing_count("W1", date(2023, 1, 1))
    finally:
        dead.close()

    rows = store.of_type("api_query")
    assert len(rows) == 3, "the failed request is still recorded — that part was right"
    for row in rows:
        assert "not a measurement of zero" in row.summary
        assert "0 works match" not in row.summary
        assert "No works matched" not in row.summary
        assert row.http_status != 200
    assert "not a measurement of zero" in trend.detail
    assert "not a measurement of zero" in citing.detail
    assert THIN_LITERATURE not in [code for code, _ in warnings], (
        "a failed request says nothing about how thin the literature is"
    )


def test_the_api_key_never_reaches_an_evidence_row(client, store) -> None:
    """The request URL goes straight into the report; a leaked credential is worse than a
    missing link."""
    client.search_literature("causal video question answering", 2022)

    assert store.of_type("api_query")
    for row in store.all():
        assert "api_key" not in (row.url or "")
        assert "test-key" not in (row.url or "")


def test_every_paper_row_derives_from_the_query_that_found_it(client, store) -> None:
    refs = client.search_literature("causal video question answering", 2022)
    query_row = store.of_type("api_query")[0]

    ids = client.fetch_top_works(refs, n=3)

    papers = [store.get(i) for i in ids]
    assert papers and all(p.source_type == "paper" for p in papers)
    assert {p.derived_from for p in papers} == {query_row.id}
    assert all(p.summary and p.year and p.authors for p in papers)


# --- AC11: only get_work mints papers --------------------------------------------------

def test_search_literature_mints_no_paper_rows(client, store) -> None:
    """A search hit has no abstract, so nothing may claim to have read it."""
    refs = client.search_literature("causal video question answering", 2022)

    assert len(refs) == 15
    assert store.of_type("paper") == []
    assert isinstance(refs[0], WorkRef)
    assert refs[0].cited_by_count >= refs[-1].cited_by_count


#: Recorded live: 3 of the 15 hits for this query have no abstract_inverted_index at all —
#: 20% of a real result page. Minting them as papers would claim a reading that never
#: happened; taking the top n blind would silently under-deliver on AC11.
NO_ABSTRACT = {"W4296122945", "W4321332401", "W4220861052"}


def test_the_recorded_page_still_exercises_the_missing_abstract_hazard() -> None:
    """Guards the two tests below: if OpenAlex backfills these, they stop proving anything."""
    without = {
        wid for wid in (w["id"].rsplit("/", 1)[-1] for w in load("works-search")["results"])
        if not load(f"work-{wid}").get("abstract_inverted_index")
    }
    assert without == NO_ABSTRACT


def test_fetch_top_works_skips_records_that_have_no_abstract(client, store) -> None:
    """Asking for 12 from a page where 3 records are abstract-less must still return 12."""
    refs = client.search_literature("causal video question answering", 2022)

    ids = client.fetch_top_works(refs, n=12)

    minted = {store.get(i).url.rsplit("/", 1)[-1] for i in ids}
    assert len(ids) == 12, "under-delivering here is how AC11 silently fails"
    assert not (minted & NO_ABSTRACT)
    assert all(store.get(i).summary for i in ids)


def test_fetch_top_works_delivers_the_requested_count(client, store) -> None:
    refs = client.search_literature("causal video question answering", 2022)

    ids = client.fetch_top_works(refs, n=4)

    assert len(ids) == 4
    assert len(store.of_type("paper")) == 4


def test_fetch_top_works_reports_when_it_cannot_reach_the_target(client, warnings) -> None:
    refs = client.search_literature("causal video question answering", 2022)

    client.fetch_top_works(refs[:1], n=4)

    assert THIN_LITERATURE in [c for c, _ in warnings]


def test_fetch_top_works_ranks_by_citations_and_dedupes(client, store) -> None:
    refs = client.search_literature("causal video question answering", 2022)
    duplicated = [*refs, *refs]

    ids = client.fetch_top_works(duplicated, n=2)

    papers = [store.get(i) for i in ids]
    assert len(ids) == 2
    assert papers[0].title.startswith("Cross-Modal Causal Relational Reasoning")


# --- AC12: the two measurements --------------------------------------------------------

def test_topic_trend_returns_a_number_and_the_row_behind_it(client, store) -> None:
    measure = client.topic_trend("causal video question answering", 2019)

    assert measure.value == 309
    assert "2019 11" in measure.detail and "2025 58" in measure.detail
    assert store.get(measure.evidence_id).source_type == "api_query"


def test_citing_count_returns_a_number_and_the_row_behind_it(client, store) -> None:
    measure = client.citing_count("https://openalex.org/W4379929708", date(2023, 1, 1))

    assert measure.value == 154
    assert "154 works" in measure.detail
    assert store.get(measure.evidence_id) is not None


# --- identity --------------------------------------------------------------------------

def test_resolve_author_ranks_without_filtering_on_institution(client, events) -> None:
    """Filtering on last_known_institutions.ror excluded a 417-work researcher live."""
    match = client.resolve_author("Basura Fernando", "basurafernando.github.io",
                                  profile_text=PROFILE_TEXT)

    assert match is not None
    assert match.author_id.endswith("A5090467618")
    assert match.works_count == 189
    assert match.confidence == "unverified", "disambiguation is a non-goal (§4)"
    assert events == [("identity.resolved", {
        "author_id": match.author_id,
        "display_name": "Basura Fernando",
        "institution": match.institution,
        "confidence": "unverified",
        "margin": match.margin,
    })]


def test_resolve_author_handles_the_empty_name_extract_identity_can_return(
    client, warnings, store
) -> None:
    """extract_identity returns ("", domain) when a page offers no name — not an error here."""
    assert client.resolve_author("", "example.org") is None
    assert [c for c, _ in warnings] == [AUTHOR_UNRESOLVED]
    assert len(store) == 0, "a lookup we never made must not mint a row"


def test_resolve_author_returns_none_when_openalex_knows_nobody(client, warnings, store) -> None:
    assert client.resolve_author("Zzqx Nobody", "example.org") is None
    assert AUTHOR_UNRESOLVED in [c for c, _ in warnings]
    assert len(store.of_type("api_query")) == 1, "the failed search is still evidence"


def test_fetch_author_works_returns_refs_not_papers(client, store) -> None:
    refs = client.fetch_author_works("https://openalex.org/A5090467618", limit=40)

    assert len(refs) == 40
    assert store.of_type("paper") == []
    assert all(r.derived_from == store.of_type("api_query")[0].id for r in refs)


# --- AC9: empty-result safety ----------------------------------------------------------

def test_a_nonsense_query_completes_without_raising(client, store, warnings) -> None:
    refs = client.search_literature("qzzxwv nonsense terms nobody wrote", 2022)

    assert refs == []
    assert THIN_LITERATURE in [c for c, _ in warnings]
    assert len(store.of_type("api_query")) == 1, "a zero-result search is still evidence"


def test_thin_literature_fires_below_five_hits_but_not_above(client, warnings) -> None:
    client.search_literature("knowledge graph grounded video question answering", 2022)

    assert warnings == [], "22 hits is thin but not below the floor"


def test_a_server_error_is_retried_then_reported_never_raised(store, settings) -> None:
    attempts: list[str] = []

    def flaky(request: httpx.Request) -> httpx.Response:
        attempts.append(str(request.url))
        return httpx.Response(503, text="upstream is having a day")

    warnings: list[tuple[str, str]] = []
    client = OpenAlexClient(
        store, warn=lambda c, m: warnings.append((c, m)),
        client=httpx.Client(transport=httpx.MockTransport(flaky)),
        settings=settings, min_interval_s=0,
    )

    refs = client.search_literature("anything", 2022)

    assert refs == []
    assert len(attempts) == 3, "tenacity should retry a 5xx, three attempts total"
    assert OPENALEX_FAILED in [c for c, _ in warnings]


def test_a_rate_limit_is_retried_and_succeeds_on_the_second_attempt(store, settings) -> None:
    attempts: list[str] = []

    def throttled(request: httpx.Request) -> httpx.Response:
        attempts.append(str(request.url))
        if len(attempts) == 1:
            return httpx.Response(429, text="slow down")
        return route(request)

    client = OpenAlexClient(
        store, client=httpx.Client(transport=httpx.MockTransport(throttled)),
        settings=settings, min_interval_s=0,
    )

    refs = client.search_literature("causal video question answering", 2022)

    assert len(attempts) == 2 and len(refs) == 15


def test_measurements_return_zero_rather_than_indexing_into_nothing(store, settings) -> None:
    client = OpenAlexClient(
        store,
        client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))),
        settings=settings, min_interval_s=0,
    )

    trend = client.topic_trend("anything", 2019)
    citing = client.citing_count("W1", date(2023, 1, 1))

    assert (trend.value, citing.value) == (0.0, 0.0)
    assert trend.evidence_id is not None and citing.evidence_id is not None


def test_a_malformed_author_record_does_not_crash_the_lookup(store, settings) -> None:
    """A candidate with no id is unusable, but must not be an exception."""
    warnings: list[tuple[str, str]] = []
    client = OpenAlexClient(
        store, warn=lambda c, m: warnings.append((c, m)),
        client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(
            200, json={"meta": None, "results": [{"works_count": 5, "topics": [{}]}]}
        ))),
        settings=settings, min_interval_s=0,
    )

    assert client.resolve_author("Someone", "") is None
    assert AUTHOR_UNRESOLVED in [c for c, _ in warnings]


def test_a_malformed_trend_group_does_not_crash_the_measurement(store, settings) -> None:
    client = OpenAlexClient(
        store,
        client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(
            200, json={"group_by": [{"key": "2024"}, {"key": "unknown", "count": 3}]}
        ))),
        settings=settings, min_interval_s=0,
    )

    measure = client.topic_trend("anything", 2019)

    assert measure.value == 0.0 and "2024 0" in measure.detail


def test_abstract_reconstruction_handles_a_missing_index() -> None:
    assert _abstract({}) == ""
    assert _abstract({"abstract_inverted_index": None}) == ""
    assert _abstract({"abstract_inverted_index": {"Hello": [1], "world": [0]}}) == "world Hello"


# --- live ------------------------------------------------------------------------------

@pytest.mark.live
def test_live_three_directions_mint_at_least_twelve_paper_rows() -> None:
    """AC11 against the real API: 3 directions × 4 works, all with abstracts."""
    store = EvidenceStore()
    client = OpenAlexClient(store)
    queries = [
        "causal video question answering",
        "intent prediction human robot collaboration",
        "knowledge graph grounded video question answering",
    ]
    try:
        for query in queries:
            refs = client.search_literature(query, 2022)
            client.fetch_top_works(refs, n=4)
            client.topic_trend(query, 2019)
            if refs:
                client.citing_count(refs[0].id, date(2023, 1, 1))
    finally:
        client.close()

    papers = store.of_type("paper")
    assert len(papers) >= 12, f"AC11 needs 12 paper rows, got {len(papers)}"
    assert len({p.url for p in papers}) == len(papers), "papers must be distinct"
    assert all(p.summary and p.derived_from for p in papers)
    assert all(store.get(p.derived_from).source_type == "api_query" for p in papers)


@pytest.mark.live
def test_live_resolve_author_finds_the_frozen_demo_researcher() -> None:
    store = EvidenceStore()
    client = OpenAlexClient(store)
    try:
        match = client.resolve_author("Basura Fernando", "basurafernando.github.io",
                                      profile_text=PROFILE_TEXT)
    finally:
        client.close()

    assert match is not None
    assert match.author_id.endswith("A5090467618")
    assert match.works_count >= 20, "WI-0.0's gate"
