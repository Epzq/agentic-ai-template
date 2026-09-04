from __future__ import annotations

import os

from langchain_core.tools import tool

# ---------------------------------------------------------------------------
# A single-shot call to Gemini with Google Search + URL-context grounding.
# The model does the browsing/searching and returns prose - no manual fetching
# or HTML parsing here. Build tools by wrapping ask_gemini() with a prompt.
#
# Requires:  uv pip install -e ".[gemini]"   and   GOOGLE_API_KEY=...
# Model:     AGENT_RESEARCHER_MODEL  (default gemini-2.5-flash)
# ---------------------------------------------------------------------------

_DEFAULT_MODEL = os.environ.get("AGENT_RESEARCHER_MODEL", "gemini-2.5-flash")


def ask_gemini(prompt: str, *, model: str | None = None, search: bool = True) -> str:
    """Ask Gemini one question, with web search + URL-context grounding enabled.

    Returns the response text, or a string starting with ``"gemini error:"`` on any
    failure (missing key, missing package, API error) so callers can hand it
    straight back to the orchestrator instead of raising.
    """
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "gemini error: set GOOGLE_API_KEY (or GEMINI_API_KEY) to use this tool."
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return 'gemini error: run  uv pip install -e ".[gemini]"'

    grounding: list = (
        [types.Tool(url_context=types.UrlContext()), types.Tool(google_search=types.GoogleSearch())]
        if search
        else []
    )
    try:
        client = genai.Client(api_key=api_key)  # keep a reference: an inline client
        resp = client.models.generate_content(  # gets GC'd and closes mid-call
            model=model or _DEFAULT_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(tools=grounding, temperature=0.0),
        )
    except Exception as exc:  # noqa: BLE001 - surface to the model, don't crash the loop
        return f"gemini error: {exc}"
    return (resp.text or "").strip() or "gemini error: empty response."


