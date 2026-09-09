# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

The repo ships with `uv` + `make` (see README/CONTRIBUTING), but **this checkout is actually run
from a conda env named `agentic-ai`** (Python 3.11, see `HOW-TO-USE.md`):

```bash
conda activate agentic-ai
pip install -e ".[gemini,docs]" "langchain[google-genai]"
```

```bash
make lint          # ruff check src tests + mypy src
make fmt           # ruff --fix + ruff format
make test          # pytest (coverage on agentic_ai, `-m 'not network'` by default)
pytest tests/test_agent.py::test_name   # single test
pytest -m network                       # opt into the real-network tests
agentic-ai                              # REPL
agentic-ai analyse <doc> <pi_url> [--call NAME] [--json]   # grant-fit analyst
python scripts/demo_analyst.py          # streamed token/tool-call view of the analyst
```

Tests need no API key — they inject `ScriptedChatModel` from `tests/fakes.py`.

## Configuration

All runtime knobs come from `Settings` (`config.py`), a `pydantic-settings` model reading
`AGENT_`-prefixed env vars from `.env`. Note that `.env` here overrides the code default of
`claude-opus-5`: the orchestrator is `google_genai:gemini-2.5-flash`, keyed by `GOOGLE_API_KEY`.
`AGENT_RESEARCHER_MODEL` is read separately, at import time, by `gemini.py` (not via `Settings`).

## Architecture

Two agents share one substrate. Both are LangChain 1.x `create_agent` (a LangGraph
model→tools→model loop), not hand-written pipelines.

- **Substrate:** `config.py` (Settings) → `llm.py` (`build_model` via provider-agnostic
  `init_chat_model`) → `tools.py` (`default_tools(settings)`) → `agent.py` (`build_agent`,
  with an `InMemorySaver` checkpointer keyed on `thread_id` for multi-turn memory).
  Every dependency of `build_agent`/`build_analyst` is injectable so tests pass fakes.
- **General agent:** `cli.py` REPL, one `thread_id` for the process lifetime.
- **Grant-fit analyst:** `analyst.py` — tools `read_context` / `web_research` /
  `profile_researcher` / `save_report`, the `_SYSTEM` prompt, and
  `response_format=GrantFitReport` (`report.py`). `analyse()` falls back to an explicit
  `with_structured_output` coercion (`COERCE_PROMPT`) when `structured_response` is missing,
  which small/local models often trigger. `documents.py` turns PDF/DOCX/TXT/MD into text.

**Two model providers by design.** The orchestrator goes through LangChain
(`build_model`). Anything needing live web access goes through `gemini.py`'s `ask_gemini`,
which calls the `google-genai` SDK directly with Google Search + URL-context grounding — no
`langchain-core` dependency, so no version clash. `ask_gemini` is the single place the
research provider is named.

## Conventions

- Tools **return error strings, never raise** (`"lookup failed: ..."`, `"gemini error: ..."`,
  `"read failed: ..."`) so the agent reads the failure and recovers instead of crashing the loop.
- Filesystem tools are confined to `settings.workdir` by `_safe_path()` in `tools.py`; they are
  built inside `default_tools()` so they can close over the workdir.
- New tools: add to `tools.py` with a one-line docstring (the model reads it) *and* to the list
  in `default_tools`, plus a unit test in `tests/test_tools.py` (`tool.invoke({...})`).
- Real network calls in tests must be marked `@pytest.mark.network`.
- Keep `src/agentic_ai/` small and readable — it is meant to be read start to finish.
