# How to Run the Grant-Fit Analyst

Set up the backend and run the app in a browser. Start to finish, on a clean machine, this
takes about ten minutes — most of it waiting for `pip`.

**What you get:** a page where you upload a grant-call document and paste a researcher's
profile URL, watch the agent work in real time, and read a structured funding-fit report.

---

## 1. Prerequisites

| | |
|---|---|
| Python | 3.10 or newer (3.11 recommended) |
| Conda | Miniconda or Anaconda — [install](https://docs.conda.io/projects/miniconda/) |
| A Gemini API key | Free tier is enough. Get one at [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| A browser | Anything current. The page uses `EventSource`, supported everywhere since 2011 |

The API key is not optional. The analyst's research tools are the whole product, and they all
go through Gemini — without a key the app starts, the page loads, and every run comes back
empty.

---

## 2. Create the environment

From the project root:

```bash
conda create -n agentic-ai python=3.11 -y
conda activate agentic-ai
```

You create it once. Every session after this needs only `conda activate agentic-ai`.

Confirm you're in the right place:

```bash
python --version     # Python 3.11.x
which python         # .../envs/agentic-ai/bin/python
```

If `which python` doesn't mention `agentic-ai`, the environment isn't active and everything
below will install into the wrong place.

---

## 3. Install the project

```bash
pip install -e ".[web,gemini,docs]" "langchain[google-genai]"
```

Four things, and you need all four:

| Piece | What it brings |
|---|---|
| `.[web]` | FastAPI, uvicorn, python-multipart — the server and file uploads |
| `.[gemini]` | `google-genai`, the SDK the web-research tools call directly |
| `.[docs]` | `pypdf` and `python-docx`, so the agent can read PDF and Word call documents |
| `langchain[google-genai]` | Lets the **orchestrator** run on Gemini instead of Claude |

`-e` installs in editable mode: edit the source and the change is live on the next restart, no
reinstall.

Check it landed:

```bash
agentic-ai --help
agentic-ai serve --help
```

---

## 4. Configure

Create `.env` in the project root:

```bash
cp .env.example .env
```

Open it and make it read:

```ini
# The orchestrator - the model that runs the agent loop and decides which tool to call
AGENT_MODEL=google_genai:gemini-2.5-flash

# Your key. Powers both the orchestrator and the web-research tools
GOOGLE_API_KEY=paste_your_real_key_here

# The model behind profile_researcher / web_research (Google Search grounded)
AGENT_RESEARCHER_MODEL=gemini-2.5-flash

# Optional
AGENT_TEMPERATURE=0.0
AGENT_MAX_TOKENS=4096
AGENT_WORKDIR=./workspace        # uploads land in ./workspace/uploads/<run_id>/
AGENT_REPORTS_DIR=./reports      # save_report writes ./reports/<PI name>/report.md
```

You do **not** need `ANTHROPIC_API_KEY`. The repo's code default is `claude-opus-5`, but the
`AGENT_MODEL` line above overrides it — `.env` wins.

`.env` holds a live credential. It's already in `.gitignore`; keep it that way, and don't
commit `.env.bak` either.

### Verify the key loads

```bash
python -c "
from dotenv import load_dotenv; load_dotenv()
import os
print('key loaded:', bool(os.getenv('GOOGLE_API_KEY')))
print('model     :', os.getenv('AGENT_MODEL'))"
```

Expect `key loaded: True`. If it says `False`, you're not in the directory holding `.env`.

---

## 5. Start the server

```bash
agentic-ai serve
```

```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

Open **http://127.0.0.1:8000**.

Confirm the backend is healthy before using the page:

```bash
curl -s localhost:8000/api/health
# {"ok":true,"model":"google_genai:gemini-2.5-flash","gemini_key":true}
```

`"gemini_key": false` means the key isn't reaching the process — the page will show a warning
banner saying the same thing. Go back to §4.

### Options

```bash
agentic-ai serve --port 8080          # if 8000 is taken
agentic-ai serve --host 0.0.0.0       # reachable from other machines - see the warning below
```

> **`--host 0.0.0.0` exposes the app to your whole network.** There is no login, no
> authentication, and no rate limit: anyone who can reach the port can upload files and spend
> your API quota. Use it only on a trusted network, and prefer the SSH tunnel below.

### Running on a remote server

If the project lives on a remote box (as it does here, under `/data/nrf1/...`), leave the
server bound to localhost and tunnel to it from your laptop:

```bash
# on your laptop
ssh -L 8000:localhost:8000 you@the-server
```

Then open `http://127.0.0.1:8000` in your local browser. The traffic goes over SSH and the
port is never exposed.

---

## 6. Using the page

Three fields:

| Field | Notes |
|---|---|
| **Context document** | The grant call or project brief. PDF, DOCX, TXT, MD, RST. Max 10 MB. Uploaded — you don't type a path, so filenames with spaces are fine |
| **PI profile URL** | Faculty bio, lab site, Google Scholar, ORCID. The agent hands this to Gemini, which browses it |
| **Grant call** *(optional)* | e.g. `NRF CRP`. Leave blank and the agent identifies the best-fit open call itself |

Click **Analyse**.

### What you'll see

A live log, because **a real run takes several minutes** and silence would look like a hang:

```
Reading the document…
Researching the PI…
Searching the web: awarded NRF CRP grants in computer vision…
Searching the web: research groups working on video understanding…
Saving the report…
```

An elapsed timer runs alongside it. Then the report appears:

- **PI** and the **grant call** it was matched against
- **Match %** as a bar, with the rationale behind the number
- **PI strengths and track record**
- **Proposed direction** — one specific, fundable idea
- **Competitors** — each lab with their strengths, how they compare to the PI, and an
  **attack** / **avoid** angle
- **Relevant past grants**, with links where the agent found them

**Download JSON** saves the raw report. The agent also writes a Markdown copy to
`./reports/<PI name>/report.md`; the page shows that path when it does.

Try it with the file already in this repo:

- Document: `data/CRP Call Information Sheet.pdf`
- PI URL: `https://basurafernando.github.io/`

---

## 7. The CLI, if you prefer it

The same analysis without a browser:

```bash
agentic-ai analyse "data/CRP Call Information Sheet.pdf" \
    "https://basurafernando.github.io/" --call "CRP"

agentic-ai analyse "data/CRP Call Information Sheet.pdf" \
    "https://basurafernando.github.io/" --json     # raw JSON

agentic-ai                                          # a general chat REPL
```

Quote paths containing spaces. `HOW-TO-USE.md` covers the CLI in more depth.

---

## 8. Stopping and restarting

`Ctrl-C` stops the server. Uploads under `workspace/uploads/` and reports under `reports/`
survive; the in-memory `run_id → file` map does not, so a page left open across a restart must
re-upload before it can analyse again.

Next time, all you need is:

```bash
conda activate agentic-ai
agentic-ai serve
```

---

## 9. Troubleshooting

### `agentic-ai: command not found`
The environment isn't active, or the install didn't happen in it.
```bash
conda activate agentic-ai
pip install -e ".[web,gemini,docs]" "langchain[google-genai]"
```

### `serve needs the web extra: pip install -e ".[web]"`
Exactly what it says — FastAPI and uvicorn aren't installed. Rerun the §3 command.

### The page shows a warning banner about `GOOGLE_API_KEY`
The server can't see your key. Check `.env` is in the directory you launched from, has no
quotes around the value, and no space before the `=`. Then restart the server — `.env` is read
at startup.

### `Unable to import langchain_google_genai`
```bash
pip install -U "langchain[google-genai]"
```

### `[Errno 98] Address already in use`
Something already holds port 8000. Use another: `agentic-ai serve --port 8080`.

### The log stalls, or the report is full of "could not be found"
Almost always the key or quota. Every research tool returns its failure as text starting
`gemini error:` rather than crashing — the log surfaces those, so read it. Check your quota at
[aistudio.google.com](https://aistudio.google.com/).

### `unsupported document type`
Only `.pdf`, `.docx`, `.txt`, `.md`, `.markdown`, `.rst`. Convert first.

### "file is larger than 10 MB"
The cap is `MAX_UPLOAD_BYTES` in `src/agentic_ai/web/app.py`. A call document that big is
usually mostly images — extract the text pages instead of raising the limit.

### The browser shows the report but `reports/` is empty
The agent decides when to call `save_report`; it sometimes finishes without it. Use **Download
JSON** — the structured report is always in the page.

---

## 10. For developers

```bash
make test        # pytest, no network and no API key needed
make lint        # ruff + mypy
make fmt         # ruff --fix and format

pytest tests/test_web.py -x        # one file
pytest -m network                  # the tests that do hit the network
```

Tests inject a fake model (`tests/fakes.py`), so the suite runs offline and costs nothing.

### How the pieces fit

```
browser  ──POST /api/upload──▶  saves to workspace/uploads/<run_id>/, returns run_id
         ──GET  /api/analyse─▶  SSE stream of AnalysisEvents
                                  │
                                  ▼
                            stream_analysis()          src/agentic_ai/stream.py
                                  │
                                  ▼
                            the analyst agent          src/agentic_ai/analyst.py
                             ├── read_context          documents.py  (PDF/DOCX/TXT/MD)
                             ├── profile_researcher ─┐
                             ├── web_research      ──┤ Gemini + Google Search  gemini.py
                             └── save_report          → reports/<PI>/report.md
```

Two model providers by design: the orchestrator goes through LangChain (`llm.py`), while
anything needing live web access calls the `google-genai` SDK directly (`gemini.py`) — that
keeps the search-grounded calls free of any `langchain-core` version constraint.

`CLAUDE.md` has the architecture in full; `docs/ui-plan.md` records how the web UI was built,
work item by work item.
