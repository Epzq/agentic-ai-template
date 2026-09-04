from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.tools import tool

from .config import Settings
from .gemini import ask_gemini

# ---------------------------------------------------------------------------
# Each @tool below becomes a function the model can call. The docstring is the
# description the model sees, and the type hints define the arguments' schema.
# Keep descriptions short and concrete: they are prompt real estate.
# ---------------------------------------------------------------------------


@tool
def add(a: float, b: float) -> float:
    """Add two numbers and return the sum."""
    return a + b


@tool
def multiply(a: float, b: float) -> float:
    """Multiply two numbers and return the product."""
    return a * b


@tool
def now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


@tool
def search_wikipedia(query: str) -> str:
    """Return a short plain-text summary of a topic from English Wikipedia."""
    title = urllib.parse.quote(query.strip().replace(" ", "_"))
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
    req = urllib.request.Request(url, headers={"User-Agent": "agentic-ai-starter/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.load(resp)
    except Exception as exc:  # noqa: BLE001 - hand the error back to the model, don't crash
        return f"lookup failed: {exc}"
    return data.get("extract") or "No summary found."

@tool
def search_awarded_grants(query: str, top_n: int = 5) -> str:
    """Search awarded research grant calls online and return the top matches with a
    one-line abstract and a link each."""
    return ask_gemini(
        f"Search awarded research grants relevant to: {query!r}. "
        f"Prefer Singapore's researchgrant.gov.sg (NRF/A*STAR/MOE/MOH) awarded projects. "
        f"Return the {top_n} most relevant as a numbered list, each with the project "
        f"title, a one-sentence abstract, the funder/scheme, and a URL."
    )


@tool
def find_competitor_labs(direction: str, top_n: int = 5) -> str:
    """Given a research direction, return labs or universities likely working on the
    same problem, with a link to their publication history."""
    return ask_gemini(
        f"For the research direction: {direction!r}, identify the {top_n} labs or "
        f"university groups most likely working on the same problem. Return JSON: a "
        f'list of objects with "group", "institution", "lead_pi", "why_relevant", and '
        f'"publications_url" (Google Scholar / group publications page).'
    )

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


def _safe_path(workdir: str, relpath: str) -> Path:
    """Resolve ``relpath`` inside ``workdir``, refusing anything that escapes it."""
    base = Path(workdir).resolve()
    target = (base / relpath).resolve()
    if target != base and base not in target.parents:
        raise ValueError(f"path escapes workdir: {relpath!r}")
    return target


def default_tools(settings: Settings | None = None) -> list:
    """Build the default toolset.

    Filesystem tools are closed over ``settings.workdir`` so they can only ever
    touch files under that directory.
    """
    settings = settings or Settings()
    workdir = settings.workdir
    Path(workdir).mkdir(parents=True, exist_ok=True)

    @tool
    def read_text_file(path: str) -> str:
        """Read a UTF-8 text file located inside the agent's workdir."""
        return _safe_path(workdir, path).read_text(encoding="utf-8")

    @tool
    def list_files(subdir: str = ".") -> str:
        """List files and folders inside the agent's workdir."""
        base = _safe_path(workdir, subdir)
        return "\n".join(sorted(p.name for p in base.iterdir())) or "(empty)"

    return [
        add,
        multiply,
        now,
        search_wikipedia,
        read_text_file,
        list_files,
        profile_researcher,
        search_awarded_grants,
        find_competitor_labs,
    ]
