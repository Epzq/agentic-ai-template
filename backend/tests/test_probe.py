"""WI-1.4b — the pre-flight probe and its four deterministic detectors (AC14, AC9)."""

from __future__ import annotations

import ast
import io
import pathlib
import time
import zipfile

import httpx
import pytest

from roia.evidence import EvidenceStore
from roia.ingest import (
    ALL_CALLS,
    ALL_SCHEMES,
    CONTINUE,
    MULTIPLE_CALL_PERIODS,
    MULTIPLE_SCHEMES,
    NO_ELIGIBILITY_FOUND,
    THIN_PROFILE,
    DocumentSet,
    ProbeOption,
    ProbeQuestion,
    ProbeResult,
    answers_brief,
    build_questions,
    probe,
    probe_id_for,
    resolve_answers,
)

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "fixtures"
CRP_URL = "https://www.rgp.gov.sg/nrf-ar/crp"
PROFILE_URL = "https://basurafernando.github.io/"
ZIP_URL = (
    "https://assets.app.optical.gov.sg/rgp/production/published/base/pages/9/"
    "ee9b60cc-1ee9-4444-a2ba-327bd9b7fe56.zip?download="
)


def zipped_grant() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("2026 F-CRP Launch Documents/F-CRP Call Information Sheet (2026).pdf",
                         (FIXTURES / "grant.pdf").read_bytes())
    return buffer.getvalue()


@pytest.fixture
def seen() -> list[str]:
    """Every URL the probe requested — the evidence for 'zero LLM calls'."""
    return []


@pytest.fixture
def client(seen: list[str]) -> httpx.Client:
    routes = {
        CRP_URL: httpx.Response(200, text=(FIXTURES / "crp-page.html").read_text(),
                                headers={"content-type": "text/html; charset=utf-8"}),
        PROFILE_URL: httpx.Response(200, text=(FIXTURES / "profile-page.html").read_text(),
                                    headers={"content-type": "text/html; charset=utf-8"}),
        ZIP_URL: httpx.Response(200, content=zipped_grant(),
                                headers={"content-type": "application/zip"}),
        "https://www.rgp.gov.sg/robots.txt": httpx.Response(200, text="User-Agent: *\nAllow: /\n"),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return routes.get(str(request.url), httpx.Response(404, text="not found"))

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def result(client: httpx.Client) -> ProbeResult:
    return probe(CRP_URL, PROFILE_URL, EvidenceStore(), client=client, min_interval_s=0)


# --- AC14 -----------------------------------------------------------------------------

def test_ac14_the_crp_url_yields_a_question_naming_both_call_periods(
    result: ProbeResult,
) -> None:
    """The one thing retrieval genuinely cannot answer: which call the applicant means."""
    question = next(q for q in result.questions if q.code == MULTIPLE_CALL_PERIODS)
    labels = " | ".join(o.label for o in question.options)

    assert "CRP36" in labels and "14 Sep 2026" in labels
    assert "Frontier CRP" in labels and "23 Mar 2026" in labels
    assert result.detected["call_periods"] == [
        "CRP36 — 14 Sep 2026 (9am) to 9 Nov 2026 (4pm)",
        "2026 Frontier CRP — 23 Mar 2026 (9am) to 18 May 2026 (4pm)",
    ]
    assert question.default == ALL_CALLS, "skipping must always be allowed"


def test_ac14_the_probe_makes_no_network_call_beyond_the_two_inputs(
    result: ProbeResult, seen: list[str]
) -> None:
    """Zero LLM calls, demonstrated rather than asserted: these are the only hosts touched."""
    hosts = {httpx.URL(url).host for url in seen}

    assert hosts == {"www.rgp.gov.sg", "assets.app.optical.gov.sg", "basurafernando.github.io"}
    assert not any("googleapis" in url or "generativelanguage" in url for url in seen)


def test_ac14_ingest_module_imports_nothing_that_can_call_a_model() -> None:
    """Structural: the probe cannot make an LLM call because it cannot reach one."""
    tree = ast.parse((pathlib.Path("roia") / "ingest.py").read_text())
    imported = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imported |= {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert not [m for m in imported if "genai" in m or m in ("roia.llm", "google")]


def test_ac14_a_chosen_answer_reaches_the_grant_brief(result: ProbeResult) -> None:
    """The answer is an input to LLM #1, not an invisible side channel."""
    frontier = next(
        o for q in result.questions if q.code == MULTIPLE_CALL_PERIODS
        for o in q.options if "Frontier" in o.label
    )

    answers = resolve_answers(result, {MULTIPLE_CALL_PERIODS: frontier.value})
    brief = answers_brief(answers)

    chosen = next(a for a in answers if a.code == MULTIPLE_CALL_PERIODS)
    assert chosen.answered is True
    assert chosen.label == frontier.label
    assert "23 Mar 2026" in brief
    assert "default applied" not in brief.split("\n")[1]


@pytest.mark.live
def test_ac14_live_probe_completes_inside_twenty_seconds() -> None:
    """AC14's budget, against the real pair. Measured at ~17.5 s on a home connection."""
    started = time.monotonic()

    result = probe(CRP_URL, PROFILE_URL, EvidenceStore())

    elapsed = time.monotonic() - started
    assert elapsed < 20, f"probe took {elapsed:.1f}s; AC14 allows 20"
    assert len(result.detected["call_periods"]) == 2


# --- evidence-bearing -----------------------------------------------------------------

def test_every_detected_option_points_at_a_stored_record(client: httpx.Client) -> None:
    """A detection the run cannot trace back is a claim, not evidence."""
    store = EvidenceStore()

    result = probe(CRP_URL, PROFILE_URL, store, client=client, min_interval_s=0)

    options = [o for q in result.questions for o in q.options if o.evidence_ids]
    assert options, "no option carried provenance"
    for option in options:
        for evidence_id in option.evidence_ids:
            assert store.get(evidence_id) is not None, f"{option.label} cites {evidence_id}"


def test_a_match_inside_a_pdf_is_attributed_to_its_own_page() -> None:
    """Attributing to 'the PDF' would be useless; the row must name the page it is on.

    ``_read_pdf`` writes a ``[p.N]`` marker ahead of each page, so the nearest preceding
    marker is what turns a character offset back into the evidence row a reader can open.
    """
    from roia.ingest import Artefact

    store = EvidenceStore()
    ids = [
        store.mint(source_type="grant_doc", url="https://x/call.zip",
                   title=f"call.pdf — p. {n}", page=n, sha256="a" * 64)
        for n in (1, 2, 3)
    ]
    grant = DocumentSet(source="x", policy="grant", artefacts=[Artefact(
        kind="pdf", name="call.pdf", url="https://x/call.zip", evidence_ids=ids,
        text=("[p.1] Introduction to the programme. Eligibility applies.\n\n"
              "[p.2] T-CRP is a sub-category of the CRP.\n\n"
              "[p.3] F-CRP funding scheme for smaller programmes."),
    )])

    questions, _ = build_questions(grant, _documents("y" * 900, "profile"), store)

    scheme = next(q for q in questions if q.code == MULTIPLE_SCHEMES)
    pages = {o.label: store.get(o.evidence_ids[0]).page for o in scheme.options if o.evidence_ids}
    assert pages == {"T-CRP": 2, "F-CRP": 3}


# --- the four detectors ---------------------------------------------------------------

def _documents(text: str, policy: str = "grant") -> DocumentSet:
    from roia.ingest import Artefact

    return DocumentSet(
        source="x", policy=policy,
        artefacts=[Artefact(kind="html", name="page", url="https://x/", text=text)],
    )


def test_one_call_period_asks_nothing() -> None:
    """Never ask what is not ambiguous."""
    grant = _documents("F-CRP Grant Call Period: 23 Mar 2026 to 18 May 2026. Eligibility: IHLs.")

    questions, detected = build_questions(grant, _documents("x" * 900, "profile"), EvidenceStore())

    assert [q.code for q in questions] == []
    assert detected["call_periods"] == ["F-CRP — 23 Mar 2026 to 18 May 2026"]


def test_multiple_schemes_fires_only_on_scheme_shaped_acronyms() -> None:
    """A bare acronym scan returns PI, NRF, NUS and NTU — noise, and a pointless question."""
    grant = _documents(
        "The NRF CRP funding scheme, run by NRF with NUS and NTU. Each PI must apply. "
        "T-CRP is a sub-category of the CRP. F-CRP is a sub-category of the CRP. "
        "Eligibility applies."
    )

    questions, detected = build_questions(grant, _documents("y" * 900, "profile"), EvidenceStore())

    assert detected["schemes"] == ["T-CRP", "F-CRP"]
    assert [q.code for q in questions] == [MULTIPLE_SCHEMES]
    assert questions[0].default == ALL_SCHEMES


def test_thin_profile_fires_below_six_hundred_chars() -> None:
    grant = _documents("Grant Call Period: 1 Jan 2026 to 2 Feb 2026. Eligibility: anyone.")

    questions, detected = build_questions(grant, _documents("short", "profile"), EvidenceStore())

    assert [q.code for q in questions] == [THIN_PROFILE]
    assert detected["profile_chars"] == len("## page\nshort")
    assert questions[0].default == CONTINUE


def test_no_eligibility_found_fires_when_nothing_readable_mentions_it() -> None:
    grant = _documents("A programme about research. Grant Call Period: 1 Jan to 2 Feb 2026.")

    questions, detected = build_questions(grant, _documents("z" * 900, "profile"), EvidenceStore())

    assert [q.code for q in questions] == [NO_ELIGIBILITY_FOUND]
    assert detected["eligibility_found"] is False


def test_an_unreachable_profile_is_caught_before_the_run_starts(seen: list[str]) -> None:
    """AC9, moved earlier: a dead profile URL becomes a question, not a failed run."""
    routes = {CRP_URL: httpx.Response(200, text=(FIXTURES / "crp-page.html").read_text(),
                                      headers={"content-type": "text/html"})}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return routes.get(str(request.url), httpx.Response(404))

    result = probe(CRP_URL, "https://nowhere.example/gone", EvidenceStore(),
                   client=httpx.Client(transport=httpx.MockTransport(handler)), min_interval_s=0)

    assert THIN_PROFILE in [q.code for q in result.questions]
    assert "fetch_failed" in [w.code for w in result.warnings]


# --- answers --------------------------------------------------------------------------

def _one_question() -> ProbeResult:
    return ProbeResult(
        probe_id="pb_test",
        questions=[ProbeQuestion(
            code=MULTIPLE_CALL_PERIODS,
            question="Which call?",
            options=[ProbeOption(value="f_crp", label="F-CRP", evidence_ids=["e1"]),
                     ProbeOption(value=ALL_CALLS, label="Whole programme")],
            default=ALL_CALLS,
        )],
    )


def test_skipping_applies_the_default_and_says_so() -> None:
    """The run must never block for an answer."""
    answers = resolve_answers(_one_question(), None)

    assert (answers[0].value, answers[0].answered) == (ALL_CALLS, False)
    assert "default applied" in answers_brief(answers)


def test_an_answer_we_never_offered_falls_back_to_the_default() -> None:
    answers = resolve_answers(_one_question(), {MULTIPLE_CALL_PERIODS: "'; DROP TABLE --"})

    assert (answers[0].value, answers[0].answered) == (ALL_CALLS, False)


def test_answers_brief_is_empty_when_nothing_was_asked() -> None:
    assert answers_brief(resolve_answers(ProbeResult(probe_id="pb_x"), None)) == ""


# --- the API payload ------------------------------------------------------------------

def test_probe_id_is_stable_per_input_pair() -> None:
    """WI-2.1 caches by input hash, so the same inputs must give the same id."""
    assert probe_id_for(CRP_URL, PROFILE_URL) == probe_id_for(CRP_URL, PROFILE_URL)
    assert probe_id_for(CRP_URL, PROFILE_URL) != probe_id_for(CRP_URL, "https://other.example/")


def test_model_dump_is_the_api_payload_and_carries_no_document_text(
    result: ProbeResult,
) -> None:
    """~100k chars of grant text must not be serialised to the browser."""
    payload = result.model_dump()

    assert set(payload) == {"probe_id", "detected", "questions", "warnings"}
    assert result.grant is not None and len(result.grant.text) > 20_000
    assert "Frontier Competitive Research" not in result.model_dump_json()
    assert len(result.model_dump_json()) < 20_000
