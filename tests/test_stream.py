from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

import agentic_ai.gemini as gem
from agentic_ai.analyst import COERCE_PROMPT
from agentic_ai.report import GrantFitReport
from agentic_ai.stream import AnalysisEvent, stream_analysis
from tests.fakes import ScriptedChatModel
from tests.test_analyst import _REPORT


class _CoercingChatModel(ScriptedChatModel):
    """A model whose ``response_format`` step comes back empty (``structured_response``
    is None) but which answers the explicit COERCE_PROMPT call - the fallback path
    small / local models put ``stream_analysis`` through."""

    coerced: Any = None

    def with_structured_output(self, schema, **kwargs):  # noqa: ANN001
        def run(payload: Any) -> Any:
            if isinstance(payload, str) and payload.startswith(COERCE_PROMPT):
                if isinstance(self.coerced, Exception):
                    raise self.coerced
                return self.coerced
            return None

        return RunnableLambda(run)


@pytest.fixture
def context_doc(tmp_path):
    doc = tmp_path / "ctx.md"
    doc.write_text("Project: next-gen battery electrolytes.", encoding="utf-8")
    return doc


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    monkeypatch.setattr(gem, "ask_gemini", lambda *a, **k: "canned research")


def _responses(path: str) -> list[AIMessage]:
    """One tool call, then a final answer."""
    return [
        AIMessage(
            content="",
            tool_calls=[{"name": "read_context", "args": {"path": path}, "id": "1"}],
        ),
        AIMessage(content="Estimated match: 78%."),
    ]


def test_event_sequence_is_tool_call_output_token_report(context_doc):
    model = ScriptedChatModel(responses=_responses(str(context_doc)), structured_response=_REPORT)

    events = list(stream_analysis(str(context_doc), "http://pi", "NRF CRP", model=model))

    assert [e.type for e in events] == ["tool_call", "tool_output", "token", "report"]
    call, output, token, report = events
    assert call.name == "read_context"
    assert str(context_doc) in (call.text or "")
    assert output.name == "read_context"
    assert "battery electrolytes" in (output.text or "")
    assert token.text == "Estimated match: 78%."
    assert token.reasoning is False
    assert isinstance(report.report, GrantFitReport)
    assert report.report.grant_to_pi_match_pct == 78


def test_events_are_json_serialisable(context_doc):
    model = ScriptedChatModel(responses=_responses(str(context_doc)), structured_response=_REPORT)

    for event in stream_analysis(str(context_doc), "http://pi", model=model):
        payload = event.model_dump_json()
        assert AnalysisEvent.model_validate_json(payload).type == event.type


def test_missing_structured_response_falls_back_to_coercion(context_doc):
    model = _CoercingChatModel(
        responses=_responses(str(context_doc)), structured_response=None, coerced=_REPORT
    )

    events = list(stream_analysis(str(context_doc), "http://pi", model=model))

    assert [e.type for e in events] == ["tool_call", "tool_output", "token", "report"]
    assert events[-1].report == _REPORT


def test_failed_coercion_yields_error_event_not_a_raise(context_doc):
    model = _CoercingChatModel(
        responses=_responses(str(context_doc)),
        structured_response=None,
        coerced=RuntimeError("no json"),
    )

    events = list(stream_analysis(str(context_doc), "http://pi", model=model))

    assert events[-1].type == "error"
    assert "no json" in (events[-1].text or "")


def test_agent_failure_yields_error_event_not_a_raise(context_doc):
    # only one scripted response, so the loop runs out of messages mid-run
    model = ScriptedChatModel(
        responses=_responses(str(context_doc))[:1], structured_response=_REPORT
    )

    events = list(stream_analysis(str(context_doc), "http://pi", model=model))

    assert events[-1].type == "error"
    assert events[-1].text and events[-1].text.startswith("analysis failed:")


def test_reasoning_tokens_are_marked(context_doc):
    thinking = AIMessage(
        content=[
            {"type": "thinking", "thinking": "weighing the fit"},
            {"type": "text", "text": "78%"},
        ]
    )
    model = ScriptedChatModel(
        responses=[_responses(str(context_doc))[0], thinking], structured_response=_REPORT
    )

    events = list(stream_analysis(str(context_doc), "http://pi", model=model))
    tokens = [e for e in events if e.type == "token"]

    assert [(e.text, e.reasoning) for e in tokens] == [("weighing the fit", True), ("78%", False)]
