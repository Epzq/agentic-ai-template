# Proposal Studio: the 90-second demo

## What will impress the judges?

Lead with **a decision and a story**, not a wall of generated research:

1. **An idea with a visual hook.** The opening frame pairs a memorable project
   title with an overall opportunity ring and a short audience question.
2. **Four signals, not a mysterious magic score.** Grant Fit, Novelty, PI Match,
   and Competition Risk have score bars, rationales, and expandable evidence.
   A radar chart shows the trade-offs; risk is inverted on the radar only.
3. **Audience participation.** Ask “What if the competition were much stronger?”
   and move the risk slider. The *hypothetical* overall changes immediately;
   the underlying assessment does not. No API call or fake new research.
4. **A strategy, not a competitor name dump.** Three competitor cards show
   their strength, the PI's angle, and where to avoid a head-on contest.
5. **A proposed proof plan.** Close on three milestones and a 30-second pitch,
   rather than a purportedly complete professional grant proposal.
6. **Visible agent collaboration.** Show the Analyst → Summarizer → UI pipeline,
   then open a supporting quote to show that the polished UI retains an audit trail.

Further ideas for the team: have the audience vote on which assumption to test
first, narrate one competitor as a potential collaborator, or compare two separately
generated pitches side by side. These are presentation suggestions, not implemented
automatic comparisons or new research capabilities.

## Codebase analysis and design

The existing [analyst](../src/agentic_ai/analyst.py) decides how to read a local
context document, profile a PI, and research competitors and awards. Its
[GrantFitReport](../src/agentic_ai/report.py) contains long narrative fields,
competitor comparisons, and **only one numeric score**, `grant_to_pi_match_pct`.
The old terminal demo is oriented toward raw model/tool output, not a stage pitch.
The old analyst and its public API are unchanged.

New modules form independently usable boundaries:

| Component | Input → output | Responsibility |
|---|---|---|
| [Summarizer](../src/agentic_ai/summarizer.py) | `GrantFitReport` → `ProposalSummary` | Short story, evidence-linked strengths, three new heuristic estimates, proposed milestones, caveats |
| [UI agent](../src/agentic_ai/ui_agent.py) | `ProposalSummary` → `PresentationPlan` | Choose theme, highlighted metric, scene order, speaker cues |
| [Contracts](../src/agentic_ai/presentation.py) | Pydantic schemas | Limits, original-quote checks, enum-only layout decisions, deterministic score rubric |
| [Renderer](../src/agentic_ai/renderer.py) | Summary + plan → standalone HTML | Safe escaping, visual scorecard, local simulator, presenter controls, JSON export |
| [Rehearsal](../src/agentic_ai/demo.py) | Prepared fictional fixtures → same contracts | Exercise both agents without APIs, network, or test-package imports |

The two new “agents” are deliberately **single structured model calls**, not
unnecessary autonomous tool loops. There is no new research in these stages.
`build_summarizer()` and `build_ui_agent()` return composable LangChain runnables;
`summarize()` and `design_presentation()` are convenient direct entry points.
Each accepts an independently injectable `model` and `settings`, so the two
stages can use different providers or be tested separately.

```python
from agentic_ai.summarizer import summarize
from agentic_ai.ui_agent import design_presentation
from agentic_ai.renderer import save_presentation

# report is the existing analyse(...) result; no changes to the analyst required.
summary = summarize(report)
plan = design_presentation(summary)
save_presentation(summary, plan, "reports/pitch.html")
```

## Run a reliable rehearsal

Install the project using the repository's normal setup. Then:

```bash
python scripts/demo_proposal.py --offline --open
```

Omitting `--offline` also selects rehearsal mode. This mode replays an **invented
PI, call, labs, award, and prepared agent outputs** through the two real agent
boundaries. It does not claim to perform live generation. The page has a prominent
fictional-rehearsal badge. It needs neither API credentials nor a model download.

By default the output directory is `reports/proposal-demo`. It contains a standalone
HTML page, the original analyst report JSON, the summary JSON, and the presentation
plan JSON. Choose another directory with `--output`. The HTML is fully offline:
no server, CDN, fonts, analytics, or external assets are required. Keep this saved
page ready as the event fallback. `--open` may not launch a local browser over SSH;
open the generated file with VS Code's browser/preview or download it instead.

## Input form for the team

```bash
pip install -e ".[showcase,docs,gemini]"
streamlit run scripts/proposal_app.py
```

The form accepts a **grant call name, PI webpage, and pasted grant context or an
uploaded TXT/MD/PDF/DOCX**. Start with rehearsal enabled; disable it for real
inputs. Live mode uses `AGENT_MODEL` and its provider credentials for all three
agents; Gemini web research needs `GOOGLE_API_KEY`. The provider must support
structured output. Rehearsal disables real inputs rather than pretending to use them.

The form shows stage-level progress, embeds the dashboard, exposes typed handoffs,
and downloads the standalone HTML. Uploaded context is processed in a temporary
directory that is removed after analysis. The generated output remains in the
current Streamlit session. Live mode sends content to configured providers; use
public, non-sensitive material. This is a local hackathon UI, not a hardened
multi-user service: do not expose it publicly without authentication, resource
limits, and a deployment/security review.

## Live CLI or cached analyst input

```bash
python scripts/demo_proposal.py --live \
  --document /path/to/grant-call.pdf \
  --pi-url https://example.edu/researcher \
  --grant-call "Your target call" --output reports/live-pitch --open

python scripts/demo_proposal.py --report /path/to/analyst-report.json \
  --output reports/cached-pitch --open
```

`--report` expects a `GrantFitReport` JSON object, not Markdown or a summary. It
skips analyst research but **still calls the two new models**. It is useful for
fast iteration on a real report. Neither live mode silently falls back to fictional
content. Invalid schemas, unsupported structured output, or missing evidence
quotes cause a visible failure; use rehearsal deliberately when needed.

## Score semantics and honesty

- **PI Match** is copied directly from `grant_to_pi_match_pct`. It is an analyst
  estimate, not an independently established fact.
- **Grant Fit** estimates alignment of the proposed direction with the call.
- **Novelty** estimates differentiation *within the supplied report only*, not
  verified scientific novelty from a comprehensive literature search.
- **Competition Risk** estimates competitive pressure. **Higher is worse.**
  No competitors in the report means unknown risk, not zero risk.
- **Overall** is calculated in code: 35% Grant Fit + 25% Novelty + 25% PI Match
  + 15% (100 − Competition Risk), rounded to the nearest integer (half up).
  If any component is unknown, overall is withheld rather than treating missing
  evidence as zero or quietly redistributing weights.

The same weights are passed to the browser simulator. Its slider changes never
alter the baseline, the summary, or exported scores. The original report is kept
inside `ProposalSummary` for inspection; `summary.scores` and
`summary.overall_score` are derived Python properties, not model-writable fields.
The browser's JSON export includes those derived values as well as the handoffs.
Long original analyst passages are shortened on cards only; full text is retained
in the evidence drawer and exports.

Every numeric summarizer estimate and extracted PI strength references an exact
quote in a known analyst field. Validation proves the quote exists, **not that it
supports the interpretation or that the analyst is correct**. Narrative claims,
speaker notes, eligibility, budgets, and novelty still need human review. Prompts
require missing information to be preserved. Proposed milestones are visibly
labelled as hypotheses/future work, never completed results.

## A suggested stage script

| Time | Action | Message |
|---|---|---|
| 0–15s | Open the hero + scorecard | “We turn a grant call and a PI into a decision-ready story, not 40 pages.” |
| 15–35s | Explain risk direction; move the risk slider | “What if the competitive landscape changes? These are transparent assumptions, not funding odds.” |
| 35–55s | Switch to strategy; reveal one evidence quote | “Here is our angle—and here is the analyst text behind it.” |
| 55–75s | Show the proof plan | “Three experiments to test the idea. We don't pretend the proposal is already validated.” |
| 75–90s | Show speaker cues or handoff JSON | “Separate agents research, edit, and design. Code protects the scores and presentation boundary.” |

Use **Present** for one scene at a time, left/right arrows to navigate, **Speaker
cues** for notes, and Escape to exit. The dashboard also supports printing to PDF,
keyboard focus, reduced-motion preferences, responsive layout, and a no-JavaScript
read-only view. For large projected text, use browser zoom as needed.

## Safety and tests

The UI agent never emits HTML/CSS/JavaScript: it selects a validated theme, metric,
and scene order. Model text is escaped; embedded JSON escapes HTML raw-text
delimiters. Only trusted bundled JavaScript runs, with no external requests.
Paths are selected by the caller, not by the models. This separation is both a
modularity feature and a protection against rendering untrusted research as code.

```bash
pytest tests/test_presentation.py tests/test_summarizer.py tests/test_ui_agent.py tests/test_demo_proposal.py
```

Tests cover the typed boundaries, evidence rejection, missing scores, risk
inversion, script injection, round-trip JSON, offline generation, and live-mode
wiring with injected fakes. Live provider output quality remains non-deterministic;
rehearse a cached artifact before presenting.

Optional form tests run when Streamlit is installed. Optional browser tests run
when Playwright and Chromium are installed; neither is required for the core test
suite or for opening the generated HTML:

```bash
pip install playwright
python -m playwright install chromium
pytest tests/test_presentation_browser.py tests/test_proposal_app.py
```