"""The report — assembled in Python, rendered by Jinja, never written by a model.

Three fields on every direction are **Python's, not the model's**: `rank` and `overall` are
arithmetic (rule 2), and `thin_evidence` is a verdict about the model's own output, which it
is in no position to make about itself.

Every link in `report.md` is resolved from the evidence store by ID. No URL in the rendered
file came from an LLM response, which is what AC13 checks.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from jinja2 import Environment
from pydantic import BaseModel, Field

from roia.evidence import EVIDENCE_FLOOR, Evidence, EvidenceStore
from roia.llm_schemas import (
    CRITERIA,
    NOT_ASSESSED,
    CriterionScore,
    DirectionDraft,
    DirectionSection,
)
from roia.openalex import AuthorMatch, Measure
from roia.ranking import DEFAULT_WEIGHTS, compute_ranking, confidence_for


class ReportInputs(BaseModel):
    grant_url: str
    profile_url: str
    grant_document: str | None = None
    grant_sha256: str | None = None


class ReportIdentity(BaseModel):
    """Always ``unverified`` — disambiguation is a non-goal (§4) and the banner says so."""

    author_id: str
    display_name: str
    institution: str | None = None
    confidence: str = "unverified"
    margin: float = 0.0


class Direction(BaseModel):
    """One ranked direction, as the report and the browser see it."""

    rank: int
    overall: float
    confidence: str
    #: Set from the evidence floor, never claimed by the model about its own output.
    thin_evidence: bool
    title: str
    problem_statement: DirectionSection
    evidence_backed_gap: DirectionSection
    key_strengths: list[str] = Field(default_factory=list)
    key_weaknesses: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    #: All nine criteria in §6.4 order; the two non-goals are ``None``.
    scores: dict[str, CriterionScore | None]


class Report(BaseModel):
    run_id: str
    generated_at: datetime
    inputs: ReportInputs
    identity: ReportIdentity | None = None
    weights: dict[str, float]
    directions: list[Direction] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


def build_report(
    run_id: str,
    inputs: ReportInputs,
    drafts: list[DirectionDraft],
    store: EvidenceStore,
    *,
    identity: AuthorMatch | None = None,
    weights: dict[str, float] | None = None,
    generated_at: datetime | None = None,
) -> Report:
    """§5 step 9 — rank the directions and assemble the report. No model is involved."""
    active = weights or DEFAULT_WEIGHTS
    ranked = sorted(
        drafts,
        key=lambda d: compute_ranking(_nine(d), active),
        reverse=True,
    )
    directions = [
        Direction(
            rank=position,
            overall=compute_ranking(_nine(draft), active),
            confidence=confidence_for(
                _nine(draft), thin_evidence=len(draft.evidence_ids) < EVIDENCE_FLOOR
            ),
            thin_evidence=len(draft.evidence_ids) < EVIDENCE_FLOOR,
            title=draft.title,
            problem_statement=draft.problem_statement,
            evidence_backed_gap=draft.evidence_backed_gap,
            key_strengths=draft.key_strengths,
            key_weaknesses=draft.key_weaknesses,
            evidence_ids=draft.evidence_ids,
            scores=_nine(draft),
        )
        for position, draft in enumerate(ranked, start=1)
    ]
    return Report(
        run_id=run_id,
        generated_at=generated_at or datetime.now(UTC),
        inputs=inputs,
        identity=(
            ReportIdentity(
                author_id=identity.author_id,
                display_name=identity.display_name,
                institution=identity.institution,
                confidence=identity.confidence,
                margin=identity.margin,
            )
            if identity is not None
            else None
        ),
        weights=active,
        directions=directions,
        evidence=store.all(),
    )


def _nine(draft: DirectionDraft) -> dict[str, CriterionScore | None]:
    """All nine criteria in §6.4 order, with the two non-goals as ``None``.

    The LLM is asked for seven; the report carries nine so the UI can render "not assessed"
    rather than silently omitting a column.
    """
    return {
        name: None if name in NOT_ASSESSED else getattr(draft.scores, name)
        for name in CRITERIA
    }


# --- rendering -------------------------------------------------------------------------

TEMPLATE = """\
# Research directions for {{ report.inputs.grant_url }}

{% if report.identity -%}
Analysing **{{ report.identity.display_name }}**{% if report.identity.institution %} at
**{{ report.identity.institution }}**{% endif %} — *{{ report.identity.confidence }}*.
Author identity is resolved automatically and not cross-checked; correct it if it is wrong.
{%- else -%}
No researcher could be resolved from the profile page.
{%- endif %}

Generated {{ report.generated_at.strftime('%Y-%m-%d %H:%M') }} UTC from {{ counts }}.

*Confidence* is derived from each direction's `evidence_strength` score, not asserted by the
model — it says how well **supported** a direction is, not how good it is. A lower-ranked
direction resting on a large, well-measured literature can honestly read *high*.
{% if warnings %}
## ⚠️ What this run is unsure about

{{ warnings|length }} warning{{ 's were' if warnings|length != 1 else ' was' }} recorded.
These belong in the report rather than in a log: the tool says where it is less certain
instead of presenting everything at the same confidence.

{% for warning in warnings -%}
- **{{ warning.code }}** — {{ warning.message }}
{% endfor %}
{%- endif %}
{% for direction in report.directions %}
## {{ direction.rank }}. {{ direction.title }}

**{{ '%.2f'|format(direction.overall) }}** overall · confidence *{{ direction.confidence }}*
{%- if direction.thin_evidence %} · ⚠️ **thin evidence**{% endif %}

### The problem

{{ direction.problem_statement.text }}

{{ cite(direction.problem_statement.evidence_ids) }}

### The gap

{{ direction.evidence_backed_gap.text }}

{{ cite(direction.evidence_backed_gap.evidence_ids) }}

{% if direction.key_strengths -%}
### Strengths
{% for item in direction.key_strengths %}
- {{ item }}
{%- endfor %}
{%- endif %}

{% if direction.key_weaknesses -%}
### Weaknesses
{% for item in direction.key_weaknesses %}
- {{ item }}
{%- endfor %}
{%- endif %}

### Scores

| Criterion | Score | Why | Evidence |
|---|---|---|---|
{% for name, score in direction.scores.items() -%}
{{ score_row(name, score) }}
{% endfor -%}
{% endfor %}
## Evidence

Every row below was retrieved by the tool. Nothing here was written by a model.

| ID | Type | Source | Retrieved |
|---|---|---|---|
{% for row in report.evidence -%}
{{ evidence_row(row) }}
{% endfor %}
"""


def render_markdown(report: Report, warnings: Sequence[Any] = ()) -> str:
    """§5 step 10 — a Jinja template, no LLM.

    Both helpers resolve IDs against the report's own evidence list, so a link can only
    exist if the row does (AC13). An ID with no row renders as bare text rather than a
    dangling link.

    `warnings` are the run's `warning` events. They are optional because `Report` does not
    carry them — they live on the event log — but leaving them out is how the markdown
    ended up being the one view of a run that hid them. The browser puts two
    `quote_unverified` alerts at the top of the demo run; the file a reviewer forwards to a
    colleague showed nothing at all, which inverts AC9 in the exact place it matters most.
    Anything with `.code` and `.message` will do, so this stays free of `roia.events`.
    """
    rows = {row.id: row for row in report.evidence}

    def link(row: Evidence) -> str:
        label = row.title.replace("|", "\\|")
        return f"[{label}]({row.url})" if row.url else label

    def cite(ids: list[str]) -> str:
        parts = [
            f"[{row.id}]({row.url})" if row.url else row.id
            for row in (rows.get(i) for i in ids)
            if row is not None
        ]
        return " · ".join(parts)

    def score_row(name: str, score: CriterionScore | None) -> str:
        """One markdown table row. Built here rather than in the template, because a
        wrapped template line emits a real newline and breaks the table."""
        if score is None:
            return f"| {name} | — | not assessed in this build | |"
        why = score.rationale.replace("|", "\\|").replace("\n", " ")
        return f"| {name} | {score.value:.1f} | {why} | {cite(score.evidence_ids)} |"

    def evidence_row(row: Evidence) -> str:
        return (
            f"| {row.id} | {row.source_type} | {link(row)} "
            f"| {row.retrieved_at.strftime('%Y-%m-%d')} |"
        )

    papers = sum(1 for row in report.evidence if row.source_type == "paper")
    # "read in full" was not true and `demo-spec.md` says so twice: §4 makes paper full text
    # an explicit non-goal ("the demo reads OpenAlex abstracts only"), and §10 lists "papers
    # are read as abstracts not full text" among the things the demo must *say* — "claiming
    # otherwise invites the one question you cannot answer". It is not even the whole
    # abstract: `Evidence.summary` caps at 400 characters, and all twelve paper rows on the
    # recorded run are truncated at that cap.
    counts = (
        f"{len(report.evidence)} retrieved records, "
        f"of which {papers} are papers whose abstracts were retrieved"
    )

    environment = Environment(autoescape=False, trim_blocks=False)  # noqa: S701 - markdown
    template = environment.from_string(TEMPLATE)
    # Read defensively: `Event` is `extra="allow"`, so a malformed warning must degrade to
    # a visible row rather than blow up the whole render four minutes into a run.
    warning_rows = [
        {
            "code": str(getattr(event, "code", "") or "warning"),
            "message": str(getattr(event, "message", "") or "").replace("\n", " "),
        }
        for event in warnings
    ]

    return template.render(
        report=report, counts=counts, cite=cite, link=link,
        score_row=score_row, evidence_row=evidence_row, warnings=warning_rows,
    )


def measure_lines(trends: list[Measure], citings: list[Measure]) -> list[str]:
    """The numbers behind AC12, already in renderable English from `Measure.detail`.

    Reused rather than re-derived: the renderer must never retype a count the model was
    forbidden to state.
    """
    return [m.detail for m in [*trends, *citings] if m.detail]


def report_dict(report: Report) -> dict[str, Any]:
    """`report.json`, the exact shape `fixtures/report-sample.json` freezes."""
    return report.model_dump(mode="json")
