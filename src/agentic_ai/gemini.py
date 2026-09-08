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


@tool
def profile_researcher(url: str) -> str:
    """Given a URL to a researcher (faculty bio, ORCID, Google Scholar, lab site),
    research them online and return a short profile of their capabilities: research
    directions, methods, notable publications, and grants/projects.

    Returns the profile text, or a line starting with 'gemini error:'.
    """
    return ask_gemini(
        f"Research the person associated with this page: {url}\n\n"
        "Read that page and closely related sources (their publication list, ORCID, "
        "Google Scholar, lab/group site, recent grant announcements). Then write about "
        "six sentences covering: their main research directions and application domains; "
        "key methods, techniques and platforms they use; a few representative "
        "publications with years; and grants, awards or funded projects (funder and "
        "their role if stated). Ground every claim in what you find; if the public "
        "record is thin, say so. Finish with one sentence on the kinds of grant calls "
        "they would be a strong fit for."
    )