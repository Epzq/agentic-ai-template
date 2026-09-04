from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda


class ScriptedChatModel(BaseChatModel):
    """A chat model that replays a fixed list of ``AIMessage``s, one per call.

    Enough to drive the whole agent loop in tests with no network access. Encode
    tool calls directly in the scripted messages via ``AIMessage(tool_calls=...)``.
    Set ``structured_response`` to the object that ``with_structured_output`` should
    return (used by agents compiled with ``response_format=``).
    """

    responses: list
    structured_response: Any = None

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001 - tools are ignored on purpose
        return self

    def with_structured_output(self, schema, **kwargs):  # noqa: ANN001
        value = self.structured_response
        return RunnableLambda(lambda _input: value)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        message = self.responses.pop(0)
        return ChatResult(generations=[ChatGeneration(message=message)])
