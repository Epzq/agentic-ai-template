from __future__ import annotations

from langchain_core.messages import AIMessage

from agentic_ai.agent import build_agent
from agentic_ai.tools import default_tools
from tests.fakes import ScriptedChatModel


def test_agent_runs_a_tool_then_answers(settings):
    """The model asks for `add(2, 3)`, the loop runs it, the model then answers."""
    scripted = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "add", "args": {"a": 2, "b": 3}, "id": "call_1"}],
            ),
            AIMessage(content="The sum is 5."),
        ]
    )
    agent = build_agent(settings, model=scripted, tools=default_tools(settings))

    result = agent.invoke(
        {"messages": [{"role": "user", "content": "add 2 and 3"}]},
        {"configurable": {"thread_id": "t1"}},
    )

    assert "5" in result["messages"][-1].content


def test_agent_answers_without_tools(settings):
    scripted = ScriptedChatModel(responses=[AIMessage(content="Hello!")])
    agent = build_agent(settings, model=scripted, tools=default_tools(settings))

    result = agent.invoke(
        {"messages": [{"role": "user", "content": "hi"}]},
        {"configurable": {"thread_id": "t2"}},
    )

    assert result["messages"][-1].content == "Hello!"
