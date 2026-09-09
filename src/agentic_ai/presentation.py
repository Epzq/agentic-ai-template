"""Typed contracts shared by the summarizer, UI agent, and trusted renderer."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .report import GrantFitReport

ShortText = Annotated[str, Field(min_length=1, max_length=220)]
SourceField = Literal[
    "grant_call",
    "pi_strengths_and_track_record",
    "match_rationale",
    "proposed_direction",
    "competitors",
    "relevant_past_grants",
]
Metric = Literal["grant_fit", "novelty", "pi_match", "competition_risk"]
Section = Literal["scorecard", "strategy", "roadmap"]

# Risk is inverted BEFORE weighting. Keep the browser simulator on the same rubric.
SCORE_WEIGHTS: dict[Metric, int] = {
    "grant_fit": 35,
    "novelty": 25,
    "pi_match": 25,
    "competition_risk": 15,
}


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceRef(Contract):
    source: SourceField
    quote: Annotated[str, Field(min_length=1, max_length=300)]


class Insight(Contract):
    text: ShortText
    evidence: EvidenceRef


class ScoreEstimate(Contract):
    value: Annotated[int, Field(strict=True, ge=0, le=100)] | None
    rationale: ShortText
    evidence: EvidenceRef | None

    @model_validator(mode="after")
    def require_evidence(self) -> ScoreEstimate:
        if self.value is not None and self.evidence is None:
            raise ValueError("A numeric estimate requires analyst evidence; use null if unknown")
        return self


class Milestone(Contract):
    label: Annotated[str, Field(min_length=1, max_length=50)]
    outcome: ShortText


class SummaryDraft(Contract):
    """Only the fields the summarizer may generate; no authority to change PI match."""

    title: Annotated[str, Field(min_length=1, max_length=70)]
    tagline: Annotated[str, Field(min_length=1, max_length=120)]
    hook: ShortText
    elevator_pitch: Annotated[str, Field(min_length=1, max_length=450)]
    grant_fit: ScoreEstimate
    novelty: ScoreEstimate
    competition_risk: ScoreEstimate
    strengths: Annotated[list[Insight], Field(max_length=3)]
    differentiator: ShortText
    milestones: Annotated[list[Milestone], Field(min_length=3, max_length=3)]
    caveats: Annotated[list[ShortText], Field(min_length=1, max_length=4)]


def source_text(report: GrantFitReport, source: SourceField) -> str:
    """Expose original field text without invented source URLs or citations."""
    value = getattr(report, source)
    if source == "competitors":
        return "\n".join(str(v) for item in value for v in item.model_dump().values())
    if isinstance(value, list):
        return "\n".join(value)
    return str(value)


def overall_score(values: dict[Metric, int | None]) -> int | None:
    """Return a rounded heuristic, or unknown if any component is unknown."""
    total = 0
    for metric, weight in SCORE_WEIGHTS.items():
        value = values[metric]
        if value is None:
            return None
        total += weight * (100 - value if metric == "competition_risk" else value)
    return (total + 50) // 100


class ProposalSummary(SummaryDraft):
    """Validated handoff, retaining the original report for provenance and audit."""

    analyst_report: GrantFitReport

    @model_validator(mode="after")
    def verify_quotes(self) -> ProposalSummary:
        if not self.analyst_report.competitors and self.competition_risk.value is not None:
            raise ValueError("Competition risk must be unknown when competitor evidence is absent")
        refs = [item.evidence for item in self.strengths]
        for estimate in (self.grant_fit, self.novelty, self.competition_risk):
            if estimate.evidence is not None:
                refs.append(estimate.evidence)
        for ref in refs:
            original = source_text(self.analyst_report, ref.source)
            if not ref.quote.strip() or ref.quote not in original:
                raise ValueError(f"Evidence quote not found in analyst field: {ref.source}")
        return self

    @property
    def scores(self) -> dict[Metric, int | None]:
        return {
            "grant_fit": self.grant_fit.value,
            "novelty": self.novelty.value,
            "pi_match": self.analyst_report.grant_to_pi_match_pct,
            "competition_risk": self.competition_risk.value,
        }

    @property
    def overall_score(self) -> int | None:
        return overall_score(self.scores)


class Scene(Contract):
    section: Section
    speaker_note: Annotated[str, Field(min_length=1, max_length=300)]


class PresentationPlan(Contract):
    """The UI agent chooses composition, not executable HTML, scripts, or scores."""

    theme: Literal["aurora", "ember"]
    spotlight: Metric
    scenes: Annotated[list[Scene], Field(min_length=3, max_length=3)]

    @model_validator(mode="after")
    def require_each_section(self) -> PresentationPlan:
        if {scene.section for scene in self.scenes} != {"scorecard", "strategy", "roadmap"}:
            raise ValueError("Include scorecard, strategy, and roadmap exactly once")
        return self