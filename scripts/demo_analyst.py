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
from agentic_ai.stream import stream_analysis

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
    ctx = './test_data/InfoSheet.pdf'

    report = None
    for event in stream_analysis(ctx, "https://chaneyddtt.github.io/"):
        if event.type == "tool_output":
            # read_context returns a whole document; keep the terminal readable
            text = event.text or ""
            if event.name == "read_context":
                text = text[:1000]
            print(f"\n<tool_output {event.name}>\n{text}\n", flush=True)
        elif event.type == "tool_call":
            print(f"\n<tool_call {event.name}> {event.text}", flush=True)
        elif event.type == "token":
            text = event.text or ""
            print(f"\033[2m{text}\033[0m" if event.reasoning else text, end="", flush=True)
        elif event.type == "report":
            report = event.report
        elif event.type == "error":
            print(f"\n[{event.text}]", flush=True)

    print("\n\n" + "=" * 70 + "\nSTRUCTURED REPORT\n" + "=" * 70)
    if report is None:
        return
    print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
