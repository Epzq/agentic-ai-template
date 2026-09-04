"""Run the grant-fit analyst with a FAKE ask_gemini but the REAL orchestrator model.

No Gemini key needed. Uses whatever AGENT_MODEL points at:

    AGENT_MODEL=ollama:qwen2.5 uv run python scripts/demo_analyst.py     # fully local
    ANTHROPIC_API_KEY=... uv run python scripts/demo_analyst.py          # default (claude-opus-5)

Streams the model's raw output token-by-token. Tool activity is inlined as:

    ...model text...
    <tool_call NAME> {json args}
    <tool_output NAME> ...result...
    ...model text...

Then prints the final structured GrantFitReport.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import agentic_ai.analyst as analyst
import agentic_ai.gemini as gemini

# --- canned "research" the orchestrator gets instead of live web calls ---

_PI_PROFILE = """\
Dr. A. Tan, Associate Professor, Dept. of Materials Science, NUS.
Research directions: solid-state lithium batteries; sulfide and halide solid
electrolytes; electrode-electrolyte interphase characterisation (cryo-EM, XPS).
Methods: in-situ synchrotron XRD, impedance spectroscopy, DFT interface modelling.
Publications: "Halide electrolytes with 10 mS/cm conductivity" (Nature Energy, 2023);
"Interphase failure modes in sulfide ASSBs" (JACS, 2022); ~70 papers, h-index 34.
Grants: NRF Investigatorship 2021 (S$3M); MOE Tier 2 2019; A*STAR IAF-PP co-PI 2020.
"""

_GRANTS = """\
1. NRF-CRP 2019 - "All-solid-state Li batteries for grid storage", S$8M, NTU-led.
   https://www.researchgrant.gov.sg/example/crp2019-assb
2. RIE2025 Materials - "Scalable sulfide electrolyte synthesis", S$5M, A*STAR IMRE.
   https://www.researchgrant.gov.sg/example/rie2025-sulfide
3. NRF Investigatorship 2021 - Dr Tan, "Interphase engineering in ASSBs", S$3M.
"""

_COMPETITORS = """\
[
  {"group": "Solid Power Lab", "institution": "NTU",
   "strengths": "pouch-cell integration, dry-room scale-up, industry ties (BMW)",
   "publications_url": "https://scholar.google.com/citations?user=example1"},
  {"group": "Cui Group", "institution": "Stanford",
   "strengths": "nanostructured Li anodes, cryo-EM of SEI, very high citation impact",
   "publications_url": "https://scholar.google.com/citations?user=example2"},
  {"group": "IMRE Solid Electrolytes", "institution": "A*STAR",
   "strengths": "halide synthesis at kg scale, process engineering",
   "publications_url": "https://www.a-star.edu.sg/imre/example"}
]
"""


def fake_ask_gemini(prompt: str, **_kwargs) -> str:
    p = prompt.lower()
    if "person associated with" in p or ("profile" in p and "researcher" in p):
        return _PI_PROFILE
    if any(k in p for k in ("competitor", "competing lab", "working on the same problem")):
        return _COMPETITORS
    return _GRANTS


def main() -> None:
    # patch both references: gemini.py's (used by profile_researcher) and
    # analyst.py's (used by the web_research tool)
    #gemini.ask_gemini = fake_ask_gemini
    #analyst.ask_gemini = fake_ask_gemini

    # ctx = Path(tempfile.mkdtemp()) / "project-context.md"
    # ctx.write_text(
    #     "# Project context\n\n"
    #     "We want to propose a project on next-generation solid-state battery "
    #     "electrolytes with improved room-temperature ionic conductivity and stable "
    #     "electrode interphases, targeting grid-scale storage. Budget ~S$4M, 4 years.",
    #     encoding="utf-8",
    # )
    ctx='./test_data/InfoSheet.pdf'
    agent = analyst.build_analyst()
    task = (
        f"Context document path: {ctx}\n"
        "PI profile URL: https://chaneyddtt.github.io/\n"
        #"Target grant call: not specified - identify the best-fit open call\n\n"
        "Produce the grant-fit report."
    )
    inp = {"messages": [{"role": "user", "content": task}]}
    cfg = {"recursion_limit": 25}

    # One stream. "values" only to keep the final state for the report below;
    # everything shown comes from "messages" - the raw per-token model output.
    final = None
    for mode, chunk in agent.stream(inp, cfg, stream_mode=["values", "messages"]):
        if mode == "values":
            final = chunk
            continue

        msg, _meta = chunk
        if type(msg).__name__ == "ToolMessage":
            #print(f"\n<tool_output {msg.name}>\n{msg.content}\n", flush=True)
            if msg.name == 'read_context':
                print(f"\n<tool_output {msg.name}>\n{msg.content[:1000]}\n", flush=True)
            else:
                print(f"\n<tool_output {msg.name}>\n{msg.content}\n", flush=True)
            continue

        # reasoning models that separate their thinking (Claude thinking blocks,
        # ollama `reasoning`). deepseek-r1 style <think>...</think> just rides in content.
        rc = msg.additional_kwargs.get("reasoning_content")
        if rc:
            print(f"\033[2m{rc}\033[0m", end="", flush=True)  # dim
        if isinstance(msg.content, list):
            for part in msg.content:
                if isinstance(part, dict) and part.get("type") in ("thinking", "reasoning"):
                    t = part.get("thinking") or part.get("reasoning") or ""
                    print(f"\033[2m{t}\033[0m", end="", flush=True)
                elif isinstance(part, dict) and part.get("type") == "text":
                    print(part["text"], end="", flush=True)
        elif msg.content:
            print(msg.content, end="", flush=True)

        for tc in getattr(msg, "tool_call_chunks", None) or []:
            print(f"\n<tool_call {tc['name']}> {tc['args']}", flush=True)

    print("\n\n" + "=" * 70 + "\nSTRUCTURED REPORT\n" + "=" * 70)
    report = final.get("structured_response") if final else None
    if report is None:
        from agentic_ai.analyst import COERCE_PROMPT
        from agentic_ai.llm import build_model
        from agentic_ai.report import GrantFitReport

        coercer = build_model().with_structured_output(GrantFitReport)
        try:
            report = coercer.invoke(COERCE_PROMPT + str(final["messages"][-1].content))
        except Exception as exc:  # noqa: BLE001
            print(f"[structured coercion failed: {exc}]")
            return
    print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    main()