from __future__ import annotations

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.memory import InMemorySaver

from .config import Settings
from .llm import build_model
from .tools import default_tools


def build_agent(
    settings: Settings | None = None,
    *,
    model: BaseChatModel | None = None,
    tools: list | None = None,
    checkpointer=None,
):
    """Create a tool-calling agent: a model that calls tools in a loop until done.

    ``create_agent`` (LangChain 1.x) compiles a small LangGraph state machine::

        START -> model -> has tool calls? --yes--> tools -> model -> ...
                              |
                              no
                              v
                             END

    The ``checkpointer`` is what gives the agent memory: pass a ``thread_id`` in
    the run config and every turn is appended to that thread's message history.

    All arguments are injectable so tests (and your own experiments) can swap in
    a fake model or a custom tool list without touching the rest of the code.
    """
    settings = settings or Settings()
    model = model or build_model(settings)
    tools = default_tools(settings) if tools is None else tools
    checkpointer = checkpointer or InMemorySaver()

    return create_agent(
        model,
        tools,
        system_prompt=settings.system_prompt,
        checkpointer=checkpointer,
    )
