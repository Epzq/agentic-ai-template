"""The evidence store — Python mints, the LLM only cites.

This module is where the product's one guarantee lives. Every record here was created by
retrieval code from something we actually fetched; no model ever authors one. LLM outputs
carry evidence *IDs* and nothing else (see ``llm_schemas``), so a fabricated citation has
nowhere to live: an ID either resolves to a row in this store or it is dropped.

``Evidence`` is the one model in the codebase that legitimately has a ``url``, which is
why AC5's walk deliberately excludes it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SourceType = Literal["grant_doc", "webpage", "paper", "api_query"]

#: ``warn(code, message)``. WI-1.3's ``Run.warning`` is wired into this slot by the
#: pipeline; keeping it a plain callable means the store has no dependency on the event
#: system and can be tested on its own.
#:
#: The return is ``object``, not ``None``: ``Run.warning`` returns the ``Event`` it emitted,
#: which is useful to its own callers, and ``Callable[..., None]`` would reject it — return
#: types are covariant, so a callable returning ``Event`` is not one returning ``None``.
#: ``object`` says what is meant, which is that we ignore whatever comes back.
WarnFn = Callable[[str, str], object]

#: AC10a — an LLM cited an ID that is not in the store. The ID is dropped, never fatal.
UNRESOLVABLE_EVIDENCE_ID = "unresolvable_evidence_id"
#: AC10b — a citing node is still under its floor after one retry.
THIN_EVIDENCE = "thin_evidence"

#: AC3: "every direction cites >= 2 evidence IDs". Per-model overridable — a single
#: criterion score only needs one (``plan.md`` §7.2).
EVIDENCE_FLOOR = 2

#: ``demo-spec.md`` §6.1: "summary: str  # <=400 chars, shown in the chip hover".
SUMMARY_MAX_CHARS = 400


class Evidence(BaseModel):
    """One retrieved record. ``demo-spec.md`` §6.1.

    The nullable fields default to ``None`` so a call site states only what it actually
    has, but AC4's provenance rules are enforced rather than trusted: a ``grant_doc``
    without a page and a hash, or a ``webpage`` that did not return 200, is a bug in the
    retrieval code and is refused here rather than reaching the report.
    """

    # A misspelt kwarg to mint() must not be silently swallowed: that is how a row loses
    # its sha256 or its http_status and quietly fails AC4.
    model_config = ConfigDict(extra="forbid")

    id: str
    source_type: SourceType
    url: str | None = None
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    page: int | None = None          # grant_doc
    sha256: str | None = None        # grant_doc
    quote: str | None = None
    summary: str = ""                # <=400 chars, shown in the chip hover
    derived_from: str | None = None  # paper -> the api_query row it came from
    http_status: int | None = None
    retrieved_at: datetime

    @field_validator("summary", mode="before")
    @classmethod
    def _cap_summary(cls, v: Any) -> Any:
        """Truncate rather than raise.

        An OpenAlex abstract is routinely 1,200-2,200 chars. Refusing one would kill a
        run four minutes in over a display-length rule, so the excess is trimmed at a
        word boundary and marked with an ellipsis.
        """
        if not isinstance(v, str) or len(v) <= SUMMARY_MAX_CHARS:
            return v
        return v[: SUMMARY_MAX_CHARS - 2].rsplit(" ", 1)[0].rstrip(",.;:") + " …"

    @model_validator(mode="after")
    def _provenance_matches_source_type(self) -> Evidence:
        """AC4, restated as code.

        "No record carries a URL the system did not either fetch or receive inside a
        fetched API response" cannot be checked from inside the model, but everything
        that identifies *how* a row was obtained can be.
        """
        missing: list[str] = []
        if self.source_type == "grant_doc":
            if self.page is None:
                missing.append("page")
            if not self.sha256:
                missing.append("sha256")
        elif self.source_type == "webpage":
            if not self.url:
                missing.append("url")
            if self.http_status != 200:
                missing.append(f"http_status==200 (got {self.http_status!r})")
        elif self.source_type == "api_query":
            if not self.url:
                missing.append("url (the full request URL)")
            if self.http_status is None:
                missing.append("http_status")
        elif self.source_type == "paper":
            if not self.derived_from:
                missing.append("derived_from (the api_query row it came from)")

        if missing:
            raise ValueError(
                f"{self.source_type} evidence {self.id!r} is missing "
                f"{', '.join(missing)} — AC4 requires it"
            )
        return self


class EvidenceStore:
    """Mints and resolves evidence IDs for one run.

    IDs are short and sequential (``e1``, ``e2``, …) rather than content hashes: models
    copy short tokens far more reliably, and an unresolvable one costs a dropped chip
    rather than a dead stage.
    """

    def __init__(self) -> None:
        self._rows: dict[str, Evidence] = {}
        self._minted = 0

    def mint(self, **fields: Any) -> str:
        """Create one record and return its ID.

        Only retrieval code calls this. Raises on a malformed record — that is a bug in
        our own code, not an external failure, and silently storing a row with broken
        provenance would defeat the point of having AC4 at all.
        """
        if "id" in fields:
            raise ValueError("mint() assigns the id; do not pass one")
        evidence_id = f"e{self._minted + 1}"

        derived_from = fields.get("derived_from")
        if derived_from is not None:
            parent = self._rows.get(derived_from)
            if parent is None:
                raise ValueError(
                    f"{evidence_id} derives from {derived_from!r}, which is not in the store"
                )
            # AC4: a paper must point at an api_query record that itself logged a 200.
            if fields.get("source_type") == "paper" and (
                parent.source_type != "api_query" or parent.http_status != 200
            ):
                raise ValueError(
                    f"{evidence_id} is a paper derived from {derived_from!r}, which is a "
                    f"{parent.source_type} with http_status {parent.http_status!r}; AC4 "
                    f"requires an api_query with a logged 200"
                )

        fields.setdefault("retrieved_at", datetime.now(UTC))
        row = Evidence(id=evidence_id, **fields)
        self._rows[evidence_id] = row
        self._minted += 1
        return evidence_id

    def fork(self) -> EvidenceStore:
        """A private copy, for a run that starts from a cached probe's ingestion.

        The probe caches its store so a run does not re-fetch seven PDFs. Handing the same
        object to every run that quotes that `probe_id` made the cache a shared mutable
        bucket: the second run began holding the first run's 85 rows, minted its own on top,
        and its report listed — and could cite — evidence gathered for somebody else's run.
        Pressing **Analyse** twice on the same inputs was all it took.

        `Evidence` rows are written once by `mint` and never touched again, so copying the
        mapping is enough; the rows themselves can be shared. `_minted` comes along so the
        new store keeps numbering where the probe left off rather than reissuing `e1`.
        """
        clone = EvidenceStore()
        clone._rows = dict(self._rows)
        clone._minted = self._minted
        return clone

    def get(self, evidence_id: str) -> Evidence | None:
        return self._rows.get(evidence_id)

    def resolve_ids(self, ids: Iterable[str]) -> tuple[list[str], list[str]]:
        """Split cited IDs into ``(kept, dropped)``.

        Order is preserved and duplicates collapse into the first mention — a model that
        cites ``e4`` twice meant it once.
        """
        kept: list[str] = []
        dropped: list[str] = []
        seen: set[str] = set()
        for evidence_id in ids:
            if evidence_id in seen:
                continue
            seen.add(evidence_id)
            (kept if evidence_id in self._rows else dropped).append(evidence_id)
        return kept, dropped

    def all(self) -> list[Evidence]:
        """Every record, in mint order."""
        return list(self._rows.values())

    def of_type(self, source_type: SourceType) -> list[Evidence]:
        """Every record of one kind — AC11 counts ``paper`` rows with this."""
        return [row for row in self._rows.values() if row.source_type == source_type]

    def __contains__(self, evidence_id: object) -> bool:
        return evidence_id in self._rows

    def __len__(self) -> int:
        return len(self._rows)


@dataclass
class CitationContext:
    """Validation context for LLM outputs that cite evidence IDs.

    Passed as ``Model.model_validate(payload, context=ctx)``; the ``CitesEvidence``
    validator reaches it through ``ValidationInfo.context``. One instance per LLM call,
    so ``dropped`` is a record of what that call got wrong.
    """

    store: EvidenceStore
    warn: WarnFn | None = None
    dropped: list[str] = field(default_factory=list)

    def resolve(self, ids: list[str], owner: str) -> list[str]:
        """Keep the IDs that resolve, drop the rest, and say so (AC10a)."""
        kept, dropped = self.store.resolve_ids(ids)
        if dropped:
            self.dropped.extend(dropped)
            if self.warn is not None:
                self.warn(
                    UNRESOLVABLE_EVIDENCE_ID,
                    f"{owner} cited {len(dropped)} evidence id(s) not in the store "
                    f"({', '.join(dropped)}); dropped.",
                )
        return kept
