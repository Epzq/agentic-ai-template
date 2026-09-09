from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

from .analyst import COERCE_PROMPT, build_analyst
from .config import Settings
from .llm import build_model
from .report import GrantFitReport

# ---------------------------------------------------------------------------
# One streaming loop over the analyst, shared by scripts/demo_analyst.py and the
# web layer. `analyse()` in analyst.py stays the simple blocking path; this is the
# same run with every intermediate step surfaced as a JSON-serialisable event.
# ---------------------------------------------------------------------------

EventType = Literal["token", "tool_call", "tool_output", "report", "error"]


class AnalysisEvent(BaseModel):
    """One step of a streamed analysis. JSON-serialisable: SSE sends it verbatim.

    - ``token``: a piece of model output. ``reasoning`` marks a thinking block.
    - ``tool_call`` / ``tool_output``: ``name`` is the tool, ``text`` the JSON args
      or the tool's return value (never truncated here - callers decide).
    - ``report``: the final ``GrantFitReport``.
    - ``error``: the run could not produce a report; ``text`` says why.
    """

    type: EventType
    name: str | None = None
    text: str | None = None
    report: GrantFitReport | None = None
    reasoning: bool = False


def _tool_call_events(msg: Any) -> Iterator[AnalysisEvent]:
    """Tool calls as the model emits them: partial arg chunks when it streams,
    the assembled call when it doesn't (a non-streaming model, e.g. in tests)."""
    chunks = getattr(msg, "tool_call_chunks", None) or []
    if chunks:
        for chunk in chunks:
            yield AnalysisEvent(
                type="tool_call", name=chunk.get("name"), text=chunk.get("args") or ""
            )
        return
    for call in getattr(msg, "tool_calls", None) or []:
        yield AnalysisEvent(
            type="tool_call", name=call.get("name"), text=json.dumps(call.get("args") or {})
        )


def _message_events(msg: Any) -> Iterator[AnalysisEvent]:
    """Translate one streamed message into events."""
    if type(msg).__name__ == "ToolMessage":
        yield AnalysisEvent(type="tool_output", name=msg.name, text=str(msg.content))
        return

    # Reasoning models that separate their thinking (Claude thinking blocks, ollama
    # `reasoning`). deepseek-r1 style <think>...</think> just rides in content.
    reasoning = msg.additional_kwargs.get("reasoning_content")
    if reasoning:
        yield AnalysisEvent(type="token", text=reasoning, reasoning=True)
    if isinstance(msg.content, list):
        for part in msg.content:
            if not isinstance(part, dict):
                continue
            if part.get("type") in ("thinking", "reasoning"):
                text = part.get("thinking") or part.get("reasoning") or ""
                yield AnalysisEvent(type="token", text=text, reasoning=True)
            elif part.get("type") == "text":
                yield AnalysisEvent(type="token", text=part["text"])
    elif msg.content:
        yield AnalysisEvent(type="token", text=msg.content)

    yield from _tool_call_events(msg)


def _report_event(
    final: dict | None, settings: Settings | None, model: BaseChatModel | None
) -> AnalysisEvent:
    """The final report, coercing the last message when langgraph's own
    structured-output step came back empty (small / local models often fail it)."""
    report = final.get("structured_response") if final else None
    if report is None:
        if not final or not final.get("messages"):
            return AnalysisEvent(type="error", text="analysis produced no report")
        try:
            coercer = (model or build_model(settings)).with_structured_output(GrantFitReport)
            report = coercer.invoke(COERCE_PROMPT + str(final["messages"][-1].content))
        except Exception as exc:  # noqa: BLE001 - an error event, never a raise
            return AnalysisEvent(type="error", text=f"structured coercion failed: {exc}")
    if not isinstance(report, GrantFitReport):
        return AnalysisEvent(type="error", text=f"unexpected report type: {type(report).__name__}")
    return AnalysisEvent(type="report", report=report)


def stream_analysis(
    document: str,
    pi_url: str,
    grant_call: str | None = None,
    *,
    settings: Settings | None = None,
    model: BaseChatModel | None = None,
    recursion_limit: int = 25,
) -> Iterator[AnalysisEvent]:
    """Run the analyst, yielding every step as an ``AnalysisEvent``.

    Never raises: a failure anywhere becomes a final ``error`` event, so a caller
    streaming to a browser always sees why a run stopped.
    """
    task = (
        f"Context document path: {document}\n"
        f"PI profile URL: {pi_url}\n"
        f"Target grant call: {grant_call or 'not specified - identify the best-fit open call'}\n\n"
        "Produce the grant-fit report."
    )

    final: dict | None = None
    try:
        agent = build_analyst(settings, model=model)
        # One stream. "values" only to keep the final state (for the report);
        # everything shown comes from "messages" - the raw per-token model output.
        for mode, chunk in agent.stream(
            {"messages": [{"role": "user", "content": task}]},
            {"recursion_limit": recursion_limit},
            stream_mode=["values", "messages"],
        ):
            if mode == "values":
                final = chunk
                continue
            yield from _message_events(chunk[0])
    except Exception as exc:  # noqa: BLE001 - the caller sees the failure, not a traceback
        yield AnalysisEvent(type="error", text=f"analysis failed: {exc}")
        return

    yield _report_event(final, settings, model)
