# Research Opportunity Intelligence

Give it a **grant call** (URL or PDF) and a **researcher's public profile**, and it returns
**3 ranked research directions** to pursue under that call — each backed by evidence it
actually retrieved, with the ranking exposed rather than asserted.

It does **not** write a proposal. It helps decide what to write one *about*.

## Why it is built the way it is

The product's whole value is that the output can be trusted. So:

- **Python retrieves and mints every piece of evidence; the LLM only cites IDs.** No LLM output
  schema has a `url` field — a fabricated citation cannot survive validation, let alone render.
- **The ranking is arithmetic, not an opinion.** The LLM scores each criterion with evidence;
  Python does the weighted sum. That is what makes the in-browser weight sliders honest.
- **A gap is only "open" on positive evidence.** Finding nothing means *don't know*, never *nobody
  has done this*.

## Layout

```
backend/     the Python project — roia/, tests/, fixtures/, pyproject.toml, .env, .venv/
frontend/    the Vite + React app; FastAPI serves its dist/ at the same origin in prod
*.md         the planning documents, below
```

Every Python command is run from `backend/`. Paths written inside that directory are relative
to it; the planning documents at the root spell them out in full (`backend/roia/api.py`).

## Documents

### Slash commands

Three, in `.claude/commands/`. They are the intended way to work on this repo.

| Command | What it does |
|---|---|
| `/explain-app <question>` | **Understanding it.** Answers from the documents *and* the code, and always marks what is in the demo versus what exists only in `plan.md`'s full design. `/explain-app explain all the tools and what each is for` |
| `/fix-in-app <requirement>` | **Changing it.** Reads the design, surfaces every conflict and risk in your request, **asks before deciding anything**, writes an agreed work item into `execution-plan.md`, then hands off to `/execute-workitem`. It never edits code itself |
| `/execute-workitem <id>` | **Building it.** One work item per session, end to end — implement, self-review, test, mark done, commit. `EXECUTION_PROMPT.md` is a pointer to it |

### Documents

| File | Read it for |
|---|---|
| `how-to-use.md` | **Running it.** Setup, the two commands, what inputs to give, what the output means. Plain English, no internals |
| `e2e-flow.md` | **How it works.** Input to report in twelve steps, every tool call and its purpose, and what the tool deliberately does not do. Written for someone with no context |
| `execution-plan.md` | The work items, dependencies, hours, cut order — and, at the end, §The review pass and §Known and not fixed |
| `demo-spec.md` | The 2-day scope: acceptance criteria, non-goals, architecture, contracts |
| `plan.md` | The full ~15-day design and the reasoning behind it |
| `requirements_design.md` | The original product requirement |
| `tool-comparison.md` | Plain-English: what this gives you over a simpler tool |

`demo-spec.md` wins over `plan.md` wherever they differ — `plan.md` describes a larger system
that is not being built yet.

## Status

**Complete. All 22 work items are done and all 16 acceptance criteria are ticked**, each with the
one command that proves it — see the AC walk-through at the end of `execution-plan.md`.

It runs three ways: from a terminal, over HTTP, and in a browser.

```
$ cd backend
$ python -m roia run --grant https://www.rgp.gov.sg/nrf-ar/crp --out runs/demo
  run-20260906-025302   158s
  directions : 3        evidence : 85 rows, 12 papers      events : 162
  report     : runs/demo/report.json · runs/demo/report.md
```

That run reads the call and the researcher's page, resolves the author in OpenAlex, proposes
three directions **without** seeing any literature, runs nine searches, reads twelve papers'
abstracts (capped at 400 chars), measures each field's trend and citing counts, then writes the gaps
— with the evidence catalogue in front of it. Every citation in `report.md` resolves to a record
the tool retrieved. **310 hermetic tests** and **45 browser tests**, plus 8 marked `live` that hit the real APIs.

The same run is available over HTTP, with the activity timeline streaming as it happens:

```
$ cd backend && uvicorn roia.api:app_factory --factory --port 8000   # no --reload during a run
$ curl -s -X POST localhost:8000/api/runs -H 'Content-Type: application/json' \
       -d '{"grant_url":"…","profile_url":"…"}'                      # -> 201 {"run_id": …}
$ curl -N localhost:8000/api/runs/$RUN/events                        # every event, from seq 0
$ curl -s localhost:8000/api/runs/$RUN/report.md                     # the report, as markdown
```

And in a browser, which is where the evidence is actually legible — three ranked cards, every
claim carrying chips you can click through to the record it came from, nine weight sliders that
re-rank in **52 ms with no network traffic**, and a live activity timeline.

```
$ cd frontend && nvm use && npm run build     # Node 20.19+/22.12+; the default node here is 18
$ cd ../backend && uvicorn roia.api:app_factory --factory --port 8000
$ open http://localhost:8000/
```

**No API keys, no waiting:** `?fixture=run-001` replays a real recorded run — 162 events in 19 s,
or `&speed=10` for two. It is both the frontend iteration loop and the demo-day fallback, and it
serves the finished report too.

```
$ open 'http://localhost:8000/runs/run-001?fixture=run-001&speed=10'
$ curl -N 'localhost:8000/api/runs/run-001/events?fixture=run-001&speed=10'
```

⚠️ **Before demoing, look at the report.** The per-criterion score spread varies between runs:
one run had six of seven criteria re-ranking the directions, another had one. The weight sliders
are the third thing the demo claims, and a flat run undersells it. A `compressed_scores` warning
fires when that happens — re-run if you see it.

## Setup

```bash
cd backend
cp .env.example .env               # then fill in both keys
python3.12 -m venv .venv           # 3.12 exactly, not the system python3
.venv/bin/pip install -e '.[dev]'  # every dependency is pinned ==, not floored
.venv/bin/pytest                   # 310 passed, 53 deselected
```
