"""Explicitly fictional rehearsal fixtures; no API keys, network, or test imports."""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableLambda

from .presentation import PresentationPlan, ProposalSummary, SummaryDraft
from .report import CompetitorTake, GrantFitReport
from .summarizer import summarize
from .ui_agent import design_presentation


class _RehearsalModel(BaseChatModel):
    """Replay prepared structured outputs through the real agent boundaries."""

    output: Any

    @property
    def _llm_type(self) -> str:
        return "fictional-rehearsal"

    def _generate(self, *args, **kwargs):
        raise AssertionError("Rehearsal must not call a real model")

    def with_structured_output(self, schema, **kwargs):
        return RunnableLambda(lambda _: schema.model_validate(self.output))


def fictional_report() -> GrantFitReport:
    """Return invented people, labs, and a call, clearly labelled as demo data."""
    return GrantFitReport(
        pi="Dr Mira Chen · fictional PI",
        grant_call="Future Cities / Resilient Energy · fictional call",
        pi_strengths_and_track_record=(
            "The fictional PI studies solid-state battery interfaces. "
            "Her team combines operando imaging with electrochemical modelling. "
            "A lab-scale interface diagnostic is available; field-scale validation is missing."
        ),
        grant_to_pi_match_pct=86,
        match_rationale=(
            "The call prioritizes safer, longer-lived urban energy storage. "
            "Interface diagnostics align with the PI's methods, "
            "but deployment partners are missing."
        ),
        proposed_direction=(
            "Build a battery-interface early-warning system: combine operando imaging and "
            "electrochemical models to detect degradation before capacity loss. "
            "Compare predictive warning time against conventional monitoring."
        ),
        competitors=[
            CompetitorTake(
                group="VoltForge Lab", institution="Fictional Northbridge Institute",
                their_strengths="Pouch-cell integration and manufacturing scale-up.",
                vs_pi="Their scale-up is stronger; the PI has deeper interface diagnostics.",
                attack="Compete on early failure signals, not factory throughput.",
                avoid="A race to build the largest cell-production line.",
            ),
            CompetitorTake(
                group="IonWorks Group", institution="Fictional Harbour University",
                their_strengths="High-conductivity electrolyte discovery.",
                vs_pi="They lead materials discovery; the PI links interfaces to failure.",
                attack="Make degradation explainable rather than chase conductivity records.",
                avoid="A leaderboard contest on room-temperature conductivity.",
            ),
            CompetitorTake(
                group="GridSense Lab", institution="Fictional Civic Energy Centre",
                their_strengths="Fleet-scale battery monitoring and operational datasets.",
                vs_pi="Their field data is richer; the PI offers mechanism-level insights.",
                attack="Explore a complementary validation partnership.",
                avoid="Claiming field readiness without a deployment partner.",
            ),
        ],
        relevant_past_grants=[
            "Fictional seed award: operando battery-interface diagnostics. "
            "No real award is claimed."
        ],
    )


def rehearsal_draft() -> SummaryDraft:
    """Prepared editorial output: repeatable on stage, not claimed to be generated live."""
    return SummaryDraft.model_validate({
        "title": "A smoke alarm for battery failure",
        "tagline": "Spot the interface warning. Act before the battery fades.",
        "hook": "What if a battery could warn us before its performance starts to fall?",
        "elevator_pitch": (
            "Battery degradation is often noticed after performance drops. We propose an "
            "early-warning system that connects interface images to electrochemical models. "
            "The PI brings the diagnostic toolkit; the call brings the urban-storage challenge. "
            "First prove earlier warning in the lab, then seek a deployment partner."
        ),
        "grant_fit": {
            "value": 89,
            "rationale": "Early failure warning supports safer, longer-lived storage.",
            "evidence": {
                "source": "match_rationale",
                "quote": "The call prioritizes safer, longer-lived urban energy storage.",
            },
        },
        "novelty": {
            "value": 81,
            "rationale": "Mechanism-level early warning differentiates within this report only.",
            "evidence": {
                "source": "proposed_direction",
                "quote": "detect degradation before capacity loss",
            },
        },
        "competition_risk": {
            "value": 38,
            "rationale": "Rivals have scale and data advantages, but there is room to specialize.",
            "evidence": {
                "source": "competitors",
                "quote": "Their field data is richer; the PI offers mechanism-level insights.",
            },
        },
        "strengths": [
            {
                "text": "See the failure mechanism, not just the symptom.",
                "evidence": {
                    "source": "pi_strengths_and_track_record",
                    "quote": "studies solid-state battery interfaces",
                },
            },
            {
                "text": "Connect live images to predictive models.",
                "evidence": {
                    "source": "pi_strengths_and_track_record",
                    "quote": "combines operando imaging with electrochemical modelling",
                },
            },
            {
                "text": "Start with an existing lab diagnostic, not a blank page.",
                "evidence": {
                    "source": "pi_strengths_and_track_record",
                    "quote": "A lab-scale interface diagnostic is available",
                },
            },
        ],
        "differentiator": (
            "Don't build a bigger battery. Test whether interface-level signals can make "
            "battery failure visible earlier."
        ),
        "milestones": [
            {
                "label": "Find the warning",
                "outcome": "Identify interface signals before capacity loss.",
            },
            {
                "label": "Prove the lead time",
                "outcome": "Benchmark warning time against conventional monitoring.",
            },
            {
                "label": "Bridge to the field",
                "outcome": "Seek a deployment partner and scope a validation pilot.",
            },
        ],
        "caveats": [
            "Entirely fictional rehearsal: PI, call, labs, award, and scores are invented.",
            "Scientific novelty needs a literature search beyond the analyst report.",
            "Field-scale validation and deployment partners are missing.",
        ],
    })


def rehearsal_plan() -> PresentationPlan:
    return PresentationPlan.model_validate({
        "theme": "aurora", "spotlight": "grant_fit",
        "scenes": [
            {"section": "scorecard", "speaker_note": (
                "These are fictional heuristic scores, not funding odds. Ask the audience: "
                "what if competition risk rose to 80? Move the slider and show the trade-off."
            )},
            {"section": "strategy", "speaker_note": (
                "The strategy is not to beat everyone at everything. Point to the early-warning "
                "angle, then open one evidence quote to show where the claim came from."
            )},
            {"section": "roadmap", "speaker_note": (
                "End with a testable idea rather than a long proposal. These are proposed "
                "milestones. The missing deployment partner is a gap, not a hidden success."
            )},
        ],
    })


def run_rehearsal() -> tuple[ProposalSummary, PresentationPlan]:
    """Run both new agents with prepared outputs; bypass live analyst research explicitly."""
    summary = summarize(fictional_report(), model=_RehearsalModel(output=rehearsal_draft()))
    plan = design_presentation(summary, model=_RehearsalModel(output=rehearsal_plan()))
    return summary, plan