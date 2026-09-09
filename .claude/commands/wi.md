---
description: Implement one work item from docs/ui-plan.md end to end — plan, implement, self-review, test, mark done, commit
argument-hint: "<work item id, e.g. 3 or WI-3>"
---

## Your work item: $ARGUMENTS

**Normalise the id first.** If `$ARGUMENTS` doesn't start with `WI-`, prefix it: `3` → `WI-3`.
That normalised id is **the work item** below.

**If `$ARGUMENTS` is empty, or no `## WI-…` heading in `docs/ui-plan.md` matches:** stop
immediately. Print the Progress table, name the next `pending` item whose dependencies are done,
and ask which the user wants. Do not guess and do not start work.

You are implementing **exactly that one work item — and nothing else.**

---

## 1. The project

`agentic-ai-template` — a **grant-fit analyst**. Given a context document (PDF/DOCX/TXT/MD) and a
PI's profile URL, it produces a `GrantFitReport`: the PI's strengths, a 0–100 match against a
grant call, one proposed research direction, competing labs with attack/avoid angles, and
relevant past grants.

It is a LangChain 1.x `create_agent` ReAct loop, not a pipeline — the model chooses the order of
its tools. `CLAUDE.md` in the repo root has the architecture; read it. You are building a web UI
in front of `analyse()`; **the agent itself is not yours to change** unless your work item says so.

Run everything from the repo root with the conda env active:

```bash
conda activate agentic-ai
```

## 2. Read before writing code

| File | Why |
|---|---|
| `docs/ui-plan.md` | **Your task list and the shared memory between sessions.** Your item's Do / Test / Done-when, and the STATUS lines of items before it | 
| `CLAUDE.md` | Architecture, conventions, commands |
| `src/agentic_ai/analyst.py`, `report.py` | What you are wrapping and the exact shape you must render |
| `scripts/demo_analyst.py` | The streaming loop WI-1 extracts; the reference for event handling |
| `tests/fakes.py`, `tests/conftest.py` | `ScriptedChatModel` — how to test without a network or a key |

**Read the `STATUS` lines of completed items.** They record decisions already made — event field
names, endpoint shapes, chosen libraries. Do not contradict or re-litigate them.

## 3. Rules you may never break

1. **Tools return error strings; they never raise.** `"gemini error: …"`, `"read failed: …"`,
   `"lookup failed: …"`, `"save failed: …"` are values the agent reads and recovers from. If you
   add a tool or touch one, keep this. And in the UI: a returned error string is a *visible*
   failure, never a silent one — that is the whole point of WI-7.
2. **Confine every filesystem path.** Uploads, reports, workdir tools — resolve the target and
   reject anything that escapes its base, the way `_safe_path()` in `tools.py` and `save_report`
   in `analyst.py` already do. The browser must never send or receive a server filesystem path.
3. **Tests make no network calls and need no API key.** Inject `ScriptedChatModel`. Anything that
   genuinely must hit the network is `@pytest.mark.network` (deselected by default).
4. **New deps go in an extra, imported lazily.** `fastapi`/`uvicorn` belong to `.[web]`; a plain
   `.[dev]` install must still import, lint and test clean. Skip web tests when `fastapi` is absent.
5. **Never invent scope.** If your item's Do list doesn't mention it, it isn't yours. No
   refactoring outside the item, no "small version" of a later item.
6. **Never fake a passing test.** No `assert True`, no vacuous test, no `pytest.skip` to get green.
   If a test can't pass, the code or the plan is wrong — say so (§7).
7. **Keep `src/agentic_ai/` readable.** It is meant to be read start to finish. Match the
   surrounding style, naming and comment density.

## 4. The loop

### Step 1 — Orient
Read your item's **Do**, **Test** and **Done when** lines. Confirm its dependencies (the
Progress table's *Depends on* column) are marked done. If one isn't built, **stop and say so** —
do not stub it.

### Step 2 — Plan
State in three or four lines: files created/changed, public functions added, tests you'll write.
If that doesn't match the item's Do list, re-read the Do list.

### Step 3 — Implement
- Type-annotate public functions; pydantic models for anything crossing a boundary.
- Anything the browser receives must be JSON-serialisable.
- Never let an external call raise into the request handler — catch it and turn it into a
  visible `error` event or an HTTP error with a readable message.
- Frontend: no build step, no framework, no CDN. Inline CSS/JS in `index.html`.

### Step 4 — Self-review
Re-read your own diff and answer honestly:
- Does every line of the Do list have code behind it?
- Does the **Done when** line actually hold, or did I approximate it?
- Did I break any rule in §3?
- Did I add anything the item didn't ask for?
- Can an exception escape to the caller? Can a path escape its base directory?
- Are there hardcoded values that belong in `Settings` (`config.py`)?

Fix what you find **before** running tests.

### Step 5 — Test
See §5. Every work item ends green.

### Step 6 — Self-correct
Fix the code and re-run. Do not weaken a test to make it pass. If you weaken or delete an
assertion, say so explicitly in your final summary and why.

### Step 7 — Mark it done
Before committing, update `docs/ui-plan.md` in two places:
1. The **Progress** table — your row `pending` → `✅ done`.
2. A `> **STATUS: ✅ DONE**` line immediately under your item's `##` heading, recording what the
   next agent needs: names you chose (event types, endpoint paths, query params), values you
   settled on, anything you deliberately left out, any assumption a human should confirm.

If the item is only **partially** done, write `> **STATUS: ⚠️ PARTIAL**` and list exactly what is
outstanding and why. Never mark it done when the Done-when line doesn't hold.

**Then check the user-facing docs.** If your change alters how the tool is run or what it shows,
update `README.md` and `HOW-TO-USE.md` in the same commit — `HOW-TO-USE.md` is the conda-based
guide this checkout actually follows, and a claim the code no longer supports is worse than none.

### Step 8 — Commit
Only once tests are green, the Done-when line genuinely holds, and `docs/ui-plan.md` is updated.
Plan update goes in the same commit as the code.

## 5. Testing

Every work item, always:

```bash
conda activate agentic-ai
make lint          # ruff check src tests + mypy src
make test          # pytest, coverage, -m 'not network'
pytest tests/test_stream.py -x          # just your new file, while iterating
```

Backend logic (WI-1): drive it with `ScriptedChatModel` from `tests/fakes.py` — encode tool calls
as `AIMessage(tool_calls=[...])` and assert on the emitted event sequence. Set
`structured_response=None` on the fake to exercise the `COERCE_PROMPT` fallback path.

HTTP (WI-2 … WI-4): `fastapi.testclient.TestClient`, with the whole module guarded by
`pytest.importorskip("fastapi")`. Verify SSE by reading the response body and parsing `data:` lines.

Frontend (WI-5, WI-6): no test framework — verify by hand and say exactly what you did:

```bash
agentic-ai serve                        # then open http://127.0.0.1:8000
curl -s localhost:8000/api/health | python -m json.tool
curl -N "localhost:8000/api/analyse?run_id=…&pi_url=…"   # -N or you'll see nothing and blame the server
```

A **real** end-to-end run costs Gemini calls and takes minutes. Run one when the item's Done-when
line requires it (WI-5, WI-6, WI-7) — use `data/CRP Call Information Sheet.pdf` and
`https://basurafernando.github.io/` — and don't for the rest.

## 6. Commit

One commit per work item. Stage only its files; check `git diff --cached` first.

```
WI-<id>: <short imperative summary>

<why, and any non-obvious decision>

Tests: <n> added, pytest green, ruff + mypy clean
Plan: docs/ui-plan.md marked done
```

**Never commit** `.env`, `.env.bak`, `.venv/`, `workspace/uploads/`, `reports/`, `data/`,
`__pycache__/`, or anything containing a key. `.env.bak` is untracked and not covered by name in
`.gitignore` — do not add it.

## 7. When you are blocked or the plan is wrong

**Stop and report. Do not improvise.**

If the plan contradicts the code (a function it names doesn't exist, a shape it assumes is
different):
1. Quote the conflicting lines, with file and line numbers.
2. Say what you think the right resolution is and why.
3. Implement everything in the item that does **not** depend on the answer.
4. Report what you left out.

Same for a genuinely blocked dependency — a missing `GOOGLE_API_KEY`, a rate limit, an upstream
403. Report it plainly with the error, say what you tried, and stop. Don't fabricate data or a
canned response to keep moving.

## 8. Anti-patterns

| Don't | Why |
|---|---|
| Make a tool raise instead of returning an error string | Kills the agent loop mid-run; breaks rule 1 |
| Show a spinner and swallow a `gemini error:` result | The run looks healthy and the report is empty — the failure mode WI-7 exists for |
| Put `fastapi` in the base `dependencies` | A `.[dev]`-only install must stay green |
| Accept a filesystem path from the browser | Arbitrary read; use the `run_id` → path mapping |
| Block the event loop with the synchronous agent run | One analysis freezes the whole server |
| Log a whole `read_context` output to the browser | It's an entire PDF; truncate |
| Add a JS framework or a CDN script | No build step by design; keep it one HTML file |
| Refactor `analyst.py` while doing a UI item | Keeps the diff reviewable |

## 9. Finish by reporting

- Which Do-list points you completed, and any you didn't, with the reason
- Confirmation `docs/ui-plan.md` is updated (Progress row + STATUS line)
- Test counts and the exact commands you ran, with their real output
- Whether you did a live end-to-end run, and what you saw
- Any assumption a human should confirm
- The commit hash
