from __future__ import annotations

import json

import pytest
from langchain_core.runnables import RunnableLambda
from pydantic import ValidationError

from agentic_ai.demo import run_rehearsal
from agentic_ai.presentation import PresentationPlan
from agentic_ai.ui_agent import build_ui_agent, design_presentation
from tests.fakes import ScriptedChatModel


def test_ui_agent_uses_summary_not_full_report(monkeypatch):
    summary, plan = run_rehearsal()
    captured = []

    def structured(self, schema, **kwargs):
        assert schema is PresentationPlan

        def respond(prompt):
            captured.extend(prompt.to_messages())
            return plan.model_dump()

        return RunnableLambda(respond)

    monkeypatch.setattr(ScriptedChatModel, "with_structured_output", structured)
    result = build_ui_agent(model=ScriptedChatModel(responses=[])).invoke(summary)
    payload = json.loads(captured[1].content)
    assert "analyst_report" not in payload
    assert payload["scores"] == summary.scores
    assert payload["overall_score"] == 82
    assert "Never output HTML" in captured[0].content
    assert result == plan


@pytest.mark.parametrize("change", [
    {"theme": '<script>alert("x")</script>'},
    {"spotlight": "made_up_score"},
    {"overall_score": 100},
])
def test_ui_agent_rejects_unsafe_or_unknown_design_fields(change):
    summary, plan = run_rehearsal()
    payload = plan.model_dump() | change
    with pytest.raises(ValidationError):
        design_presentation(
            summary, model=ScriptedChatModel(responses=[], structured_response=payload)
        )


def test_ui_agent_requires_each_scene_once():
    _, plan = run_rehearsal()
    payload = plan.model_dump()
    payload["scenes"][2]["section"] = "scorecard"
    with pytest.raises(ValidationError, match="exactly once"):
        PresentationPlan.model_validate(payload)