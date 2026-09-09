# agentic-ai-starter

A minimal, **readable** starting point for building your own open-source agentic AI,
built on [LangChain](https://python.langchain.com/) + [LangGraph](https://langchain-ai.github.io/langgraph/).

The whole core is ~150 lines across five small files. Read it top to bottom in
ten minutes, then start replacing pieces with your own.

```
you > what is 2 + 2, and what time is it in UTC?
bot > I'll use the calculator and clock tools.
      2 + 2 = 4. The current UTC time is 2026-09-01T14:03:11+00:00.
```

---

## 1. What you are building

An **agent** is a loop around a language model that lets it *act*, not just answer:

```
        ┌─────────────────────────────────────────────┐
        │                                             │
        v                                             │
   ┌─────────┐   tool calls?   ┌─────────┐   results  │
   │  model  │ ───── yes ────> │  tools  │ ───────────┘
   └─────────┘                 └─────────┘
        │
      no tool calls
        │
        v
      answer
```

1. The model receives the conversation plus a list of **tools** (functions it may call).
2. If it responds with tool calls, your code runs those functions and feeds the
   results back.
3. Repeat until the model responds with a plain answer.

That is the entire idea. This is often called the **ReAct** pattern (reason + act).
LangChain's `create_agent` (built on LangGraph) gives you a battle-tested implementation of that
loop so you can focus on the two things that actually make an agent useful: its
**tools** and its **prompt**.

---

## 2. Project layout

```
agentic-ai-starter/
├── src/agentic_ai/
│   ├── config.py     # Settings: model, prompt, workdir (env-driven)
│   ├── llm.py        # build_model(): provider-agnostic chat model factory
│   ├── tools.py      # the tools the agent can call + a factory for the default set
│   ├── agent.py      # build_agent(): wires model + tools + memory into the loop
│   └── cli.py        # a tiny REPL (the `agentic-ai` command)
├── tests/
│   ├── fakes.py         # ScriptedChatModel: drives the loop with no network
│   ├── test_tools.py    # unit tests for each tool
│   └── test_agent.py    # the loop runs a tool, then answers
├── pyproject.toml    # deps, entry point, pytest/ruff/mypy config
└── .github/workflows/ci.yml
```

---

## 3. Quickstart

Requires Python 3.10+.

### With [uv](https://docs.astral.sh/uv/) (recommended)

```bash
git clone <your-fork-url> agentic-ai-starter
cd agentic-ai-starter

uv venv                       # create .venv
uv pip install -e ".[dev]"    # install project + dev tools

cp .env.example .env          # then paste your ANTHROPIC_API_KEY

uv run agentic-ai             # start the REPL
uv run pytest                 # run tests (no API key needed - fake model)
```

`uv run <cmd>` uses `.venv` automatically, so you never have to activate it.

### With plain pip

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
agentic-ai        # or: python -m agentic_ai.cli
pytest
```

---

## 4. How it works, module by module

### `config.py` - one place for every knob

`Settings` is a `pydantic-settings` model. Fields are filled from `AGENT_`-prefixed
environment variables or `.env`, with sane defaults. Change the model for a single
run without editing code:

```bash
AGENT_MODEL=claude-haiku-4-5 AGENT_TEMPERATURE=0.3 agentic-ai
```

### `llm.py` - the model factory

```python
from langchain.chat_models import init_chat_model

init_chat_model("claude-opus-5", temperature=0, max_tokens=4096)
```

`init_chat_model` is LangChain's provider-agnostic constructor. `claude-*` routes
to Anthropic automatically; other providers are one prefix away (see §6).

### `tools.py` - what the agent can actually do

A tool is a plain function with the `@tool` decorator:

```python
@tool
def multiply(a: float, b: float) -> float:
    """Multiply two numbers and return the product."""
    return a * b
```

- The **docstring** is the description the model reads - keep it short and concrete.
- The **type hints** define the argument schema the model must fill in.
- The **return value** is sent back to the model as the tool result.

The bundled tools: `add`, `multiply`, `now`, `search_wikipedia` (stdlib HTTP, no
extra deps), plus `read_text_file` and `list_files`, which are confined to
`settings.workdir` by `_safe_path()` - a small but important guard, because tools
are where an agent touches the real world.

`default_tools(settings)` returns the list. Filesystem tools are created inside
that factory so they can close over `workdir`.

### `gemini.py` - web-research tools

Three tools that need live web access - `profile_researcher` (summarise a person's
capabilities from a profile URL), `search_awarded_grants`, and
`find_competitor_labs` - don't scrape anything themselves. They call **Gemini**
directly (its own SDK, no `langchain-core` dependency) with Google Search +
URL-context grounding on, via one helper:

```python
ask_gemini("Research the person at <url> and summarise ...")  # -> str
```

The model does the browsing and returns prose; each tool is just a prompt around
`ask_gemini`. Enable them with:

```bash
uv pip install -e ".[gemini]"
echo "GOOGLE_API_KEY=..." >> .env          # AGENT_RESEARCHER_MODEL defaults to gemini-2.5-flash
```

Without the key or package the tools return a `gemini error: ...` string (the
agent reads it and moves on) rather than raising. To use a different search-capable
model instead, rewrite `ask_gemini` - it's the only place the provider is named.

### `agent.py` - assembling the loop

```python
create_agent(model, tools, system_prompt=system_prompt, checkpointer=InMemorySaver())
```

That call compiles a LangGraph state machine: `agent -> tools -> agent -> ... -> end`.
The `checkpointer` is the memory layer - see §7. Every argument to `build_agent`
is injectable so tests can pass a fake model or a custom tool list.

### `cli.py` - the REPL

Creates one agent, generates a random `thread_id`, and loops on `input()`. Because
the same `thread_id` is reused every turn, the checkpointer replays the full
history and the conversation has memory for the life of the process.

---

## 5. Add your own tool

1. Write the function in `tools.py`:

   ```python
   @tool
   def word_count(text: str) -> int:
       """Count the words in a piece of text."""
       return len(text.split())
   ```

2. Add it to the list returned by `default_tools`:

   ```python
   return [add, multiply, now, search_wikipedia, read_text_file, list_files, word_count]
   ```

3. Add a unit test in `tests/test_tools.py`:

   ```python
   def test_word_count():
       assert word_count.invoke({"text": "one two three"}) == 3
   ```

That's it - the model will pick it up on the next run. Tips:

- **Return strings, not exceptions**, when something goes wrong (`search_wikipedia`
  does this). The model can read the error and recover or explain.
- Tools that call external services should take a timeout and handle failure.
- If a tool has side effects (writes files, sends requests, spends money), gate it -
  see "human-in-the-loop" in §10.

---

## 6. Swap the model or provider

Everything flows through `AGENT_MODEL`. Install the integration package for your
provider and set the variable:

| Provider | Install | `AGENT_MODEL` | Auth |
|---|---|---|---|
| Anthropic (default) | included | `claude-opus-5`, `claude-sonnet-5`, `claude-haiku-4-5` | `ANTHROPIC_API_KEY` |
| OpenAI | `uv pip install -e ".[openai]"` | `openai:gpt-4.1` | `OPENAI_API_KEY` |
| Groq | `uv pip install -e ".[groq]"` | `groq:llama-3.3-70b-versatile` | `GROQ_API_KEY` |
| Ollama (local) | `uv pip install -e ".[ollama]"` | `ollama:qwen2.5` | none |
| llama.cpp / vLLM / LM Studio (local) | `uv pip install -e ".[openai]"` | `openai:<name>` + `AGENT_BASE_URL` + `AGENT_API_KEY=local` | none |

> Install providers via these **extras**, not a bare `pip install langchain-<x>`.
> LangChain integration packages version in lockstep with `langchain-core`; the
> extras pin each to the `1.x` line so a bare install can't pull a mismatched
> major that fails at import.

The rest of the code does not change - **as long as the model supports native
tool calling.** That rules out most small/base models; use an 8B+ instruct model
with documented tool support (Llama 3.1/3.3, Qwen2.5/Qwen3, Mistral, Hermes 3).

### Running the orchestrator locally

**Ollama** - install from [ollama.com](https://ollama.com), then:

```bash
ollama pull qwen2.5
uv pip install -e ".[ollama]"
echo "AGENT_MODEL=ollama:qwen2.5" >> .env
uv run agentic-ai
```

**Any OpenAI-compatible server** (llama.cpp `llama-server --jinja`, vLLM, LM Studio) -
point `AGENT_BASE_URL` at its `/v1` endpoint:

```bash
uv pip install -e ".[openai]"
```
```
AGENT_MODEL=openai:qwen2.5-7b-instruct
AGENT_BASE_URL=http://localhost:8080/v1
AGENT_API_KEY=local
```

`config.py` forwards `base_url` / `api_key` to the model only when set, so hosted
providers are unaffected. Note that `AGENT_MAX_TOKENS` is silently ignored by
Ollama (its knobs are `num_predict` / `num_ctx`, set via a Modelfile); local
models also have small context windows, so keep tool outputs short.

> The default is `claude-opus-5` (most capable). For cheaper iteration during
> development, set `AGENT_MODEL=claude-haiku-4-5` or `claude-sonnet-5`.

---

## 7. Memory and multi-turn

The agent state is a list of messages. A **checkpointer** persists that list per
`thread_id`:

```python
config = {"configurable": {"thread_id": "user-42"}}
agent.invoke({"messages": [{"role": "user", "content": "My name is Sam."}]}, config)
agent.invoke({"messages": [{"role": "user", "content": "What's my name?"}]}, config)
# -> "Your name is Sam."
```

`InMemorySaver` (the default) forgets everything when the process exits. For
persistence across restarts, use a database-backed saver:

```bash
pip install langgraph-checkpoint-sqlite
```

```python
from langgraph.checkpoint.sqlite import SqliteSaver

with SqliteSaver.from_conn_string("agent.db") as saver:
    agent = build_agent(checkpointer=saver)
```

Different `thread_id`s are fully isolated conversations - that is how you serve
many users from one process.

---

## 8. Streaming

`invoke` waits for the whole run. To show progress as it happens:

```python
for chunk in agent.stream(
    {"messages": [{"role": "user", "content": "Research X and summarize"}]},
    config,
    stream_mode="values",
):
    chunk["messages"][-1].pretty_print()
```

`stream_mode="messages"` gives you token-by-token output for a chat UI.

---

## 9. Testing approach

The loop is exercised without spending a cent by injecting `ScriptedChatModel`
(`tests/fakes.py`), which replays a fixed list of `AIMessage`s - tool calls and
all. `test_agent.py` scripts "call `add(2, 3)`" then "the answer is 5" and asserts
the loop ran the tool and produced the final text.

- Tools are pure-ish functions - test them directly with `tool.invoke({...})`.
- Real network calls must be marked `@pytest.mark.network` (deselected by default;
  run them with `pytest -m network`).
- `make lint` runs `ruff` + `mypy`; `make test` runs `pytest` with coverage.

---

## 10. Going further

Once the basics click, LangGraph scales up without a rewrite:

- **Custom graph** - drop `create_agent` and build your own `StateGraph`
  with planner / executor / critic nodes, retries, and branching.
- **Human-in-the-loop** - `interrupt()` before a dangerous tool to require
  approval; resume with `Command(resume=...)`.
- **Subagents** - make a whole agent a tool of a coordinator agent for
  fan-out research or per-file work.
- **RAG** - add a `retrieve(query)` tool backed by a vector store; the agent
  decides when to search.
- **Structured output** - pass `response_format=MyPydanticModel` to
  `create_agent` to get a typed final answer.
- **Observability** - set `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` to see
  every step, token, and tool call in [LangSmith](https://smith.langchain.com/).
- **Deploy** - wrap `agent.invoke` in a FastAPI route, or use the
  [LangGraph Platform](https://langchain-ai.github.io/langgraph/cloud/) for a
  managed server with persistence and streaming built in.

---

## 11. Worked example: the grant-fit analyst

A second, task-specific agent lives in `analyst.py` - it takes a project-context
document and a PI profile URL and produces a structured funding-fit report.

```bash
uv pip install -e ".[gemini,docs]"      # google-genai + pypdf/python-docx
echo "GOOGLE_API_KEY=..." >> .env        # plus your orchestrator model key

agentic-ai analyse ./project-context.pdf https://researcher.example.edu/~pi --call "NRF CRP"
agentic-ai analyse ./context.md https://orcid.org/0000-... --json
```

It is a **pure agent**, not a pipeline: three tools (`read_context`,
`web_research`, `profile_researcher`), a system prompt listing the five steps and
the report fields, and `response_format=GrantFitReport` for a typed result. The
model decides the order, the search queries, and when it has enough.

```python
from agentic_ai.analyst import analyse

report = analyse("context.pdf", "https://.../pi", grant_call="NRF CRP")
print(report.grant_to_pi_match_pct, report.proposed_direction)
```

- `report.py` - the `GrantFitReport` / `CompetitorTake` Pydantic schema (PI, grant
  call, strengths, match %, direction, competitors with attack/avoid, past grants).
- `documents.py` - `load_document()`: PDF / DOCX / TXT / MD -> text.
- The web steps go through Gemini (`gemini.py`); the reasoning and the final
  structured write-up use the orchestrator model (`build_model`).

Trade-offs vs. a fixed `StateGraph` pipeline or a hybrid (deterministic spine,
agentic nodes): reproducibility and per-run cost are traded for adaptivity - the
agent re-searches when a PI page is thin instead of building the report on weak
data. Swap in a pipeline if you need every report strictly comparable.

**Watch it run:**

- `scripts/demo_analyst.py` - streams the raw token / tool-call view to the terminal.
- `notebooks/analyst_ui.ipynb` - the same stream in a tiny `ipywidgets` form
  (`uv pip install -e ".[notebook]"`, then open the notebook and click *Run analyst*).
- `agentic-ai serve` - the browser UI (`uv pip install -e ".[web]"`), on
  http://127.0.0.1:8000. The page is still a placeholder; `GET /api/health`
  reports the orchestrator model and whether a Gemini key is set.

Both streaming views are built on `stream.py`'s `stream_analysis()`, which yields
the run as `AnalysisEvent`s (`token`, `tool_call`, `tool_output`, `report`, `error`).

---

## License

MIT - see [LICENSE](LICENSE). Replace the copyright holder with your name before
publishing your fork.
