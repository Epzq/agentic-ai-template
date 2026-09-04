from __future__ import annotations

from pathlib import Path

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import tool

from .config import Settings
from .documents import load_document
from .gemini import ask_gemini, profile_researcher
from .llm import build_model
from .report import GrantFitReport

# ---------------------------------------------------------------------------
# The "pure agent" version of the grant-fit workflow: a few expressive tools, a
# strong system prompt, and a typed final report. The model decides the order of
# steps, the search queries, and when it has enough - nothing here is a fixed
# pipeline. See README > "Grant-fit analyst" for the pipeline/hybrid alternatives.
# ---------------------------------------------------------------------------

# _SYSTEM = """You are a grant-strategy analyst. Given a project-context document and a
# researcher (the PI), produce a funding-fit report.

# Work through these steps, adapting as needed:
# 1. Call read_context on the document path to understand the project.
# 2. Call profile_researcher on the PI URL for their capabilities and track record.
#    If it errors or comes back thin, use web_research to find a better source
#    (ORCID, Google Scholar, the group page) and try again.
# 3. Propose ONE specific, fundable research direction that fits both the PI's
#    strengths and the project context.
# 4. Use web_research for (a) awarded grants relevant to that direction - prefer
#    researchgrant.gov.sg for Singapore calls - and 
# 5. (b) competing labs working onthe same problem, with links to their publications.
# 6. Before finalising, check that every field of the report is supported by
#    something you actually found. Never fabricate; if the record is thin, say so
#    in that field.

# The report must cover: the PI; the grant call (the one given, or the best-fit one
# you identify); the PI's strengths and track record; an estimated grant-to-PI match
# percentage with a concrete rationale; the proposed direction; competitors (their
# strengths vs the PI's - what to attack, what to avoid); and relevant past grants."""
# You have the tools: read_context(path), profile_researcher(url),
# web_research(question), save_report(subfolder, content).
_SYSTEM = """You are a grant-strategy analyst.
Produce a funding-fit report for a given researcher (the PI) and grant-context document.
The report must cover: PI; fit w grant call; PI strengths and track record; 
a 0-100 grant-to-PI match estimate with rationale; 
a specific proposed direction;
competing labs currently working on the same directions and their publications
(their strengths vs the PI's — what to attack, what to avoid);
and relevant past awarded grants.
Ground every claim; if something can't be found, say so.
When the report is complete, call save_report with a subfolder named after the PI."""


COERCE_PROMPT = (
    "Convert the analysis below into the structured report. Use only what it states; "
    "do not add facts. Every field is required: pi, grant_call, "
    "pi_strengths_and_track_record, grant_to_pi_match_pct (an integer 0-100 - read it "
    "from the text, e.g. '80%' -> 80), match_rationale, proposed_direction, competitors "
    "(each with group, institution, their_strengths, vs_pi, attack, avoid), and "
    "relevant_past_grants.\n\nANALYSIS:\n"
)


def make_save_report_tool(reports_dir: str):
    """A tool that creates a subfolder under ``reports_dir`` and writes a file into it."""

    @tool
    def save_report(subfolder: str, content: str, filename: str = "report.md") -> str:
        """Create <reports_dir>/<subfolder>/ and write `content` to `filename` inside it.
        Call once when the report is complete. Returns the path written, or a line
        starting with 'save failed:'."""
        base = Path(reports_dir).resolve()
        target = (base / subfolder / filename).resolve()
        if not target.is_relative_to(base):
            return f"save failed: {subfolder!r}/{filename!r} escapes {reports_dir}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"saved: {target}"

    return save_report


def build_analyst(
    settings: Settings | None = None, *, model: BaseChatModel | None = None
):
    """Compile the grant-fit analyst agent. ``model`` is injectable for tests."""
    settings = settings or Settings()

    @tool
    def read_context(path: str) -> str:
        """Read the project-context document at a local path (PDF, DOCX, TXT, or MD)."""
        try:
            return load_document(path)
        except Exception as exc:  # noqa: BLE001 - hand the error to the agent
            return f"read failed: {exc}"

    @tool
    def web_research(question: str) -> str:
        """Answer a research question using live web search and page reading. Ask a
        specific, self-contained question; name target sites when relevant
        (e.g. researchgrant.gov.sg for Singapore grants)."""
        return ask_gemini(question)

    save_report = make_save_report_tool(settings.reports_dir)
    return create_agent(
        model or build_model(settings),
        [read_context, web_research, profile_researcher, save_report],
        system_prompt=_SYSTEM,
        response_format=GrantFitReport,
    )


def analyse(
    document: str,
    pi_url: str,
    grant_call: str | None = None,
    *,
    settings: Settings | None = None,
    model: BaseChatModel | None = None,
    recursion_limit: int = 25,
) -> GrantFitReport:
    """Run the analyst end to end and return the structured report."""
    agent = build_analyst(settings, model=model)
    task = (
        f"Context document path: {document}\n"
        f"PI profile URL: {pi_url}\n"
        f"Target grant call: {grant_call or 'not specified - identify the best-fit open call'}\n\n"
        "Produce the grant-fit report."
    )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": task}]},
        {"recursion_limit": recursion_limit},
    )
    report = result.get("structured_response")
    if report is None:
        # Small / local models often fail langgraph's built-in response_format step.
        # Fall back to an explicit coercion of the agent's final message.
        coercer = (model or build_model(settings)).with_structured_output(GrantFitReport)
        report = coercer.invoke(COERCE_PROMPT + str(result["messages"][-1].content))
    return report
