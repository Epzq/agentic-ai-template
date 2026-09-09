from __future__ import annotations

import json

import pytest
from langchain_core.runnables import RunnableLambda
from pydantic import ValidationError

from agentic_ai.demo import fictional_report, rehearsal_draft
from agentic_ai.presentation import ProposalSummary, SummaryDraft
from agentic_ai.summarizer import build_summarizer, summarize
from tests.fakes import ScriptedChatModel


def test_summarizer_accepts_dict_output_and_preserves_analyst(monkeypatch):
    report = fictional_report()
    captured = []

    def structured(self, schema, **kwargs):
        assert schema is SummaryDraft

        def respond(prompt):
            captured.extend(prompt.to_messages())
            return rehearsal_draft().model_dump()

        return RunnableLambda(respond)

    monkeypatch.setattr(ScriptedChatModel, "with_structured_output", structured)
    result = build_summarizer(model=ScriptedChatModel(responses=[])).invoke(report)
    assert isinstance(result, ProposalSummary)
    assert result.analyst_report == report
    assert result.analyst_report is not report
    assert json.loads(captured[1].content) == report.model_dump()
    assert "untrusted DATA" in captured[0].content
    report.grant_to_pi_match_pct = 1
    assert result.scores["pi_match"] == 86  # independent deep copy


def test_summarizer_rejects_fabricated_quote():
    draft = rehearsal_draft().model_dump()
    draft["grant_fit"]["evidence"]["quote"] = "A claim the analyst never made"
    model = ScriptedChatModel(responses=[], structured_response=draft)
    with pytest.raises(ValidationError, match="quote not found"):
        summarize(fictional_report(), model=model)


@pytest.mark.parametrize("field", ["pi", "overall_score", "pi_match"])
def test_summarizer_cannot_override_code_owned_fields(field):
    draft = rehearsal_draft().model_dump()
    draft[field] = 100
    with pytest.raises(ValidationError, match="Extra inputs"):
        summarize(
            fictional_report(), model=ScriptedChatModel(responses=[], structured_response=draft)
        )


def test_summary_rejects_long_copy_and_excessive_milestones():
    draft = rehearsal_draft().model_dump()
    draft["title"] = "x" * 71
    draft["milestones"].append(draft["milestones"][0])
    with pytest.raises(ValidationError) as error:
        SummaryDraft.model_validate(draft)
    assert len(error.value.errors()) == 2


def test_summarizer_does_not_silently_replace_provider_failure(monkeypatch):
    def structured(self, schema, **kwargs):
        def fail(_):
            raise RuntimeError("Model unavailable")
        return RunnableLambda(fail)

    monkeypatch.setattr(ScriptedChatModel, "with_structured_output", structured)
    with pytest.raises(RuntimeError, match="Model unavailable"):
        summarize(fictional_report(), model=ScriptedChatModel(responses=[]))