from __future__ import annotations

import json
import re

import pytest
from pydantic import ValidationError

from agentic_ai.demo import fictional_report, rehearsal_draft, run_rehearsal
from agentic_ai.presentation import (
    SCORE_WEIGHTS,
    ProposalSummary,
    ScoreEstimate,
    overall_score,
)
from agentic_ai.renderer import render_presentation, save_presentation


def test_overall_inverts_risk_and_preserves_pi_match():
    summary, _ = run_rehearsal()
    assert summary.scores["pi_match"] == 86
    assert summary.overall_score == 82  # 31.15 + 20.25 + 21.50 + 9.30 = 82.20
    assert sum(SCORE_WEIGHTS.values()) == 100
    values = dict.fromkeys(SCORE_WEIGHTS, 100)
    values["competition_risk"] = 0
    assert overall_score(values) == 100
    values["competition_risk"] = 100
    assert overall_score(values) == 85


def test_score_rounds_half_up():
    # 35% of 30 is 10.5, so banker's rounding must not produce 10.
    assert overall_score({
        "grant_fit": 30, "novelty": 0, "pi_match": 0, "competition_risk": 100,
    }) == 11


@pytest.mark.parametrize("value", [-1, 101, 12.5, "80", True])
def test_invalid_numeric_estimates_are_rejected(value):
    payload = rehearsal_draft().grant_fit.model_dump()
    payload["value"] = value
    with pytest.raises(ValidationError):
        ScoreEstimate.model_validate(payload)


def test_scored_estimates_require_evidence():
    with pytest.raises(ValidationError, match="requires analyst evidence"):
        ScoreEstimate(value=80, rationale="Guess", evidence=None)


@pytest.mark.parametrize("metric", ["grant_fit", "novelty", "competition_risk"])
def test_unknown_scores_withhold_overall_and_radar(metric):
    summary, plan = run_rehearsal()
    payload = summary.model_dump()
    payload[metric] = {"value": None, "rationale": "Insufficient evidence", "evidence": None}
    summary = ProposalSummary.model_validate(payload)
    assert summary.overall_score is None
    html = render_presentation(summary, plan)
    assert "Shape withheld" in html
    assert f'id="sim-{metric}"' in html
    assert re.search(rf'id="sim-{metric}"[^>]+disabled', html)


def test_competitor_absence_is_not_zero_risk():
    payload = rehearsal_draft().model_dump()
    report = fictional_report().model_copy(update={"competitors": []})
    with pytest.raises(ValidationError, match="risk must be unknown"):
        ProposalSummary(**payload, analyst_report=report)
    payload["competition_risk"] = {"value": None, "rationale": "No scan", "evidence": None}
    summary = ProposalSummary(**payload, analyst_report=report)
    _, plan = run_rehearsal()
    assert "Competitor evidence is missing" in render_presentation(summary, plan)


def test_summary_round_trip_retains_original_report():
    summary, _ = run_rehearsal()
    recovered = ProposalSummary.model_validate_json(summary.model_dump_json())
    assert recovered == summary
    assert recovered.overall_score == summary.overall_score


def test_renderer_escapes_markup_in_text_attributes_and_raw_json():
    summary, plan = run_rehearsal()
    attack = '</script><img src=x onerror="alert(1)">'
    payload = summary.model_dump()
    payload["title"] = attack
    payload["analyst_report"]["pi"] = attack
    payload["analyst_report"]["competitors"][0]["institution"] = attack
    summary = ProposalSummary.model_validate(payload)
    html = render_presentation(summary, plan)
    assert attack not in html
    assert "&lt;/script&gt;&lt;img" in html
    assert "\\u003c/script\\u003e" in html
    assert html.count("</script>") == 2  # data + trusted bundled JS only
    match = re.search(r'<script id="proposal-data" type="application/json">(.*?)</script>', html)
    data = json.loads(match.group(1))
    assert data["summary"]["title"] == attack
    assert data["overall_score"] == 82
    assert data["weights"] == SCORE_WEIGHTS
    assert "<script src=" not in html
    assert '<link rel="stylesheet"' not in html


def test_render_order_theme_and_all_competitors_are_auditable():
    summary, plan = run_rehearsal()
    plan = plan.model_copy(update={"scenes": list(reversed(plan.scenes)), "theme": "ember"})
    payload = summary.model_dump()
    extra = payload["analyst_report"]["competitors"][0].copy()
    extra["group"] = "Fourth lab, evidence only"
    payload["analyst_report"]["competitors"].append(extra)
    summary = ProposalSummary.model_validate(payload)
    html = render_presentation(summary, plan)
    assert 'data-theme="ember"' in html
    assert html.index('<section id="roadmap"') < html.index('<section id="scorecard"')
    assert "Showing 3 of 4" in html
    assert "Fourth lab, evidence only" in html
    assert "AI-GENERATED · VERIFY CLAIMS" in html
    assert "FICTIONAL REHEARSAL · NOT REAL RESEARCH" not in html


def test_export_is_self_contained_and_caller_selects_path(tmp_path):
    summary, plan = run_rehearsal()
    target = save_presentation(summary, plan, tmp_path / "nested" / "pitch.html", fictional=True)
    html = target.read_text(encoding="utf-8")
    assert target == tmp_path / "nested" / "pitch.html"
    assert "FICTIONAL REHEARSAL · NOT REAL RESEARCH" in html
    assert "@media (prefers-reduced-motion: reduce)" in html
    assert "<noscript>" in html


def test_long_analyst_prose_is_shortened_only_on_cards():
    summary, plan = run_rehearsal()
    payload = summary.model_dump()
    long_text = "This is a lengthy competitor observation. " * 20
    payload["analyst_report"]["competitors"][0]["attack"] = long_text
    html = render_presentation(ProposalSummary.model_validate(payload), plan)
    card = re.search(r'<div class="edge"><b>Our angle</b><p>(.*?)</p>', html).group(1)
    assert len(card) <= 180
    assert card.endswith("…")
    assert long_text in html  # original evidence is not truncated