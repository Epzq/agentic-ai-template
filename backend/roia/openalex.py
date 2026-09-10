"""OpenAlex client — the only place ``source_type="paper"`` is minted.

Two rules here are easy to get backwards and expensive to get wrong.

**``search_literature`` mints an ``api_query`` row and lightweight ``WorkRef``s — never
papers.** A search hit is a title and a citation count; it carries no abstract, so nothing
downstream can honestly claim to have read it. Only ``fetch_top_works`` mints
``source_type="paper"``, because only its free singleton lookups return the abstract that
makes a paper row mean "we read this" (AC11).

**``last_known_institutions.ror`` is a scoring signal, never a filter.** Verified live:
filtering on it excluded a 417-work researcher and returned two-work stubs, because most
real author records carry no institution at all.

Nothing here raises at the caller. Every method returns empty on failure and reports it,
because a run that dies on one 429 four minutes in is worse than a run that says so (AC9).
"""

from __future__ import annotations

import math
import re
import time
import urllib.parse
from collections.abc import Callable, Iterable, Sequence
from datetime import date
from typing import Any, Literal

import httpx
from pydantic import BaseModel
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from roia.config import Settings, get_settings
from roia.evidence import EvidenceStore, WarnFn

API = "https://api.openalex.org"
ROR_API = "https://api.ror.org/v2/organizations"

#: The polite pool allows 10 requests/second. A run makes ~20 calls, so a 1 req/s throttle
#: like ingestion's would cost 20 s of the AC1 budget for nothing.
MIN_INTERVAL_S = 0.1
TIMEOUT_S = 40.0
RETRY_ATTEMPTS = 3

#: Below this many hits the direction's gap claim rests on almost nothing, and says so.
THIN_LITERATURE_MIN = 5
SEARCH_LIMIT = 15
AUTHOR_WORKS_LIMIT = 40
AUTHOR_CANDIDATES = 25
TOP_WORKS = 4
#: Abstract coverage is **not** 100% — verified: a 25-citation work in the demo query has no
#: ``abstract_inverted_index`` at all. Taking the top ``n`` blind silently under-delivers on
#: AC11, so consider this many times more candidates and keep the first ``n`` that have one.
TOP_WORKS_OVERFETCH = 4
#: A full work record is ~25 KB of locations, references and yearly counts we never read.
#: Selecting the six fields we use cuts it to ~5 KB per paper.
WORK_SELECT = "id,display_name,publication_year,cited_by_count,authorships,abstract_inverted_index"

#: warning codes
THIN_LITERATURE = "thin_literature"
OPENALEX_FAILED = "openalex_failed"
AUTHOR_UNRESOLVED = "author_unresolved"

#: Words too generic to count as topic overlap between a page and an author record.
_STOP = frozenset({"research", "university", "professor", "science", "student", "paper", "group"})

#: ``emit(type, payload)``. WI-1.3's ``Run.emit`` is wired into this slot by the pipeline;
#: keeping it a plain callable means this module has no dependency on the event system.
#: ``object`` rather than ``None`` for the same reason as ``WarnFn``.
EmitFn = Callable[[str, dict[str, Any]], object]


class WorkRef(BaseModel):
    """A search hit: title, year, citations. **Not** a paper — it carries no abstract."""

    id: str
    title: str
    year: int | None = None
    cited_by_count: int = 0
    #: The ``api_query`` row that returned it, so a paper derived from it satisfies AC4.
    derived_from: str


class AuthorMatch(BaseModel):
    """The resolved author, always labelled unverified — disambiguation is a non-goal (§4)."""

    author_id: str
    display_name: str
    institution: str | None = None
    works_count: int = 0
    cited_by_count: int = 0
    #: Score gap to the runner-up. Small means a namesake is plausible; the UI says so.
    margin: float = 0.0
    confidence: Literal["unverified"] = "unverified"
    evidence_id: str | None = None


class Measure(BaseModel):
    """A number the report can cite, with the row it came from (AC12).

    ``evidence_id`` is ``None`` only when the call failed, and ``value`` is then 0 — never
    an exception, and never an index into an empty list.
    """

    value: float
    detail: str = ""
    evidence_id: str | None = None


class _Retryable(Exception):
    """A 429 or 5xx: worth trying again rather than reporting."""


def _abstract(work: dict[str, Any]) -> str:
    """Rebuild the abstract from OpenAlex's inverted index. ``""`` when there is none."""
    inverted = work.get("abstract_inverted_index")
    if not isinstance(inverted, dict):
        return ""
    positions: dict[int, str] = {}
    for word, indices in inverted.items():
        for index in indices:
            positions[index] = word
    return " ".join(positions[i] for i in sorted(positions))


def _work_id(value: str) -> str:
    """``W4379929708`` from either the bare id or the full OpenAlex URL."""
    return value.rsplit("/", 1)[-1]


class OpenAlexClient:
    """One run's access to OpenAlex. Mints every row it is entitled to and nothing else."""

    def __init__(
        self,
        store: EvidenceStore,
        *,
        warn: WarnFn | None = None,
        emit: EmitFn | None = None,
        client: httpx.Client | None = None,
        settings: Settings | None = None,
        min_interval_s: float = MIN_INTERVAL_S,
    ) -> None:
        self.store = store
        self.warn = warn
        self.emit = emit
        self.settings = settings or get_settings()
        self._client = client or httpx.Client()
        self._owns_client = client is None
        self.min_interval_s = min_interval_s
        self._last_request = 0.0

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    # --- plumbing ---------------------------------------------------------------------

    def _note(self, code: str, message: str) -> None:
        if self.warn is not None:
            self.warn(code, message)

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if self.min_interval_s > 0 and elapsed < self.min_interval_s:
            time.sleep(self.min_interval_s - elapsed)
        self._last_request = time.monotonic()

    def _get(self, path: str, params: dict[str, str]) -> tuple[dict[str, Any] | None, str, int]:
        """``(payload, display_url, status)``. Never raises.

        ``display_url`` is the request **without the API key** — it goes straight into an
        evidence row, and a report that leaks a credential is worse than one that omits a
        link.
        """
        display = f"{API}/{path}"
        if params:
            display += "?" + urllib.parse.urlencode(params)

        headers = {"User-Agent": f"ROIA/0.1 (mailto:{self.settings.openalex_mailto})"}
        sent = {**params, "api_key": self.settings.openalex_api_key}

        @retry(
            retry=retry_if_exception_type(_Retryable),
            stop=stop_after_attempt(RETRY_ATTEMPTS),
            wait=wait_exponential(multiplier=0.5, max=8),
            reraise=True,
        )
        def attempt() -> httpx.Response:
            self._throttle()
            response = self._client.get(
                f"{API}/{path}", params=sent, headers=headers, timeout=TIMEOUT_S
            )
            if response.status_code == 429 or response.status_code >= 500:
                raise _Retryable(f"HTTP {response.status_code}")
            return response

        try:
            response = attempt()
        except (_Retryable, RetryError, httpx.HTTPError) as exc:
            self._note(OPENALEX_FAILED, f"{display} — {type(exc).__name__}: {exc}")
            return None, display, 0

        if response.status_code != 200:
            self._note(OPENALEX_FAILED, f"{display} — HTTP {response.status_code}")
            return None, display, response.status_code
        try:
            return response.json(), display, response.status_code
        except ValueError as exc:
            self._note(OPENALEX_FAILED, f"{display} — unreadable JSON: {exc}")
            return None, display, response.status_code

    @staticmethod
    def _unretrieved(status: int) -> str:
        """What a failed request must say instead of a number.

        When `_get` fails it returns `payload is None`, and every summary below then
        computed itself from `payload or {}` — so a timeout became *"0 works match; the 0
        most cited were retrieved."*, *"No works matched."*, *"0 works … cite W123."* Those
        are claims about the literature, they are minted as evidence, and LLM #4 is handed
        them as citable numbers.

        The project's own rule is that finding nothing means **don't know**, never *nobody
        has done this*. A request that never returned is the strongest form of don't know.
        """
        return (
            f"This request did not return data "
            f"({f'HTTP {status}' if status else 'the request failed'}); nothing was "
            f"retrieved. This is not a measurement of zero."
        )

    def _mint_query(self, display: str, status: int, title: str, summary: str) -> str | None:
        """One ``api_query`` row per call: the full request URL and the status returned (AC4)."""
        try:
            return self.store.mint(
                source_type="api_query",
                url=display,
                title=title,
                http_status=status or 599,
                summary=summary,
            )
        except (ValueError, TypeError) as exc:
            self._note(OPENALEX_FAILED, f"could not store the query row: {exc}")
            return None

    @staticmethod
    def _meta(payload: dict[str, Any] | None) -> dict[str, Any]:
        meta = (payload or {}).get("meta")
        return meta if isinstance(meta, dict) else {}

    @classmethod
    def _cost(cls, payload: dict[str, Any] | None) -> str:
        cost = cls._meta(payload).get("cost_usd")
        return f" meta.cost_usd {cost}." if cost is not None else ""

    # --- identity ---------------------------------------------------------------------

    def resolve_author(
        self, name: str, domain: str, *, profile_text: str = ""
    ) -> AuthorMatch | None:
        """The best OpenAlex author for a name, ranked but never filtered on institution.

        ``extract_identity`` returns an empty name when the page offered none; that is not
        an error here, it is simply nothing to search for.
        """
        if not name.strip():
            self._note(AUTHOR_UNRESOLVED, "no researcher name was extracted; skipping lookup")
            return None

        params = {
            "filter": f"display_name.search:{name}",
            "select": "id,display_name,works_count,cited_by_count,topics,last_known_institutions",
            "sort": "works_count:desc",
            "per_page": str(AUTHOR_CANDIDATES),
        }
        payload, display, status = self._get("authors", params)
        results: list[dict[str, Any]] = (payload or {}).get("results") or []
        institution_name = self._institution_for(domain)

        evidence_id = self._mint_query(
            display, status, f'OpenAlex author search: "{name}"',
            f"{len(results)} candidate(s) for {name!r}."
            f"{f' Institution hint from {domain}: {institution_name}.' if institution_name else ''}"
            f"{self._cost(payload)}",
        )
        if not results:
            self._note(AUTHOR_UNRESOLVED, f"OpenAlex returned no author matching {name!r}")
            return None

        page_words = set(re.findall(r"[a-z]{4,}", profile_text.lower()))
        ranked = sorted(
            results, key=lambda c: self._score(c, page_words, institution_name), reverse=True
        )
        best = ranked[0]
        margin = 0.0
        if len(ranked) > 1:
            margin = round(
                self._score(best, page_words, institution_name)
                - self._score(ranked[1], page_words, institution_name),
                1,
            )

        institutions = [
            i["display_name"]
            for i in (best.get("last_known_institutions") or [])
            if i.get("display_name")
        ]
        if not best.get("id"):
            self._note(AUTHOR_UNRESOLVED, f"OpenAlex returned a record with no id for {name!r}")
            return None
        match = AuthorMatch(
            author_id=best["id"],
            display_name=best.get("display_name") or name,
            institution=institutions[0] if institutions else None,
            works_count=best.get("works_count", 0),
            cited_by_count=best.get("cited_by_count", 0),
            margin=margin,
            evidence_id=evidence_id,
        )
        if self.emit is not None:
            self.emit("identity.resolved", {
                "author_id": match.author_id,
                "display_name": match.display_name,
                "institution": match.institution,
                "confidence": match.confidence,
                "margin": match.margin,
            })
        return match

    @staticmethod
    def _score(candidate: dict[str, Any], page_words: set[str], institution: str | None) -> float:
        """``55·log(works) + 30·topic-overlap + 15·institution-match``, from the WI-0.0 spike.

        Works count dominates because OpenAlex fragments author records: a real researcher
        has one canonical record with hundreds of works plus several two-work stubs, and the
        canonical one often carries no institution. Topic overlap guards the remaining
        case — a genuine namesake in another field.
        """
        topic_words = {
            word
            for topic in (candidate.get("topics") or [])[:8]
            for word in re.findall(r"[a-z]{4,}", (topic.get("display_name") or "").lower())
        } - _STOP
        overlap = len(topic_words & page_words) / max(len(topic_words), 1)
        on_record = " ".join(
            i.get("display_name") or ""
            for i in (candidate.get("last_known_institutions") or [])
        ).lower()
        matched = bool(on_record) and bool(institution) and any(
            word in on_record for word in (institution or "").lower().split() if len(word) > 4
        )
        works = min(math.log10(candidate.get("works_count", 0) + 1) / math.log10(500), 1.0)
        return round(55 * works + 30 * overlap + 15 * matched, 1)

    def _institution_for(self, domain: str) -> str | None:
        """ROR lookup by domain, for the institution-match term only. ``None`` is fine.

        A personal domain (``…github.io``) has no ROR record, which is why institution is
        worth 15 points and not a gate.
        """
        if not domain:
            return None
        try:
            self._throttle()
            response = self._client.get(
                ROR_API,
                params={"query.advanced": f'domains:"{domain}"'},
                headers={"User-Agent": f"ROIA/0.1 (mailto:{self.settings.openalex_mailto})"},
                timeout=TIMEOUT_S,
            )
            if response.status_code != 200:
                return None
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return None
        items = payload.get("items") or []
        if not payload.get("number_of_results") or not items:
            return None
        names = items[0].get("names") or []
        return next(
            (n["value"] for n in names if "ror_display" in (n.get("types") or [])),
            items[0].get("id"),
        )

    # --- literature -------------------------------------------------------------------

    def fetch_author_works(self, author_id: str, limit: int = AUTHOR_WORKS_LIMIT) -> list[WorkRef]:
        """The author's own works, for LLM #2. Search hits, so no paper rows."""
        params = {
            "filter": f"author.id:{_work_id(author_id)}",
            "select": "id,display_name,publication_year,cited_by_count",
            "sort": "cited_by_count:desc",
            "per_page": str(limit),
        }
        payload, display, status = self._get("works", params)
        results = (payload or {}).get("results") or []
        evidence_id = self._mint_query(
            display, status, f"OpenAlex works by {_work_id(author_id)}",
            f"{len(results)} of {self._meta(payload).get('count', 0)} works "
            f"retrieved, most cited first.{self._cost(payload)}",
        )
        return self._refs(results, evidence_id)

    def search_literature(
        self, query: str, from_year: int, limit: int = SEARCH_LIMIT
    ) -> list[WorkRef]:
        """Run one direction query. Mints an ``api_query`` row — **never** a paper row."""
        params = {
            "filter": (
                f"title_and_abstract.search:{query},from_publication_date:{from_year}-01-01"
            ),
            "select": "id,display_name,publication_year,cited_by_count",
            "sort": "cited_by_count:desc",
            "per_page": str(limit),
        }
        payload, display, status = self._get("works", params)
        results = (payload or {}).get("results") or []
        total = self._meta(payload).get("count", 0) or 0
        oql = (self._meta(payload).get("x_query") or {}).get("oql", "")

        evidence_id = self._mint_query(
            display, status, f'OpenAlex works search: "{query}", {from_year} onwards',
            self._unretrieved(status) if payload is None else
            f"{total} works match; the {len(results)} most cited were retrieved."
            f"{f' OpenAlex reads the query as: {oql}.' if oql else ''}{self._cost(payload)}",
        )
        # `thin_literature` is a statement about the field. A failed request says nothing
        # about the field, and `_get` has already reported it as `openalex_failed`.
        if payload is not None and total < THIN_LITERATURE_MIN:
            self._note(
                THIN_LITERATURE,
                f'"{query}" returned {total} works since {from_year} — too few to support a '
                f"claim about what the field has or has not done",
            )
        return self._refs(results, evidence_id)

    @staticmethod
    def _refs(results: Sequence[dict[str, Any]], evidence_id: str | None) -> list[WorkRef]:
        if evidence_id is None:
            return []
        return [
            WorkRef(
                id=_work_id(work["id"]),
                title=work.get("display_name") or "(untitled)",
                year=work.get("publication_year"),
                cited_by_count=work.get("cited_by_count", 0),
                derived_from=evidence_id,
            )
            for work in results
            if work.get("id")
        ]

    def fetch_top_works(self, refs: Iterable[WorkRef], n: int = TOP_WORKS) -> list[str]:
        """Read the most-cited works properly and mint one ``paper`` row each (AC11).

        Singleton ``get_work`` lookups are free and uncapped, so this over-fetches: a work
        whose record has no abstract is skipped rather than counted, because a paper row
        without an abstract would claim a reading that never happened.

        Each row is derived from the ``api_query`` that surfaced the work, which is what
        `fixtures/report-sample.json` freezes and what makes the chip traceable to a search
        someone can re-run.
        """
        ordered = sorted(
            {ref.id: ref for ref in refs}.values(), key=lambda r: r.cited_by_count, reverse=True
        )
        minted: list[str] = []
        for ref in ordered[: n * TOP_WORKS_OVERFETCH]:
            if len(minted) >= n:
                break
            payload, _display, status = self._get(f"works/{ref.id}", {"select": WORK_SELECT})
            if payload is None or status != 200:
                continue
            abstract = _abstract(payload)
            if not abstract:
                continue  # no abstract means nothing was read; do not claim otherwise
            authors = [
                a["author"]["display_name"]
                for a in (payload.get("authorships") or [])[:6]
                if a.get("author", {}).get("display_name")
            ]
            try:
                minted.append(self.store.mint(
                    source_type="paper",
                    url=payload.get("id") or f"https://openalex.org/{ref.id}",
                    title=payload.get("display_name") or ref.title,
                    authors=authors,
                    year=payload.get("publication_year"),
                    summary=abstract,  # the store caps this at 400 chars itself
                    derived_from=ref.derived_from,
                    http_status=status,
                ))
            except (ValueError, TypeError) as exc:
                self._note(OPENALEX_FAILED, f"could not store paper {ref.id}: {exc}")
        if len(minted) < n:
            self._note(
                THIN_LITERATURE,
                f"only {len(minted)} of {n} requested works had an abstract to read",
            )
        return minted

    # --- measurements (AC12) ----------------------------------------------------------

    def topic_trend(self, query: str, since_year: int) -> Measure:
        """Works per publication year for a query. Never indexes into an empty list."""
        params = {
            "filter": (
                f"title_and_abstract.search:{query},from_publication_date:{since_year}-01-01"
            ),
            "group_by": "publication_year",
        }
        payload, display, status = self._get("works", params)
        groups = (payload or {}).get("group_by") or []
        by_year = {
            int(g["key"]): int(g.get("count") or 0)
            for g in groups
            if str(g.get("key", "")).isdigit()
        }
        total = float(sum(by_year.values()))
        curve = ", ".join(f"{year} {by_year[year]}" for year in sorted(by_year))
        if payload is None:
            detail = self._unretrieved(status)
        else:
            detail = f"Works per year: {curve}." if curve else "No works matched."

        evidence_id = self._mint_query(
            display, status, f'OpenAlex topic trend: "{query}" by publication year',
            f"{detail}{self._cost(payload)}",
        )
        return Measure(value=total, detail=detail, evidence_id=evidence_id)

    def citing_count(self, work_id: str, since: date) -> Measure:
        """How many works published since ``since`` cite this one."""
        identifier = _work_id(work_id)
        params = {
            "filter": f"cites:{identifier},from_publication_date:{since.isoformat()}",
            "select": "id",
            "per_page": "1",
        }
        payload, display, status = self._get("works", params)
        count = float(self._meta(payload).get("count", 0) or 0)
        detail = (
            self._unretrieved(status) if payload is None else
            f"{int(count)} works published on or after {since.isoformat()} cite {identifier}."
        )

        evidence_id = self._mint_query(
            display, status, f"OpenAlex citing count: {identifier} since {since.isoformat()}",
            f"{detail}{self._cost(payload)}",
        )
        return Measure(value=count, detail=detail, evidence_id=evidence_id)
