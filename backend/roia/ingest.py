"""Ingestion — one self-detecting function for both inputs.

The user pastes a URL or points at a file and never says what it is. ``ingest_source``
dispatches on **``Content-Type``, never on the file extension**: the CRP page's document
links all end ``…pdf?download=``, so extension matching finds zero PDFs on a page that has
seven.

HTML is read in three layers, because no single one is complete. On the demo grant call the
call *dates* exist only in the Next.js flight payload (layer 2, invisible to trafilatura),
while the objectives, eligibility, evaluation criteria and budget exist only inside a PDF
that is inside a ZIP (layer 3). Layers 1-3 are ported from ``spikes/probe_grant_url.py``,
which is the verified reference for exactly this page.

Recovering a framework's own JSON payload is *parsing*, not *rendering* — it needs no
browser and does not touch the no-Playwright non-goal (``demo-spec.md`` §4).

Nothing here raises at the caller. Every failure becomes ``warn(code, message)`` and an
empty or partial result, because a run that dies on one unreachable link is worse than a
run that reports it (AC9).
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import time
import urllib.parse
import urllib.robotparser
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path
from typing import Any, Literal, cast

import httpx
import lxml.html
import pymupdf
import pymupdf4llm
import trafilatura
from lxml.etree import ParserError
from pydantic import BaseModel, Field

from roia.evidence import EvidenceStore, WarnFn

# --- warning codes --------------------------------------------------------------------
FETCH_FAILED = "fetch_failed"
UNSUPPORTED_TYPE = "unsupported_type"
THIN_EXTRACTION = "thin_extraction"
IDENTITY_INPUTS_MISSING = "identity_inputs_missing"
ROBOTS_DISALLOWED = "robots_disallowed"
EVIDENCE_REJECTED = "evidence_rejected"

# --- thresholds, all from demo-spec.md §5 ---------------------------------------------
#: Below this much recovered text the page is probably JS-rendered and we say so.
MIN_EXTRACTED_CHARS = 600
#: …or the text is a rounding error against the markup that carried it.
MIN_TEXT_HTML_RATIO = 0.01
#: One request per second per host. Politeness, not configuration.
REQUEST_INTERVAL_S = 1.0
FETCH_TIMEOUT_S = 90.0
#: What a chip hover shows; the store truncates anyway, this just avoids the round trip.
SUMMARY_CHARS = 400

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)

_DOCUMENT_SUFFIXES = (".zip", ".pdf", ".docx", ".doc")


@dataclass(frozen=True)
class IngestPolicy:
    """The only thing that differs between the two inputs (``demo-spec.md`` §5)."""

    name: str
    #: ``documents`` follows pdf/zip/docx links; ``pages`` follows same-site HTML.
    follow: Literal["documents", "pages"]
    max_artefacts: int
    unzip: bool
    #: Same-site paths worth following, for ``follow="pages"``.
    path_pattern: re.Pattern[str] | None = None


GRANT = IngestPolicy(name="grant", follow="documents", max_artefacts=6, unzip=True)
PROFILE = IngestPolicy(
    name="profile",
    follow="pages",
    max_artefacts=2,
    unzip=False,
    path_pattern=re.compile(r"/(publication|research|people)", re.I),
)


class Artefact(BaseModel):
    """One thing we actually fetched and read."""

    kind: Literal["html", "pdf"]
    name: str
    url: str
    text: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


class IngestWarning(BaseModel):
    code: str
    message: str


class DocumentSet(BaseModel):
    """Everything one input yielded, across every layer.

    Carried into the run so WI-1.4b's probe and the pipeline share one ingestion rather
    than fetching the same seven PDFs twice.
    """

    source: str
    policy: str
    final_url: str | None = None
    #: The seed page's raw HTML — ``extract_identity`` needs it, and nothing else keeps it.
    seed_html: str | None = None
    artefacts: list[Artefact] = Field(default_factory=list)
    warnings: list[IngestWarning] = Field(default_factory=list)

    @property
    def text(self) -> str:
        """Every layer merged, in retrieval order. No single source is complete."""
        return "\n\n".join(f"## {a.name}\n{a.text}".strip() for a in self.artefacts if a.text)

    @property
    def evidence_ids(self) -> list[str]:
        return [eid for a in self.artefacts for eid in a.evidence_ids]


# --- layer 2: embedded framework payloads ---------------------------------------------

def flight_text(raw: str) -> tuple[str, list[str]]:
    """Recover text and document links from Next.js App Router flight data.

    ``('', [])`` if this is not a Next.js page. Ported from ``spikes/probe_grant_url.py``,
    where it is what recovers the CRP call period — trafilatura returns 2,287 chars of
    that page and none of them are the deadline. The bytes are in the response, so this
    is a parsing problem, not a rendering one.
    """
    chunks = re.findall(r'self\.__next_f\.push\(\[1,\s*"((?:[^"\\]|\\.)*)"\]\)', raw)
    if not chunks:
        return "", []
    try:
        payload = "".join(json.loads('"' + c + '"') for c in chunks)
    except json.JSONDecodeError:
        return "", []

    out: list[str] = []
    for block in re.findall(r'"wysiwyg":"((?:[^"\\]|\\.)*)"', payload):
        try:
            decoded = json.loads('"' + block + '"')
        except json.JSONDecodeError:
            continue
        text = unescape(re.sub(r"<[^>]+>", " ", decoded))
        if text := re.sub(r"\s+", " ", text).strip():
            out.append(text)

    links = sorted(
        set(re.findall(r'https?://[^\\"\s]+\.(?:pdf|zip|docx?)(?:\?[^\\"\s]*)?', payload))
    )
    return "\n".join(out), links


def embedded_payloads(raw: str) -> str:
    """The rest of the L2 registry: ``__NEXT_DATA__``, ``window.__NUXT__``, JSON-LD.

    Cheap and always worth trying — a site that hides its content in one of these returns
    nothing useful from trafilatura, and the alternative is reporting an empty grant call.
    """
    found: list[str] = []
    patterns = (
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        r"window\.__NUXT__\s*=\s*(\{.*?\});?\s*</script>",
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    )
    for pattern in patterns:
        for blob in re.findall(pattern, raw, re.S | re.I):
            try:
                found.extend(_json_strings(json.loads(blob)))
            except (json.JSONDecodeError, TypeError):
                continue
    return "\n".join(dict.fromkeys(found))


def _json_strings(node: Any, _depth: int = 0) -> Iterable[str]:
    """Every human-looking string in a JSON blob, deduped by the caller."""
    if _depth > 12:
        return
    if isinstance(node, str):
        text = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", node))).strip()
        if len(text) > 40 and " " in text:
            yield text
    elif isinstance(node, dict):
        for value in node.values():
            yield from _json_strings(value, _depth + 1)
    elif isinstance(node, list):
        for value in node:
            yield from _json_strings(value, _depth + 1)


# --- link harvesting ------------------------------------------------------------------

def rank_links(urls: Iterable[str]) -> list[str]:
    """Rank candidate documents by **type**: zip, then pdf, then anything else.

    Not by keyword. On rgp.gov.sg every href is an opaque UUID, so scoring the URL text
    finds nothing — and the actual Call Information Sheet is inside a ZIP.
    """

    def key(url: str) -> tuple[int, int, str]:
        stem = urllib.parse.urlparse(url).path.lower()
        bucket = 0 if stem.endswith(".zip") else 1 if stem.endswith(".pdf") else 2
        return (bucket, len(url), url)

    return sorted(dict.fromkeys(urls), key=key)


def _candidate_links(doc: lxml.html.HtmlElement, flight_links: list[str],
                     policy: IngestPolicy, seed_url: str) -> list[str]:
    """Links worth following, from **both** the DOM and the L2 payload."""
    href_values = [
        str(a.get("href", "")) for a in doc.xpath("//a[@href]")
    ]
    dom_links = [h for h in href_values if h.startswith("http")]

    if policy.follow == "documents":
        candidates = [
            u for u in {*flight_links, *dom_links}
            if urllib.parse.urlparse(u).path.lower().endswith(_DOCUMENT_SUFFIXES)
        ]
        return rank_links(candidates)

    seed_host = urllib.parse.urlparse(seed_url).netloc
    pattern = policy.path_pattern
    pages = [
        u for u in dict.fromkeys(dom_links)
        if urllib.parse.urlparse(u).netloc == seed_host
        and u.split("#")[0] != seed_url.split("#")[0]
        and (pattern is None or pattern.search(urllib.parse.urlparse(u).path))
    ]
    return pages


# --- identity -------------------------------------------------------------------------

_ROLE_PREFIX = re.compile(r"^(Prof\.?|Professor|Dr\.?|A/Prof\.?|Assoc\.?\s+Prof\.?)\s+", re.I)


def extract_identity(html: str, url: str, *, warn: WarnFn | None = None) -> tuple[str, str]:
    """``(name, domain)`` for the researcher whose page this is.

    On the critical path: step 2b cannot resolve an author without a name, and no other
    step produces one. Returns ``("", domain)`` plus a warning rather than raising — the
    run continues and says the identity is unknown (AC9).
    """
    domain = urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")

    match = (
        re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', html, re.I)
        or re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S | re.I)
        or re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    )
    if match is None:
        if warn is not None:
            warn(IDENTITY_INPUTS_MISSING, f"no og:title, h1 or title on {url}")
        return "", domain

    name = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", match.group(1)))).strip()
    # "Name - Lab" / "Name | University" / "Name — Institute". The ASCII hyphen must be
    # **surrounded by spaces** to count as a separator: without that, `Jean-Baptiste Mouret`
    # became `Jean` and step 2b then resolved whichever OpenAlex author is called Jean. A
    # pipe or an en/em dash never occurs inside a personal name, so those may run tight.
    name = re.split(r"\s+-\s+|\s*[|–—]\s*", name)[0].strip()
    name = _ROLE_PREFIX.sub("", name)
    name = re.sub(r"\s*\([^)]*\)", "", name).strip()  # "Name (CFAR, IHPC, NTU)"

    if not name and warn is not None:
        warn(IDENTITY_INPUTS_MISSING, f"page title on {url} left no name after cleaning")
    return name, domain


# --- the session ----------------------------------------------------------------------

@dataclass
class _Session:
    """One ingestion: the client, the store, and the politeness state."""

    store: EvidenceStore
    policy: IngestPolicy
    client: httpx.Client
    warn: WarnFn | None = None
    min_interval_s: float = REQUEST_INTERVAL_S
    warnings: list[IngestWarning] = field(default_factory=list)
    _last_request: dict[str, float] = field(default_factory=dict)
    _robots: dict[str, urllib.robotparser.RobotFileParser | None] = field(default_factory=dict)

    def note(self, code: str, message: str) -> None:
        self.warnings.append(IngestWarning(code=code, message=message))
        if self.warn is not None:
            self.warn(code, message)

    def throttle(self, url: str) -> None:
        host = urllib.parse.urlparse(url).netloc
        elapsed = time.monotonic() - self._last_request.get(host, 0.0)
        if self.min_interval_s > 0 and elapsed < self.min_interval_s:
            time.sleep(self.min_interval_s - elapsed)
        self._last_request[host] = time.monotonic()

    def fetch(self, url: str) -> httpx.Response | None:
        """Never raises. A failure is a warning and a ``None``."""
        self.throttle(url)
        try:
            response = self.client.get(
                url,
                headers={"User-Agent": BROWSER_UA},
                follow_redirects=True,
                timeout=FETCH_TIMEOUT_S,
            )
        except httpx.HTTPError as exc:
            self.note(FETCH_FAILED, f"{url} — {type(exc).__name__}: {exc}")
            return None
        if response.status_code != 200:
            self.note(FETCH_FAILED, f"{url} — HTTP {response.status_code}")
            return None
        return response

    def allowed_by_robots(self, url: str) -> bool:
        """Honoured for links we chose to follow, not for the URL the user handed us."""
        parts = urllib.parse.urlparse(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            self._robots[origin] = self._load_robots(origin)
        parser = self._robots[origin]
        if parser is None:
            return True
        return parser.can_fetch(BROWSER_UA, url)

    def _load_robots(self, origin: str) -> urllib.robotparser.RobotFileParser | None:
        self.throttle(origin)
        try:
            response = self.client.get(
                f"{origin}/robots.txt",
                headers={"User-Agent": BROWSER_UA},
                follow_redirects=True,
                timeout=FETCH_TIMEOUT_S,
            )
        except httpx.HTTPError:
            return None
        if response.status_code != 200:
            return None  # no robots.txt is permission, not prohibition
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(response.text.splitlines())
        return parser

    def mint(self, **fields: Any) -> str | None:
        """Mint, or warn and carry on.

        ``EvidenceStore.mint`` raises on a row that cannot satisfy AC4. That is our bug,
        not the source's, but it must not take the run down with it four minutes in.
        """
        try:
            return self.store.mint(**fields)
        except (ValueError, TypeError) as exc:
            self.note(EVIDENCE_REJECTED, f"could not store evidence: {exc}")
            return None


# --- readers --------------------------------------------------------------------------

def _sniff(body: bytes, content_type: str) -> Literal["html", "pdf", "zip", "other"]:
    """Content-Type first; magic bytes for local files, which have no header."""
    kind = content_type.split(";")[0].strip().lower()
    if kind == "application/pdf" or body[:4] == b"%PDF":
        return "pdf"
    if kind in ("application/zip", "application/x-zip-compressed") or body[:4] == b"PK\x03\x04":
        return "zip"
    if kind.startswith("text/html") or kind == "application/xhtml+xml":
        return "html"
    if not kind and re.search(rb"<\s*(!doctype\s+html|html|body)\b", body[:2048], re.I):
        return "html"  # a local file, which carries no header to dispatch on
    return "other"


def _page_title(doc: lxml.html.HtmlElement, fallback: str) -> str:
    for xpath in ('//meta[@property="og:title"]/@content', "//title/text()", "//h1//text()"):
        values = doc.xpath(xpath)
        if values and str(values[0]).strip():
            return re.sub(r"\s+", " ", str(values[0])).strip()
    return fallback


def _parse_html(session: _Session, url: str, raw: str) -> lxml.html.HtmlElement | None:
    """Parse once, with absolute links. ``None`` — never an exception — on junk.

    ``lxml.html.fromstring("")`` raises ``ParserError``, and an empty 200 is exactly the
    sort of thing a flaky CDN returns.
    """
    try:
        # fromstring is annotated as returning _Element; for HTML input it is always the
        # HtmlElement subclass, which is what carries make_links_absolute.
        doc = cast(lxml.html.HtmlElement, lxml.html.fromstring(raw))
        doc.make_links_absolute(url)  # trafilatura fabricates URLs without this
    except (ParserError, ValueError) as exc:
        session.note(THIN_EXTRACTION, f"{url} returned no parseable HTML: {type(exc).__name__}")
        return None
    return doc


def _read_html(
    session: _Session,
    url: str,
    raw: str,
    doc: lxml.html.HtmlElement,
    *,
    http_status: int | None,
    sha256: str | None = None,
) -> Artefact:
    """Layers 1 and 2, merged, and one evidence row for the page.

    ``http_status`` is the real one or ``None`` for a file read off disk. A local file is
    **not** minted as a ``webpage``: AC4 wants a webpage row to prove a successful fetch,
    and nothing was fetched. It is recorded the way a document is — by content hash.
    """
    try:
        layer1 = (
            trafilatura.extract(
                doc,
                output_format="markdown",
                include_links=True,
                include_tables=True,
                favor_recall=True,
            )
            or ""
        )
    except Exception as exc:  # noqa: BLE001 - one odd page must not end the run
        session.note(THIN_EXTRACTION, f"{url}: trafilatura failed with {type(exc).__name__}")
        layer1 = ""
    layer2 = "\n".join(part for part in (flight_text(raw)[0], embedded_payloads(raw)) if part)
    text = "\n\n".join(part for part in (layer1, layer2) if part)

    recovered = len(layer1) + len(layer2)
    if recovered < MIN_EXTRACTED_CHARS or (raw and recovered / len(raw) < MIN_TEXT_HTML_RATIO):
        session.note(
            THIN_EXTRACTION,
            f"{url} yielded {recovered} chars from {len(raw)} of HTML — "
            f"the page may render its content in the browser",
        )

    title = _page_title(doc, url)
    if http_status is not None:
        evidence_id = session.mint(
            source_type="webpage",
            url=url,
            title=title,
            http_status=http_status,
            summary=text[:SUMMARY_CHARS],
        )
    else:
        evidence_id = session.mint(
            source_type="grant_doc",
            url=url,
            title=title,
            page=1,
            sha256=sha256 or hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest(),
            summary=text[:SUMMARY_CHARS],
        )
    return Artefact(
        kind="html",
        name=title,
        url=url,
        text=text,
        evidence_ids=[evidence_id] if evidence_id else [],
    )


def _read_pdf(session: _Session, url: str, name: str, body: bytes) -> Artefact:
    """One ``grant_doc`` evidence row per page, each carrying the document's sha256."""
    sha256 = hashlib.sha256(body).hexdigest()
    try:
        # to_markdown wants a Document; it will not take raw bytes or a file object, and
        # everything here arrives as bytes (an HTTP body, or a member of a ZIP in memory).
        with pymupdf.Document(stream=body, filetype="pdf") as document:
            chunks = pymupdf4llm.to_markdown(document, page_chunks=True)
    except Exception as exc:  # noqa: BLE001 - a corrupt PDF must not end the run
        session.note(FETCH_FAILED, f"{name} could not be parsed as a PDF: {type(exc).__name__}")
        return Artefact(kind="pdf", name=name, url=url)

    pages: list[str] = []
    evidence_ids: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        metadata = chunk.get("metadata") or {}
        # The key is `page_number` here and `page` where pymupdf-layout is absent.
        raw_page = metadata.get("page_number") or metadata.get("page") or index
        try:
            page = int(raw_page)
        except (TypeError, ValueError):
            page = index
        body_text = (chunk.get("text") or "").strip()
        pages.append(f"[p.{page}] {body_text}")
        evidence_id = session.mint(
            source_type="grant_doc",
            url=url,
            title=f"{name} — p. {page}",
            page=page,
            sha256=sha256,
            summary=body_text[:SUMMARY_CHARS],
        )
        if evidence_id:
            evidence_ids.append(evidence_id)

    return Artefact(
        kind="pdf", name=name, url=url, text="\n\n".join(pages), evidence_ids=evidence_ids
    )


def _read_zip(session: _Session, url: str, body: bytes) -> list[Artefact]:
    """Unzip in memory and read every PDF inside — the real call sheet lives in one."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(body))
    except zipfile.BadZipFile as exc:
        session.note(FETCH_FAILED, f"{url} is not a readable ZIP: {exc}")
        return []

    artefacts: list[Artefact] = []
    for entry in archive.namelist():
        if not entry.lower().endswith(".pdf"):
            continue
        try:
            inner = archive.read(entry)
        except (KeyError, zipfile.BadZipFile, RuntimeError) as exc:
            session.note(FETCH_FAILED, f"{entry} inside {url}: {type(exc).__name__}: {exc}")
            continue
        # url stays the ZIP: that is the address the document was actually retrieved from.
        artefacts.append(_read_pdf(session, url, entry.rsplit("/", 1)[-1], inner))
    return artefacts


# --- the one entry point --------------------------------------------------------------

def ingest_source(
    src: str,
    policy: IngestPolicy,
    store: EvidenceStore,
    *,
    warn: WarnFn | None = None,
    client: httpx.Client | None = None,
    min_interval_s: float = REQUEST_INTERVAL_S,
) -> DocumentSet:
    """Read one input and everything worth following from it, depth 1.

    ``src`` is a URL or a local path; the caller never says which, and never says what
    type the thing is. Returns whatever was recovered — possibly nothing, with warnings
    explaining why.
    """
    owned = client is None
    active = client or httpx.Client()
    session = _Session(
        store=store, policy=policy, client=active, warn=warn, min_interval_s=min_interval_s
    )
    result = DocumentSet(source=src, policy=policy.name)
    try:
        _ingest(session, result, src, policy)
    finally:
        result.warnings = session.warnings
        if owned:
            active.close()
    return result


def _ingest(session: _Session, result: DocumentSet, src: str, policy: IngestPolicy) -> None:
    seed = _load_seed(session, src)
    if seed is None:
        return
    url, body, content_type, http_status = seed
    result.final_url = url

    kind = _sniff(body, content_type)
    if kind == "pdf":
        result.artefacts.append(_read_pdf(session, url, Path(url).name or url, body))
        return
    if kind == "zip":
        if not policy.unzip:
            session.note(UNSUPPORTED_TYPE, f"{url} is a ZIP and the {policy.name} policy skips it")
            return
        result.artefacts.extend(_read_zip(session, url, body))
        return
    if kind != "html":
        session.note(UNSUPPORTED_TYPE, f"{url} is {content_type or 'of unknown type'}; skipped")
        return

    raw = body.decode("utf-8", errors="replace")
    result.seed_html = raw
    doc = _parse_html(session, url, raw)
    if doc is None:
        return
    result.artefacts.append(
        _read_html(
            session, url, raw, doc,
            http_status=http_status,
            sha256=hashlib.sha256(body).hexdigest(),
        )
    )

    for link in _candidate_links(doc, flight_text(raw)[1], policy, url)[: policy.max_artefacts]:
        _follow(session, result, link, policy)


def _follow(session: _Session, result: DocumentSet, url: str, policy: IngestPolicy) -> None:
    """Depth 1. A followed link is read, never crawled from."""
    if not session.allowed_by_robots(url):
        session.note(ROBOTS_DISALLOWED, f"robots.txt disallows {url}")
        return
    response = session.fetch(url)
    if response is None:
        return

    body = response.content
    kind = _sniff(body, response.headers.get("content-type", ""))
    final = str(response.url)
    if kind == "pdf":
        name = Path(urllib.parse.urlparse(final).path).name or final
        result.artefacts.append(_read_pdf(session, final, name, body))
    elif kind == "zip" and policy.unzip:
        result.artefacts.extend(_read_zip(session, final, body))
    elif kind == "html" and policy.follow == "pages":
        raw = body.decode("utf-8", errors="replace")
        doc = _parse_html(session, final, raw)
        if doc is not None:
            result.artefacts.append(
                _read_html(session, final, raw, doc, http_status=response.status_code)
            )
    else:
        session.note(UNSUPPORTED_TYPE, f"{final} is {kind}; the {policy.name} policy skips it")


def _load_seed(session: _Session, src: str) -> tuple[str, bytes, str, int | None] | None:
    """``(url, body, content_type, http_status)``.

    A local path has neither a Content-Type nor a status, so the type is sniffed from the
    bytes and the status stays ``None`` rather than being invented.
    """
    path = Path(src)
    if not src.lower().startswith(("http://", "https://")):
        try:
            return path.resolve().as_uri(), path.read_bytes(), "", None
        except (OSError, ValueError) as exc:
            session.note(FETCH_FAILED, f"{src} — {type(exc).__name__}: {exc}")
            return None

    response = session.fetch(src)
    if response is None:
        return None
    return (
        str(response.url),
        response.content,
        response.headers.get("content-type", ""),
        response.status_code,
    )


def ingest_grant(
    src: str,
    store: EvidenceStore,
    *,
    warn: WarnFn | None = None,
    client: httpx.Client | None = None,
    min_interval_s: float = REQUEST_INTERVAL_S,
) -> DocumentSet:
    """The grant call: follow its documents, unzip them, read up to 6."""
    return ingest_source(
        src, GRANT, store, warn=warn, client=client, min_interval_s=min_interval_s
    )


def ingest_profile(
    url: str,
    store: EvidenceStore,
    *,
    warn: WarnFn | None = None,
    client: httpx.Client | None = None,
    min_interval_s: float = REQUEST_INTERVAL_S,
) -> DocumentSet:
    """The researcher's page: seed plus up to 2 same-site publication/research pages."""
    return ingest_source(
        url, PROFILE, store, warn=warn, client=client, min_interval_s=min_interval_s
    )


# --- pre-flight probe (WI-1.4b) -------------------------------------------------------
#
# Ambiguity in the *inputs* is resolved before the run starts, never during it. A run that
# suspends waiting for an answer dies to a closed tab or a sleeping laptop, and its resume
# path is the least-tested code in the repo — failing exactly when it matters. Asking first
# costs nothing, because nothing is running yet.
#
# Detectors are deterministic Python rules with a fixed question, fixed options and a
# defined default. Never "LLM, what are you unsure about?": that generates unbounded
# questions and cannot be tested. And never ask what retrieval can answer — the tool reads
# all seven CRP PDFs itself, so it only asks which call the applicant means.

MULTIPLE_CALL_PERIODS = "multiple_call_periods"
MULTIPLE_SCHEMES = "multiple_schemes"
THIN_PROFILE = "thin_profile"
NO_ELIGIBILITY_FOUND = "no_eligibility_found"

#: "CRP36 Grant Call Period: 14 Sep 2026 (9am) to 9 Nov 2026 (4pm)" — the label before the
#: phrase names the call, which is exactly what the applicant has to choose between.
CALL_PERIOD_RE = re.compile(r"([^.\n|]{0,60}?)\s*Grant Call Period\s*[:\-]\s*([^.\n]{0,90})", re.I)

#: A scheme acronym only counts near a phrase that marks it as a scheme. A bare acronym
#: scan over this corpus returns PI, NRF, NUS, NTU and AI — noise that would produce a
#: pointless question. Requiring the hyphen or the trailing number keeps F-CRP, T-CRP and
#: CRP36 and drops the rest. Precision over recall on purpose: a missed scheme falls back
#: to "analyse all of them", which is the safe direction to be wrong in.
SCHEME_SIGNAL_RE = re.compile(
    r"sub-categor\w+|funding scheme|scheme|Grant Call Period|Call-for-Proposals", re.I
)
SCHEME_TOKEN_RE = re.compile(r"\b(?:[A-Z][A-Za-z]{0,2}-[A-Z]{2,6}|[A-Z]{2,6}\d{1,3})\b")
SCHEME_WINDOW = 80

ELIGIBILITY_RE = re.compile(r"eligib", re.I)

#: What the applicant is told when they skip a question.
ALL_CALLS = "all_calls"
ALL_SCHEMES = "all_schemes"
CONTINUE = "continue"


class ProbeOption(BaseModel):
    """One answer, with the evidence that put it on the list."""

    value: str
    label: str
    evidence_ids: list[str] = Field(default_factory=list)


class ProbeQuestion(BaseModel):
    code: str
    question: str
    options: list[ProbeOption]
    #: The option applied when the applicant skips. Skipping is always allowed.
    default: str


class ProbeAnswer(BaseModel):
    """A resolved answer, carrying where the option came from.

    This is what makes the answers evidence-bearing inputs rather than an invisible side
    channel: the run can say *why* it narrowed to one call, and point at the row.
    """

    code: str
    question: str
    value: str
    label: str
    evidence_ids: list[str] = Field(default_factory=list)
    #: False when nobody answered and the default was applied.
    answered: bool


class ProbeResult(BaseModel):
    """``POST /api/probe``'s payload, plus the ingestion the run should reuse.

    ``grant`` and ``profile`` are ``exclude=True``: they hold ~100k chars of document text,
    so ``model_dump()`` gives exactly the API response while Python keeps the documents.
    """

    probe_id: str
    detected: dict[str, Any] = Field(default_factory=dict)
    questions: list[ProbeQuestion] = Field(default_factory=list)
    warnings: list[IngestWarning] = Field(default_factory=list)

    grant: DocumentSet | None = Field(default=None, exclude=True)
    profile: DocumentSet | None = Field(default=None, exclude=True)


def probe_id_for(grant_src: str, profile_url: str) -> str:
    """Stable id for one pair of inputs, so WI-2.1 can cache by input hash."""
    digest = hashlib.sha256(f"{grant_src}\n{profile_url}".encode()).hexdigest()
    return f"pb_{digest[:12]}"


def _locate(store: EvidenceStore, artefact: Artefact, offset: int) -> list[str]:
    """The evidence row a match at ``offset`` actually came from.

    A PDF artefact is many rows; ``_read_pdf`` writes a ``[p.N]`` marker ahead of each page,
    so the nearest preceding marker names the page and the row that carries it.
    """
    if not artefact.evidence_ids:
        return []
    if artefact.kind != "pdf":
        return artefact.evidence_ids[:1]

    markers = list(re.finditer(r"\[p\.(\d+)\]", artefact.text[:offset]))
    if not markers:
        return artefact.evidence_ids[:1]
    page = int(markers[-1].group(1))
    for evidence_id in artefact.evidence_ids:
        row = store.get(evidence_id)
        if row is not None and row.page == page:
            return [evidence_id]
    return artefact.evidence_ids[:1]


def _detect_call_periods(documents: DocumentSet, store: EvidenceStore) -> list[ProbeOption]:
    """Every distinct ``… Grant Call Period: …`` on record, most-cited page first."""
    found: dict[str, ProbeOption] = {}
    for artefact in documents.artefacts:
        for match in CALL_PERIOD_RE.finditer(artefact.text):
            name = " ".join(match.group(1).split()).strip(" -–—:|") or "Unnamed call"
            period = " ".join(match.group(2).split()).strip(" .")
            label = f"{name} — {period}"
            if label not in found:
                found[label] = ProbeOption(
                    value=re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "call",
                    label=label,
                    evidence_ids=_locate(store, artefact, match.start()),
                )
    return list(found.values())


def _detect_schemes(documents: DocumentSet, store: EvidenceStore) -> list[ProbeOption]:
    """Scheme acronyms named next to a phrase that marks them as schemes."""
    found: dict[str, ProbeOption] = {}
    for artefact in documents.artefacts:
        text = artefact.text
        for signal in SCHEME_SIGNAL_RE.finditer(text):
            lo = max(0, signal.start() - SCHEME_WINDOW)
            hi = signal.end() + SCHEME_WINDOW
            for token in SCHEME_TOKEN_RE.finditer(text[lo:hi]):
                acronym = token.group(0)
                if acronym not in found:
                    found[acronym] = ProbeOption(
                        value=acronym.lower().replace("-", "_"),
                        label=acronym,
                        evidence_ids=_locate(store, artefact, lo + token.start()),
                    )
    return list(found.values())


def build_questions(
    grant: DocumentSet, profile: DocumentSet, store: EvidenceStore
) -> tuple[list[ProbeQuestion], dict[str, Any]]:
    """The four detectors. Each fires or does not; none of them guesses."""
    questions: list[ProbeQuestion] = []
    calls = _detect_call_periods(grant, store)
    schemes = _detect_schemes(grant, store)
    profile_chars = len(profile.text)
    eligibility_found = bool(ELIGIBILITY_RE.search(grant.text))

    if len(calls) > 1:
        questions.append(ProbeQuestion(
            code=MULTIPLE_CALL_PERIODS,
            question=f"This page lists {len(calls)} grant calls. Which one are you applying to?",
            options=[*calls, ProbeOption(value=ALL_CALLS,
                                         label="Not sure — analyse the whole programme")],
            default=ALL_CALLS,
        ))

    if len(schemes) > 1:
        questions.append(ProbeQuestion(
            code=MULTIPLE_SCHEMES,
            question=f"The call names {len(schemes)} funding schemes. Which one is yours?",
            options=[*schemes, ProbeOption(value=ALL_SCHEMES, label="All of them")],
            default=ALL_SCHEMES,
        ))

    if profile_chars < MIN_EXTRACTED_CHARS:
        questions.append(ProbeQuestion(
            code=THIN_PROFILE,
            question=(
                f"We recovered only {profile_chars} characters from that profile page. "
                f"Is there a fuller one — a publications or lab page?"
            ),
            options=[
                ProbeOption(value=CONTINUE,
                            label="Continue anyway (applicant fit will be marked low confidence)"),
                ProbeOption(value="use_different_url", label="Let me paste a different URL"),
            ],
            default=CONTINUE,
        ))

    if not eligibility_found:
        questions.append(ProbeQuestion(
            code=NO_ELIGIBILITY_FOUND,
            question=(
                "Nothing we could read mentions eligibility. Do you want to upload the call "
                "document instead?"
            ),
            options=[
                ProbeOption(value=CONTINUE, label="Continue — record eligibility as not specified"),
                ProbeOption(value="upload_document", label="Let me upload the call document"),
            ],
            default=CONTINUE,
        ))

    detected = {
        "call_periods": [option.label for option in calls],
        "schemes": [option.label for option in schemes],
        "profile_chars": profile_chars,
        "eligibility_found": eligibility_found,
        "grant_evidence": len(grant.evidence_ids),
        "profile_evidence": len(profile.evidence_ids),
    }
    return questions, detected


def probe(
    grant_src: str,
    profile_url: str,
    store: EvidenceStore,
    *,
    warn: WarnFn | None = None,
    client: httpx.Client | None = None,
    min_interval_s: float = REQUEST_INTERVAL_S,
) -> ProbeResult:
    """Read both inputs and ask only what retrieval could not answer. **Zero LLM calls.**

    Target is under 20 s (AC14). Measured on the demo pair: 17.5 s, of which the grant's
    eight artefacts are 17.1 s. Never raises — an unreachable input comes back as warnings
    and, for the profile, as a ``thin_profile`` question.
    """
    grant = ingest_grant(grant_src, store, warn=warn, client=client, min_interval_s=min_interval_s)
    profile = ingest_profile(
        profile_url, store, warn=warn, client=client, min_interval_s=min_interval_s
    )
    questions, detected = build_questions(grant, profile, store)
    return ProbeResult(
        probe_id=probe_id_for(grant_src, profile_url),
        detected=detected,
        questions=questions,
        warnings=[*grant.warnings, *profile.warnings],
        grant=grant,
        profile=profile,
    )


def resolve_answers(
    result: ProbeResult, answers: dict[str, str] | None = None
) -> list[ProbeAnswer]:
    """Turn what the applicant chose — or did not — into resolved, evidence-bearing answers.

    Skipping is always allowed: an unanswered question resolves to its default with
    ``answered=False``, so the run never blocks and the report can still say what was
    assumed.
    """
    chosen = answers or {}
    resolved: list[ProbeAnswer] = []
    for question in result.questions:
        value = chosen.get(question.code) or question.default
        option = next((o for o in question.options if o.value == value), None)
        if option is None:  # an answer we never offered; fall back rather than trust it
            option = next(o for o in question.options if o.value == question.default)
            value = option.value
        resolved.append(ProbeAnswer(
            code=question.code,
            question=question.question,
            value=option.value,
            label=option.label,
            evidence_ids=option.evidence_ids,
            answered=chosen.get(question.code) == option.value,
        ))
    return resolved


def answers_brief(answers: list[ProbeAnswer]) -> str:
    """The block LLM #1 is given, so the applicant's choice reaches the grant brief.

    Empty when nothing was asked, which is the common case.
    """
    if not answers:
        return ""
    lines = ["The applicant was asked about ambiguities in the call and answered:"]
    for answer in answers:
        suffix = "" if answer.answered else "  (not answered; default applied)"
        lines.append(f"- {answer.question}\n  -> {answer.label}{suffix}")
    return "\n".join(lines)
