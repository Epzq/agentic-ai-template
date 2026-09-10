"""WI-1.4 — self-detecting ingestion, the three HTML layers, identity, and AC9.

Hermetic throughout: every fetch goes through an ``httpx.MockTransport`` serving the
recorded pages in ``fixtures/``. The two ``live`` tests re-check the same behaviour
against the real demo pair and are excluded from the default run.
"""

from __future__ import annotations

import hashlib
import io
import pathlib
import zipfile

import httpx
import pytest

from roia.evidence import EvidenceStore
from roia.ingest import (
    FETCH_FAILED,
    GRANT,
    IDENTITY_INPUTS_MISSING,
    PROFILE,
    THIN_EXTRACTION,
    UNSUPPORTED_TYPE,
    extract_identity,
    flight_text,
    ingest_grant,
    ingest_profile,
    ingest_source,
    rank_links,
)

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "fixtures"
GRANT_PDF = FIXTURES / "grant.pdf"
CRP_URL = "https://www.rgp.gov.sg/nrf-ar/crp"
PROFILE_URL = "https://basurafernando.github.io/"
ZIP_URL = (
    "https://assets.app.optical.gov.sg/rgp/production/published/base/pages/9/"
    "ee9b60cc-1ee9-4444-a2ba-327bd9b7fe56.zip?download="
)


@pytest.fixture
def warnings() -> list[tuple[str, str]]:
    return []


@pytest.fixture
def warn(warnings: list[tuple[str, str]]):
    return lambda code, message: warnings.append((code, message))


def zipped_grant() -> bytes:
    """The demo grant PDF inside a ZIP, as rgp.gov.sg actually serves it."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("2026 F-CRP Launch Documents/F-CRP Call Information Sheet (2026).pdf",
                         GRANT_PDF.read_bytes())
    return buffer.getvalue()


def make_client(routes: dict[str, httpx.Response]) -> httpx.Client:
    """Serve exactly these URLs; anything else is a 404, which is the interesting case."""

    def handler(request: httpx.Request) -> httpx.Response:
        return routes.get(str(request.url), httpx.Response(404, text="not found"))

    return httpx.Client(transport=httpx.MockTransport(handler))


# --- PDF ------------------------------------------------------------------------------

def test_local_pdf_mints_one_grant_doc_row_per_page(warn, warnings) -> None:
    """AC4: page 1..N, each carrying the document's real sha256."""
    store = EvidenceStore()

    documents = ingest_source(str(GRANT_PDF), GRANT, store, warn=warn, min_interval_s=0)

    rows = [store.get(eid) for eid in documents.evidence_ids]
    assert len(rows) == 21, "fixtures/grant.pdf is 21 pages"
    assert [r.page for r in rows] == list(range(1, 22))
    assert {r.source_type for r in rows} == {"grant_doc"}

    expected = hashlib.sha256(GRANT_PDF.read_bytes()).hexdigest()
    assert {r.sha256 for r in rows} == {expected}
    assert warnings == []
    assert "Frontier Competitive Research Programme".lower() in documents.text.lower()


def test_a_pdf_is_detected_by_content_type_not_extension(warn) -> None:
    """The CRP document links end '.pdf?download=' — endswith() finds nothing."""
    store = EvidenceStore()
    url = "https://example.org/download?id=9f3c-4a1b"  # no extension at all
    client = make_client({
        url: httpx.Response(200, content=GRANT_PDF.read_bytes(),
                            headers={"content-type": "application/pdf"})
    })

    documents = ingest_source(url, GRANT, store, warn=warn, client=client, min_interval_s=0)

    assert len(documents.evidence_ids) == 21
    assert store.get("e1").source_type == "grant_doc"


def test_a_corrupt_pdf_warns_and_does_not_raise(warn, warnings) -> None:
    store = EvidenceStore()
    url = "https://example.org/broken.pdf"
    client = make_client({
        url: httpx.Response(200, content=b"%PDF-1.7\nnot really",
                            headers={"content-type": "application/pdf"})
    })

    documents = ingest_source(url, GRANT, store, warn=warn, client=client, min_interval_s=0)

    assert documents.evidence_ids == []
    assert [c for c, _ in warnings] == [FETCH_FAILED]


# --- ZIP ------------------------------------------------------------------------------

def test_a_zip_is_unzipped_in_memory_and_its_pdfs_read(warn) -> None:
    """The real Call Information Sheet is inside a ZIP; stopping at the ZIP finds nothing."""
    store = EvidenceStore()
    client = make_client({
        ZIP_URL: httpx.Response(200, content=zipped_grant(),
                                headers={"content-type": "application/zip"})
    })

    documents = ingest_source(ZIP_URL, GRANT, store, warn=warn, client=client, min_interval_s=0)

    assert len(documents.evidence_ids) == 21
    row = store.get("e1")
    assert row.title.startswith("F-CRP Call Information Sheet (2026).pdf")
    # url stays the ZIP: that is the address the document was retrieved from.
    assert row.url == ZIP_URL
    assert row.sha256 == hashlib.sha256(GRANT_PDF.read_bytes()).hexdigest()


def test_the_profile_policy_refuses_to_unzip(warn, warnings) -> None:
    store = EvidenceStore()
    client = make_client({
        ZIP_URL: httpx.Response(200, content=zipped_grant(),
                                headers={"content-type": "application/zip"})
    })

    documents = ingest_source(ZIP_URL, PROFILE, store, warn=warn, client=client, min_interval_s=0)

    assert documents.evidence_ids == []
    assert [c for c, _ in warnings] == [UNSUPPORTED_TYPE]


def test_an_unsupported_type_warns_rather_than_failing(warn, warnings) -> None:
    store = EvidenceStore()
    url = "https://example.org/sheet.xlsx"
    client = make_client({
        url: httpx.Response(200, content=b"\x00\x01binary",
                            headers={"content-type": "application/vnd.ms-excel"})
    })

    ingest_source(url, GRANT, store, warn=warn, client=client, min_interval_s=0)

    assert [c for c, _ in warnings] == [UNSUPPORTED_TYPE]


# --- HTML layers ----------------------------------------------------------------------

def test_layer2_recovers_what_trafilatura_cannot_see() -> None:
    """The CRP call period lives only in the Next.js flight payload."""
    raw = (FIXTURES / "crp-page.html").read_text()

    text, links = flight_text(raw)

    assert "23 Mar 2026" in text and "18 May 2026" in text
    assert len(links) >= 6
    assert all(link.startswith("https://") for link in links)


def test_html_ingestion_merges_every_layer_and_follows_documents(warn, warnings) -> None:
    """No single source is complete: dates are page-only, criteria are PDF-only."""
    store = EvidenceStore()
    client = make_client({
        CRP_URL: httpx.Response(200, text=(FIXTURES / "crp-page.html").read_text(),
                                headers={"content-type": "text/html; charset=utf-8"}),
        ZIP_URL: httpx.Response(200, content=zipped_grant(),
                                headers={"content-type": "application/zip"}),
        "https://www.rgp.gov.sg/robots.txt": httpx.Response(200, text="User-Agent: *\nAllow: /\n"),
    })

    documents = ingest_grant(CRP_URL, store, warn=warn, client=client, min_interval_s=0)

    assert documents.final_url == CRP_URL
    assert documents.seed_html, "extract_identity has no other source for the page HTML"

    # Layer 2 gave the dates, which exist nowhere else...
    assert "23 Mar 2026" in documents.text
    # ...and the ZIP gave the evaluation criteria, which exist nowhere else.
    assert "breakthrough potential" in documents.text.lower()

    kinds = {store.get(eid).source_type for eid in documents.evidence_ids}
    assert kinds == {"webpage", "grant_doc"}
    assert len([a for a in documents.artefacts if a.kind == "pdf"]) == 1


def test_relative_hrefs_are_resolved_against_the_final_url(warn) -> None:
    """Without make_links_absolute, trafilatura emits URLs that were never on the page."""
    store = EvidenceStore()
    url = "https://example.org/lab/people/"
    page = (
        "<html><head><title>Lab</title></head><body>"
        f"<p>{'Some genuine page prose about the group and its work. ' * 20}</p>"
        '<a href="../research/index.html">Research</a>'
        "</body></html>"
    )
    target = "https://example.org/lab/research/index.html"
    client = make_client({
        url: httpx.Response(200, text=page, headers={"content-type": "text/html"}),
        target: httpx.Response(200, text="<html><body><p>Research page.</p></body></html>",
                               headers={"content-type": "text/html"}),
        "https://example.org/robots.txt": httpx.Response(404),
    })

    documents = ingest_profile(url, store, warn=warn, client=client, min_interval_s=0)

    assert [a.url for a in documents.artefacts] == [url, target]


def test_thin_extraction_is_reported(warn, warnings) -> None:
    """A page whose content only exists after JS must say so, not return silence."""
    store = EvidenceStore()
    url = "https://example.org/spa"
    client = make_client({
        url: httpx.Response(200, text="<html><body><div id='root'></div></body></html>",
                            headers={"content-type": "text/html"})
    })

    ingest_source(url, PROFILE, store, warn=warn, client=client, min_interval_s=0)

    assert THIN_EXTRACTION in [c for c, _ in warnings]


def test_empty_html_does_not_raise(warn, warnings) -> None:
    """lxml.html.fromstring('') raises ParserError; an empty 200 is a real CDN behaviour."""
    store = EvidenceStore()
    url = "https://example.org/empty"
    client = make_client({url: httpx.Response(200, text="", headers={"content-type": "text/html"})})

    documents = ingest_source(url, PROFILE, store, warn=warn, client=client, min_interval_s=0)

    assert documents.artefacts == []
    assert THIN_EXTRACTION in [c for c, _ in warnings]


def test_a_local_html_file_is_read_without_inventing_an_http_status(warn, warnings) -> None:
    """A file off disk was never fetched, so it must not be recorded as a fetched webpage."""
    store = EvidenceStore()
    path = FIXTURES / "profile-page.html"

    documents = ingest_source(str(path), PROFILE, store, warn=warn, min_interval_s=0)

    row = store.get("e1")
    assert row.source_type == "grant_doc", "nothing was fetched, so this is not a webpage (AC4)"
    assert row.http_status is None
    assert row.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert "Principal Scientist" in documents.text
    assert documents.seed_html


def test_a_fetched_page_records_its_real_status(warn) -> None:
    store = EvidenceStore()
    url = "https://example.org/"
    prose = f"<p>{'Real prose about the research group and its people. ' * 20}</p>"
    client = make_client({
        url: httpx.Response(200, text=f"<html><title>S</title><body>{prose}</body></html>",
                            headers={"content-type": "text/html"}),
        "https://example.org/robots.txt": httpx.Response(404),
    })

    ingest_profile(url, store, warn=warn, client=client, min_interval_s=0)

    row = store.get("e1")
    assert (row.source_type, row.http_status, row.url) == ("webpage", 200, url)


# --- link ranking ---------------------------------------------------------------------

def test_links_are_ranked_by_type_not_keyword() -> None:
    """rgp.gov.sg hrefs are opaque UUIDs, so keyword scoring finds nothing."""
    ranked = rank_links([
        "https://x/9f3c.docx?download=",
        "https://x/call-information-sheet.pdf",
        "https://x/1955a3df.pdf?download=",
        "https://x/708dad37.zip?download=",
    ])

    suffixes = [link.split("?")[0].rsplit(".", 1)[-1] for link in ranked]
    assert suffixes == ["zip", "pdf", "pdf", "docx"]


# --- policy ---------------------------------------------------------------------------

def test_profile_policy_follows_at_most_two_matching_same_site_pages(warn) -> None:
    store = EvidenceStore()
    url = "https://example.org/"
    prose = f"<p>{'Real prose about the research group and its people. ' * 20}</p>"
    page = (
        f"<html><head><title>Someone</title></head><body>{prose}"
        '<a href="/publications">Publications</a>'
        '<a href="/research">Research</a>'
        '<a href="/people">People</a>'
        '<a href="/contact">Contact</a>'
        '<a href="https://elsewhere.org/research">Elsewhere</a>'
        "</body></html>"
    )
    routes = {url: httpx.Response(200, text=page, headers={"content-type": "text/html"}),
              "https://example.org/robots.txt": httpx.Response(404)}
    for path in ("publications", "research", "people", "contact"):
        routes[f"https://example.org/{path}"] = httpx.Response(
            200, text=f"<html><body>{prose}</body></html>", headers={"content-type": "text/html"}
        )
    client = make_client(routes)

    documents = ingest_profile(url, store, warn=warn, client=client, min_interval_s=0)

    followed = [a.url for a in documents.artefacts[1:]]
    assert followed == ["https://example.org/publications", "https://example.org/research"]


def test_robots_txt_is_honoured_for_followed_links(warn, warnings) -> None:
    store = EvidenceStore()
    url = "https://example.org/"
    prose = f"<p>{'Real prose about the research group and its people. ' * 20}</p>"
    client = make_client({
        url: httpx.Response(
            200,
            text=f'<html><title>S</title><body>{prose}<a href="/research">R</a></body></html>',
            headers={"content-type": "text/html"},
        ),
        "https://example.org/research": httpx.Response(200, text=prose,
                                                       headers={"content-type": "text/html"}),
        "https://example.org/robots.txt": httpx.Response(
            200, text="User-agent: *\nDisallow: /research\n"
        ),
    })

    documents = ingest_profile(url, store, warn=warn, client=client, min_interval_s=0)

    assert len(documents.artefacts) == 1, "the disallowed page must not be fetched"
    assert "robots_disallowed" in [c for c, _ in warnings]


# --- AC9 ------------------------------------------------------------------------------

def test_a_404_warns_and_does_not_raise(warn, warnings) -> None:
    """AC9: an unreachable profile is a visible warning, never a crash."""
    store = EvidenceStore()
    client = make_client({})  # every URL 404s

    documents = ingest_profile("https://example.org/gone", store, warn=warn, client=client,
                               min_interval_s=0)

    assert documents.artefacts == []
    assert documents.evidence_ids == []
    assert [c for c, _ in warnings] == [FETCH_FAILED]
    assert "404" in warnings[0][1]


def test_a_connection_error_warns_and_does_not_raise(warn, warnings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("name resolution failed")

    store = EvidenceStore()
    client = httpx.Client(transport=httpx.MockTransport(handler))

    documents = ingest_profile("https://nope.invalid/", store, warn=warn, client=client,
                               min_interval_s=0)

    assert documents.artefacts == []
    assert [c for c, _ in warnings] == [FETCH_FAILED]


def test_a_missing_local_file_warns_and_does_not_raise(warn, warnings) -> None:
    store = EvidenceStore()

    documents = ingest_source("fixtures/does-not-exist.pdf", GRANT, store, warn=warn,
                              min_interval_s=0)

    assert documents.artefacts == []
    assert [c for c, _ in warnings] == [FETCH_FAILED]


def test_warnings_are_recorded_on_the_document_set_too(warn, warnings) -> None:
    """WI-1.4b's probe reuses the DocumentSet and needs to see what went wrong."""
    store = EvidenceStore()

    documents = ingest_source("fixtures/does-not-exist.pdf", GRANT, store, warn=warn,
                              min_interval_s=0)

    assert [w.code for w in documents.warnings] == [FETCH_FAILED]


def test_ingestion_works_with_no_warn_callback() -> None:
    """run.emit does not exist until WI-1.3; warn is optional and must stay optional."""
    store = EvidenceStore()

    documents = ingest_source("fixtures/does-not-exist.pdf", GRANT, store, min_interval_s=0)

    assert documents.warnings and documents.artefacts == []


# --- identity -------------------------------------------------------------------------

def test_extract_identity_on_the_demo_profile() -> None:
    """The frozen WI-0.0 profile must yield the name WI-1.5 resolves against."""
    raw = (FIXTURES / "profile-page.html").read_text()

    name, domain = extract_identity(raw, PROFILE_URL)

    assert name == "Basura Fernando"      # "(CFAR, IHPC, NTU)" stripped
    assert domain == "basurafernando.github.io"


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ("<title>Prof. Jane Roe | Somewhere University</title>", "Jane Roe"),
        ("<h1>Dr Ada Lovelace (Analytical Engines)</h1>", "Ada Lovelace"),
        ('<meta property="og:title" content="Alan Turing - Home">', "Alan Turing"),
        ("<title>A/Prof. Chen Wei &amp; Group</title>", "Chen Wei & Group"),
        # A hyphen inside a name is not a separator. This split at the first hyphen, so
        # `Jean-Baptiste Mouret` reached OpenAlex as `Jean` and step 2b resolved a
        # stranger — with the resulting applicant-fit scores written about them. The demo
        # pair has no hyphen in it, which is why nothing noticed.
        ("<title>Jean-Baptiste Mouret</title>", "Jean-Baptiste Mouret"),
        ("<title>Anne-Marie Kermarrec | EPFL</title>", "Anne-Marie Kermarrec"),
        ("<h1>Jean-Luc Starck - CEA Saclay</h1>", "Jean-Luc Starck"),
        ("<title>Wei-Shi Zheng — Sun Yat-sen University</title>", "Wei-Shi Zheng"),
    ],
)
def test_extract_identity_strips_roles_affiliations_and_trailing_titles(
    html: str, expected: str
) -> None:
    assert extract_identity(html, "https://www.example.org/x")[0] == expected


def test_extract_identity_warns_when_the_page_offers_no_name(warn, warnings) -> None:
    """Step 2b cannot run without a name, so the failure has to be visible."""
    name, domain = extract_identity("<html><body><p>nothing</p></body></html>",
                                    "https://lab.example.org/", warn=warn)

    assert name == ""
    assert domain == "lab.example.org"
    assert [c for c, _ in warnings] == [IDENTITY_INPUTS_MISSING]


# --- live -----------------------------------------------------------------------------

@pytest.mark.live
def test_live_grant_call_yields_the_dates_and_the_criteria() -> None:
    """The whole three-layer argument, against the real page."""
    store = EvidenceStore()

    documents = ingest_grant(CRP_URL, store)

    assert "23 Mar 2026" in documents.text, "layer 2 (flight payload) regressed"
    assert "breakthrough potential" in documents.text.lower(), "layer 3 (ZIP -> PDF) regressed"
    assert len([e for e in store.all() if e.source_type == "grant_doc"]) >= 20


@pytest.mark.live
def test_live_profile_yields_the_expected_identity() -> None:
    store = EvidenceStore()

    documents = ingest_profile(PROFILE_URL, store)

    assert documents.seed_html
    assert extract_identity(documents.seed_html, documents.final_url) == (
        "Basura Fernando",
        "basurafernando.github.io",
    )
