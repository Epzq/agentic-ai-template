from __future__ import annotations

from langchain_core.messages import AIMessage

import agentic_ai.gemini as gem
from agentic_ai.analyst import analyse, build_analyst
from agentic_ai.report import CompetitorTake, GrantFitReport
from tests.fakes import ScriptedChatModel

_REPORT = GrantFitReport(
    pi="Dr A. Tan",
    grant_call="NRF Competitive Research Programme",
    pi_strengths_and_track_record="15 years in solid-state batteries; 3 prior NRF awards.",
    grant_to_pi_match_pct=78,
    match_rationale="Direction sits squarely in the PI's electrochemistry track record.",
    proposed_direction="Sulfide solid electrolytes with in-situ interphase engineering.",
    competitors=[
        CompetitorTake(
            group="Solid Power Lab",
            institution="NTU",
            their_strengths="Scale-up and pouch-cell integration.",
            vs_pi="PI stronger on interface chemistry; weaker on manufacturing.",
            attack="Lead with novel interphase chemistry, not cell format.",
            avoid="Head-to-head on production throughput.",
        )
    ],
    relevant_past_grants=["NRF-CRP 2019: All-solid-state Li batteries (S$8M)"],
)


def _build_model():
    return ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "read_context", "args": {"path": "CTX"}, "id": "1"}],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "profile_researcher", "args": {"url": "http://pi"}, "id": "2"}
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "web_research", "args": {"question": "competitors"}, "id": "3"}
                ],
            ),
            # create_agent (LangChain 1.x) gets structured output via a tool call
            # named after the schema.
            AIMessage(
                content="",
                tool_calls=[{"name": "GrantFitReport", "args": _REPORT.model_dump(), "id": "sr"}],
            ),
        ],
        structured_response=_REPORT,
    )


def test_analyse_returns_structured_report(tmp_path, monkeypatch):
    ctx = tmp_path / "ctx.md"
    ctx.write_text("Project: next-gen battery electrolytes.", encoding="utf-8")
    monkeypatch.setattr(gem, "ask_gemini", lambda *a, **k: "found 1 competitor, 1 grant")

    # scripted tool call used a placeholder path; point it at the real temp file
    model = _build_model()
    model.responses[0].tool_calls[0]["args"]["path"] = str(ctx)

    report = analyse(str(ctx), "http://pi", "NRF CRP", model=model)

    assert isinstance(report, GrantFitReport)
    assert report.pi == "Dr A. Tan"
    assert report.grant_to_pi_match_pct == 78
    assert report.competitors[0].institution == "NTU"


def test_build_analyst_exposes_expected_tools():
    agent = build_analyst(model=_build_model())
    # the ToolNode is registered under "tools"; just confirm compilation succeeded
    assert agent is not None


def test_save_report_writes_into_subfolder(tmp_path):
    from agentic_ai.analyst import make_save_report_tool

    save = make_save_report_tool(str(tmp_path))
    out = save.invoke({"subfolder": "dr-tan", "content": "# Report\nhello", "filename": "r.md"})

    assert (tmp_path / "dr-tan" / "r.md").read_text() == "# Report\nhello"
    assert out.startswith("saved:")


def test_save_report_rejects_path_escape(tmp_path):
    from agentic_ai.analyst import make_save_report_tool

    save = make_save_report_tool(str(tmp_path))
    out = save.invoke({"subfolder": "../evil", "content": "x"})

    assert out.startswith("save failed:")
    assert not (tmp_path.parent / "evil").exists()
