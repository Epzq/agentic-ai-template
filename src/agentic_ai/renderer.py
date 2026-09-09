"""Render agent data with trusted, offline assets; model text is never executable."""

from __future__ import annotations

import json
from html import escape
from importlib.resources import files
from math import cos, pi, sin
from pathlib import Path
from string import Template

from .presentation import (
    SCORE_WEIGHTS,
    EvidenceRef,
    Metric,
    PresentationPlan,
    ProposalSummary,
    Section,
    source_text,
)

_LABELS: dict[Metric, str] = {
    "grant_fit": "Grant Fit",
    "novelty": "Novelty",
    "pi_match": "PI Match",
    "competition_risk": "Competition Risk",
}
_SECTIONS: dict[Section, str] = {
    "scorecard": "The opportunity",
    "strategy": "The competitive edge",
    "roadmap": "The proof plan",
}


def _e(value: object) -> str:
    return escape(str(value), quote=True)


def _brief(text: str, limit: int = 180) -> str:
    """Keep original analyst prose card-sized; full text remains in the evidence drawer."""
    if len(text) <= limit:
        return text
    prefix = text[:limit - 1]
    return (prefix.rsplit(" ", 1)[0] if " " in prefix else prefix) + "…"


def _citation(ref: EvidenceRef | None) -> str:
    if ref is None:
        return '<span class="muted">No supporting evidence supplied.</span>'
    return (
        f'<a class="citation" href="#source-{ref.source}">Analyst · '
        f'{_e(ref.source.replace("_", " "))}</a><blockquote>{_e(ref.quote)}</blockquote>'
    )


def _radar(summary: ProposalSummary) -> str:
    """All radar axes point outward for stronger opportunity, including inverse risk."""
    values = summary.scores
    if any(value is None for value in values.values()):
        return (
            '<p class="radar-unknown">Shape withheld<br>'
            '<small>Evidence is incomplete</small></p>'
        )
    numbers = [values["grant_fit"], values["novelty"], values["pi_match"]]
    risk = values["competition_risk"]
    numbers.append(100 - risk if risk is not None else None)
    points = []
    for index, value in enumerate(numbers):
        angle = -pi / 2 + index * pi / 2
        radius = (value or 0) * 0.95
        points.append(f"{150 + cos(angle) * radius:.1f},{125 + sin(angle) * radius:.1f}")
    grid = "".join(
        f'<polygon points="150,{125-r} {150+r},125 150,{125+r} {150-r},125"/>'
        for r in (24, 48, 72, 95)
    )
    return (
        '<svg viewBox="0 0 300 260" role="img" aria-label="Opportunity radar: '
        'Grant Fit, Novelty, PI Match, and 100 minus Competition Risk">'
        f'<g class="radar-grid">{grid}<path d="M150 30V220M55 125H245"/></g>'
        f'<polygon class="radar-fill" points="{" ".join(points)}"/>'
        '<g class="radar-label"><text x="150" y="17">Grant Fit</text>'
        '<text x="274" y="130">Novelty</text><text x="150" y="247">PI Match</text>'
        '<text x="26" y="118">Risk</text><text x="26" y="134">buffer</text></g></svg>'
    )


def _scorecard(summary: ProposalSummary, plan: PresentationPlan) -> str:
    cards = []
    sliders = []
    for metric, label in _LABELS.items():
        value = summary.scores[metric]
        display = "?" if value is None else str(value)
        if metric == "pi_match":
            rationale = summary.analyst_report.match_rationale
            citation = '<a class="citation" href="#source-match_rationale">Original rationale</a>'
            provenance = "Original analyst estimate"
        else:
            estimate = getattr(summary, metric)
            rationale = estimate.rationale
            citation = _citation(estimate.evidence)
            provenance = "Summarizer heuristic · not independently verified"
        direction = "Lower is better" if metric == "competition_risk" else "Higher is better"
        classes = "metric spotlight" if metric == plan.spotlight else "metric"
        if metric == "competition_risk":
            classes += " risk"
        cards.append(
            f'<article class="{classes}"><div class="eyebrow">{label}</div>'
            f'<div class="metric-value">{display}<small>/100</small></div>'
            f'<div class="bar"><span style="width:{value or 0}%"></span></div>'
            f'<p class="direction">{direction}</p><p>{_e(_brief(rationale))}</p>'
            f'<details><summary>Why this score?</summary><p class="muted">{provenance}</p>'
            f'{citation}</details></article>'
        )
        disabled = " disabled" if value is None else ""
        sliders.append(
            f'<label class="slider-label" for="sim-{metric}">{label}'
            f'<output id="out-{metric}">{display}</output></label>'
            f'<input id="sim-{metric}" data-metric="{metric}" type="range" '
            f'min="0" max="100" value="{value or 0}"{disabled} '
            f'aria-label="Hypothetical {label}; {direction.lower()}">'
        )
    overall = "?" if summary.overall_score is None else str(summary.overall_score)
    return (
        '<div class="section-heading"><div><p class="eyebrow">01 / Decision intelligence</p>'
        '<h2>Big idea. Clear signals.</h2></div>'
        '<span class="pill">Heuristics, not odds</span></div>'
        f'<div class="metrics">{"".join(cards)}</div>'
        '<div class="score-bottom"><article class="panel radar"><h3>The opportunity shape</h3>'
        f'{_radar(summary)}<p class="muted">Risk buffer = 100 − Competition Risk. '
        'Larger means stronger on this rubric, not a funding forecast.</p></article>'
        '<article class="panel simulator"><div class="eyebrow">Audience lab</div>'
        '<h3>What would change your mind?</h3><p>Move a signal. Watch the trade-off.</p>'
        f'<div class="sim-grid"><div>{"".join(sliders)}</div><div class="scenario">'
        f'<span id="scenario-score" aria-live="polite">{overall}</span><small>/100</small>'
        '<p>Hypothetical overall</p><p id="scenario-delta" class="accent">Baseline</p></div></div>'
        '<button id="reset-scenario" class="quiet" type="button">'
        'Reset to analyst + summary</button>'
        '<p class="muted">Local simulation only. No new research or model call; '
        'the original scorecard and export stay unchanged. Unknown inputs stay unknown.</p>'
        '<details><summary>Show the scoring recipe</summary><p>Overall = '
        '35% Grant Fit + 25% Novelty + 25% PI Match + 15% (100 − Competition Risk), '
        'rounded to the nearest integer. Withheld if any component is unknown.</p></details>'
        '</article></div>'
    )


def _strategy(summary: ProposalSummary) -> str:
    strengths = "".join(
        f'<article class="strength"><span class="accent">0{i}</span><p>{_e(item.text)}</p>'
        f'<details><summary>Evidence</summary>{_citation(item.evidence)}</details></article>'
        for i, item in enumerate(summary.strengths, 1)
    ) or '<p class="muted">No defensible PI strengths could be extracted from this report.</p>'
    competitors = "".join(
        f'<article class="panel competitor"><p class="eyebrow">{_e(item.institution)}</p>'
        f'<h3>{_e(item.group)}</h3><p>{_e(_brief(item.their_strengths))}</p>'
        f'<div class="edge"><b>Our angle</b><p>{_e(_brief(item.attack))}</p></div>'
        f'<div class="avoid"><b>Avoid head-on</b><p>{_e(_brief(item.avoid))}</p></div>'
        f'<details><summary>PI comparison</summary><p>{_e(item.vs_pi)}</p></details></article>'
        for item in summary.analyst_report.competitors[:3]
    ) or '<article class="panel">Competitor evidence is missing. Unknown is not low risk.</article>'
    count = len(summary.analyst_report.competitors)
    return (
        '<div class="section-heading"><div><p class="eyebrow">02 / Positioning</p>'
        '<h2>Don’t outspend. Out-position.</h2></div></div>'
        f'<div class="strengths">{strengths}</div>'
        '<article class="thesis"><p class="eyebrow">Differentiation hypothesis · to validate</p>'
        f'<h3>{_e(summary.differentiator)}</h3></article>'
        f'<div class="competitors">{competitors}</div>'
        f'<p class="muted">Showing {min(count, 3)} of {count} analyst-listed competitors; '
        'not an exhaustive market scan. Full report below.</p>'
    )


def _roadmap(summary: ProposalSummary) -> str:
    milestones = "".join(
        f'<article class="panel milestone"><span class="step">{i:02d}</span>'
        f'<h3>{_e(item.label)}</h3><p>{_e(item.outcome)}</p></article>'
        for i, item in enumerate(summary.milestones, 1)
    )
    caveats = "".join(f"<li>{_e(item)}</li>" for item in summary.caveats)
    return (
        '<div class="section-heading"><div><p class="eyebrow">03 / From promise to proof</p>'
        '<h2>Three moves. One testable idea.</h2></div>'
        '<span class="pill">Proposed, not completed</span></div>'
        f'<div class="milestones">{milestones}</div>'
        '<div class="pitch-grid"><article class="panel pitch">'
        '<p class="eyebrow">The 30-second pitch</p>'
        f'<p class="pitch-text">{_e(summary.elevator_pitch)}</p></article>'
        '<article class="panel caveats"><p class="eyebrow">What we still need to know</p>'
        f'<ul>{caveats}</ul><p class="muted">Validate eligibility, novelty, and all external '
        'claims before using this in a real submission.</p></article></div>'
    )


def render_presentation(
    summary: ProposalSummary, plan: PresentationPlan, *, fictional: bool = False
) -> str:
    """Create a self-contained HTML dashboard. No CDNs, analytics, or model-written code."""
    sections = {
        "scorecard": _scorecard(summary, plan),
        "strategy": _strategy(summary),
        "roadmap": _roadmap(summary),
    }
    scenes = "".join(
        f'<section id="{scene.section}" class="scene" aria-label="{_SECTIONS[scene.section]}">'
        f'{sections[scene.section]}<aside class="speaker-note"><b>Presenter cue</b> '
        f'{_e(scene.speaker_note)}</aside></section>'
        for scene in plan.scenes
    )
    nav = "".join(
        f'<button type="button" data-scene="{i}">{i+1:02d} {_SECTIONS[scene.section]}</button>'
        for i, scene in enumerate(plan.scenes)
    )
    evidence = "".join(
        f'<details id="source-{field}"><summary>{_e(field.replace("_", " ").title())}</summary>'
        f'<pre>{_e(source_text(summary.analyst_report, field))}</pre></details>'
        for field in (
            "grant_call", "pi_strengths_and_track_record", "match_rationale",
            "proposed_direction", "competitors", "relevant_past_grants",
        )
    )
    payload = json.dumps({
        "summary": summary.model_dump(), "plan": plan.model_dump(),
        "scores": summary.scores, "overall_score": summary.overall_score,
        "weights": SCORE_WEIGHTS, "fictional": fictional,
    }, ensure_ascii=False)
    # JSON inside <script type=application/json> still needs raw-text escaping.
    payload = payload.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    assets = files("agentic_ai").joinpath("assets")
    template = Template(assets.joinpath("proposal.html").read_text(encoding="utf-8"))
    mode = (
        "FICTIONAL REHEARSAL · NOT REAL RESEARCH"
        if fictional else "AI-GENERATED · VERIFY CLAIMS"
    )
    return template.substitute(
        title=_e(summary.title), tagline=_e(summary.tagline), hook=_e(summary.hook),
        pi=_e(summary.analyst_report.pi), grant=_e(summary.analyst_report.grant_call),
        overall="?" if summary.overall_score is None else summary.overall_score,
        ring=summary.overall_score or 0, theme=plan.theme,
        mode=mode,
        scenes=scenes, nav=nav, evidence=evidence, payload=payload,
        css=assets.joinpath("proposal.css").read_text(encoding="utf-8"),
        script=assets.joinpath("proposal.js").read_text(encoding="utf-8"),
    )


def save_presentation(
    summary: ProposalSummary,
    plan: PresentationPlan,
    path: str | Path,
    *,
    fictional: bool = False,
) -> Path:
    """Write only to a caller-selected path, never one suggested by the model."""
    target = Path(path).expanduser().resolve()
    html = render_presentation(summary, plan, fictional=fictional)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")
    return target