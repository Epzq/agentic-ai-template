# Web UI implementation plan

Goal: a browser form that takes a **context document** (upload) and a **PI profile URL**,
streams the analyst's progress live, and renders the `GrantFitReport`.

Stack: FastAPI + server-sent events + one hand-written HTML page. No frontend build step.

Execute one work item per session. Each item is independently commitable, leaves the repo
green (`make lint && make test`), and states its own done-condition.

## Progress

Update this table and the item's STATUS line before committing. This file is the only shared
memory between sessions — an agent picking up the next item reads it and nothing else.

| Item | What | Status | Depends on |
|---|---|---|---|
| WI-1 | Extract streaming loop into `agentic_ai.stream` | ✅ done | — |
| WI-2 | FastAPI skeleton + `agentic-ai serve` | ✅ done | — |
| WI-3 | Document upload endpoint | ✅ done | WI-2 |
| WI-4 | SSE analysis endpoint | ✅ done | WI-1, WI-3 |
| WI-5 | Form and live progress log | ✅ done | WI-4 |
| WI-6 | Render the report | pending | WI-5 |
| WI-7 | Failure states and docs | pending | WI-6 |
| WI-8 | (optional) `--call` into the analyst prompt | pending | — |

---

## WI-1 — Extract the streaming loop into the package

> **STATUS: ✅ DONE** — `src/agentic_ai/stream.py` exposes `stream_analysis(document, pi_url,
> grant_call=None, *, settings=None, model=None, recursion_limit=25) -> Iterator[AnalysisEvent]`
> and the pydantic `AnalysisEvent`. Fields: `type` (`token` | `tool_call` | `tool_output` |
> `report` | `error`), `name`, `text`, `report`, plus **`reasoning: bool`** — an extra field
> beyond the plan's list, so a UI can dim thinking blocks the way the demo script does.
> `text` carries the tool's JSON args (`tool_call`) or its full, **untruncated** return value
> (`tool_output`) — truncation is the caller's job (WI-5). `stream_analysis` never raises:
> agent failure, missing report and failed `COERCE_PROMPT` coercion all come back as a final
> `error` event, so the SSE endpoint (WI-4) only has to forward events. Exactly one terminal
> event per run (`report` or `error`) — WI-4 adds its own `done` marker on top.
> The task string is built identically to `analyse()`, which means the demo script now also
> sends the `Target grant call: not specified …` line it previously omitted.
> `analyse()` in `analyst.py` is untouched. `scripts/demo_analyst.py` now consumes
> `stream_analysis` (112 lines, was 173); its commented-out local overrides (fake gemini,
> `./test_data/InfoSheet.pdf`) were left exactly as committed — that path does not exist in
> this checkout, so the script needs a real document path before it will run.

**Why first:** the web layer, the CLI and `scripts/demo_analyst.py` all need the same loop.
It exists today only inside `scripts/demo_analyst.py:main()`. Pure Python, no server, fully
testable with `ScriptedChatModel`.

**Do:**
- New `src/agentic_ai/stream.py` exposing:
  ```python
  def stream_analysis(document, pi_url, grant_call=None, *, settings=None,
                      model=None, recursion_limit=25) -> Iterator[AnalysisEvent]
  ```
- `AnalysisEvent` = a small pydantic model with `type` in
  `{"token", "tool_call", "tool_output", "report", "error"}` plus `name`/`text`/`report` fields.
  It must be JSON-serialisable — the SSE endpoint sends it verbatim.
- Move in from `demo_analyst.py`: the `stream_mode=["values", "messages"]` loop, the
  reasoning/thinking-block handling, tool-call and tool-output extraction, and the
  `COERCE_PROMPT` fallback when `structured_response` is `None`. Emit the final report as a
  `report` event; emit `error` instead of raising when coercion fails.
- Rewrite `scripts/demo_analyst.py` to consume `stream_analysis` and print — it should lose
  ~60 lines and keep identical terminal output.
- `analyse()` in `analyst.py` stays as-is (the non-streaming path the CLI uses).

**Test:** `tests/test_stream.py` — drive a `ScriptedChatModel` that emits one tool call then a
final answer; assert the event sequence is `tool_call → tool_output → token… → report`, and
that a `structured_response=None` model still yields a `report` event via the coercion path.

**Done when:** `python scripts/demo_analyst.py` behaves as before and `pytest tests/test_stream.py` passes.

`refactor: extract analyst streaming loop into agentic_ai.stream`

---

## WI-2 — FastAPI skeleton and the `serve` command

> **STATUS: ✅ DONE** — `src/agentic_ai/web/app.py` exposes
> `create_app(settings: Settings | None = None) -> FastAPI` (settings injectable, as
> everywhere else — WI-4 can build an app around a scripted model this way).
> `GET /api/health` → `{"ok": true, "model": settings.model, "gemini_key": bool}`;
> `GET /` → `web/static/index.html` via `FileResponse`, media type `text/html`
> (no `StaticFiles` mount — WI-5 needs only the one page). Module constants
> `STATIC_DIR` and `INDEX_HTML` point at it.
> **`gemini_key` checks `GOOGLE_API_KEY` *or* `GEMINI_API_KEY`**, not just the first —
> that is the pair `ask_gemini` actually accepts, so WI-7's banner won't cry wolf for
> someone who set only `GEMINI_API_KEY`.
> `web` extra added (`fastapi>=0.115`, `uvicorn[standard]>=0.30`,
> `python-multipart>=0.0.9`); `agentic-ai serve [--host 127.0.0.1] [--port 8000]`
> imports uvicorn and `create_app` inside `_serve()` and exits with a readable
> `pip install -e ".[web]"` message when the extra is absent.
> **No `[tool.hatch.build]` change was needed** (the plan asked for one): hatchling's
> `packages = ["src/agentic_ai"]` already ships non-Python files under the package —
> verified by building a wheel, which contained `agentic_ai/web/static/index.html`.
> Adding an explicit `include` would have *narrowed* what ships, so I left it alone.
> `index.html` is still the placeholder heading WI-5 replaces.

**Do:**
- `src/agentic_ai/web/__init__.py`, `src/agentic_ai/web/app.py` with `create_app() -> FastAPI`.
- Routes: `GET /` serving `web/static/index.html`, `GET /api/health` returning
  `{"ok": true, "model": settings.model, "gemini_key": bool(GOOGLE_API_KEY)}`.
- `index.html` is a placeholder heading at this stage.
- New `web` extra in `pyproject.toml`: `fastapi>=0.115`, `uvicorn[standard]>=0.30`,
  `python-multipart>=0.0.9`. Add the static dir to `[tool.hatch.build]` so it ships.
- `agentic-ai serve [--host 127.0.0.1] [--port 8000]` subcommand in `cli.py`, importing
  uvicorn lazily so the extra stays optional.

**Test:** `tests/test_web.py` with `fastapi.testclient.TestClient` — `/api/health` returns 200
with the model name; `/` returns 200 and `text/html`. Skip the module if `fastapi` is missing
so the default `.[dev]` install stays green.

**Done when:** `agentic-ai serve` starts and `curl localhost:8000/api/health` responds.

`feat(web): FastAPI skeleton and agentic-ai serve`

---

## WI-3 — Document upload endpoint

> **STATUS: ✅ DONE** — `POST /api/upload` (multipart field name **`file`**) →
> `UploadResponse{run_id, filename}`, where `filename` is the *sanitised* name, not the
> one sent. Stored at `<settings.workdir>/uploads/<run_id>/<name>`; `run_id` is
> `str(uuid.uuid4())`.
> **The run registry is `app.state.runs: dict[str, Path]`** — WI-4 looks the `run_id` up
> there and 404s on a miss. It is per-app-instance and in-process: restarting the server
> drops every run_id, and a multi-worker `uvicorn --workers N` would break it (each worker
> gets its own dict). Fine for one local user; a human should confirm that's acceptable
> before this is ever run multi-worker.
> `SUPPORTED_SUFFIXES` is derived from `documents._TEXT_SUFFIXES | {".pdf", ".docx"}` rather
> than retyped, so it can't drift from what `load_document` parses. Rejections:
> **400** for an unsupported/absent suffix (detail lists the accepted set), **413** for
> over `MAX_UPLOAD_BYTES` (10 MB, a module constant in `web/app.py`, deliberately *not* a
> `Settings` field — the plan asked for a cap, not a knob). The body is streamed in 64 KB
> chunks and checked as it goes, so an oversize file is never fully buffered; on any
> failure the whole run folder is `rmtree`'d, leaving no partial upload.
> `_safe_upload_path()` reduces the name with `PurePosixPath(name.replace("\\", "/")).name`
> (so `../../x.md` → `x.md`, and a Windows-style path can't smuggle a directory through on
> posix) and then re-checks that the resolved parent is the run dir. That second check is a
> backstop the route cannot currently reach — it is the only uncovered line in `web/app.py`
> — kept because rule 2 asks for the `_safe_path()` shape.
> The browser never receives a filesystem path.

**Do:**
- `POST /api/upload` (multipart) → `{"run_id": "<uuid>", "filename": "..."}`.
- Accept only the suffixes `documents.load_document` handles: `.pdf .docx .txt .md .markdown .rst`.
  Reject anything else with 400 and a readable message.
- Store at `<settings.workdir>/uploads/<run_id>/<sanitised name>`; sanitise with
  `Path(name).name` and reject a resolved path that escapes the run dir — same guard shape as
  `_safe_path()` in `tools.py` and `save_report`.
- Keep the server-side path in an in-process `dict[run_id, Path]`; the browser never sees a
  filesystem path.
- Cap the upload size (10 MB is plenty for a call sheet).

**Test:** upload a `.md` → 200 + run_id; upload a `.exe` → 400; a filename of `../../x.md`
lands inside the run dir.

**Done when:** the tests pass and the file appears under `workspace/uploads/<run_id>/`.

`feat(web): document upload endpoint`

---

## WI-4 — SSE analysis endpoint

> **STATUS: ✅ DONE** — `GET /api/analyse?run_id=&pi_url=&call=` (the third is optional)
> returns `text/event-stream`, plus `Cache-Control: no-cache` and `X-Accel-Buffering: no`
> so a proxy can't buffer it. Unknown `run_id` -> **404 before any streaming starts**, so
> it is a real HTTP error the browser's fetch can see, not an error event.
> Each `AnalysisEvent` is sent verbatim as `data: {json}\n\n`. The terminator is
> `DONE_EVENT` = `data: {"type": "done"}\n\n` — a plain payload with only a `type`, on the
> default `message` channel (NOT an SSE `event: done` line), so WI-5's `EventSource` needs
> only `onmessage` and can switch on `data.type`. It is deliberately **not** an
> `AnalysisEvent`: `done` belongs to the transport, so stream.py's five types stay as WI-1
> set them. `done` is always the last event, including after a failure, so WI-5 can always
> re-enable its button on it.
> **Threading:** the route hands `StreamingResponse` a plain *sync* generator; Starlette
> then wraps it with `iterate_in_threadpool` itself (verified in the installed source), so
> the blocking agent run never touches the event loop. No manual queue bridge was needed.
> Proven live: `/api/health` answered in 10 ms while a 6-second analysis was mid-flight.
> **Model injection:** `get_model()` is a FastAPI dependency returning `None` (meaning
> "let stream_analysis build the one Settings describes"). Tests and WI-5's manual checks
> override it with `app.dependency_overrides[get_model] = lambda: <scripted model>`.
> **Not tested at the HTTP layer:** that events arrive incrementally. `TestClient`'s httpx
> ASGI transport buffers the whole body, so the assertion is impossible there regardless of
> how slow the model is; it was verified live instead with `curl -N` timestamps, which show
> the events spread across the model's think time.

**Do:**
- `GET /api/analyse?run_id=…&pi_url=…&call=…` → `text/event-stream`.
- Look the run_id up; 404 if unknown. Call `stream_analysis` from WI-1 and emit each event as
  `data: {json}\n\n`. Terminate with a `done` event.
- `stream_analysis` is blocking and synchronous — run it in a worker thread
  (`starlette.concurrency.iterate_in_threadpool`, or a thread + `queue.Queue` bridge) so one
  run doesn't block the event loop.
- Catch any exception from the generator and emit it as an `error` event before closing;
  the stream must never die silently.

**Test:** `TestClient` with a dependency-override that swaps in a scripted model; read the
stream and assert the JSON events arrive in order and end with `report` then `done`.

**Done when:** `curl -N "localhost:8000/api/analyse?run_id=…&pi_url=…"` prints live events.

`feat(web): SSE endpoint streaming analyst progress`

---

## WI-5 — The form and the live progress log

> **STATUS: ✅ DONE** — `web/static/index.html` only; no Python changed. One file, inline
> CSS/JS, no framework, no CDN, no build step. Element ids WI-6 can build on: `#form`,
> `#file`, `#pi`, `#call`, `#go`, `#progress`, `#state`, `#elapsed`, `#log`.
> Flow: `fetch POST /api/upload` → `new EventSource("/api/analyse?" + params)` →
> `onmessage` switching on `data.type`. `finish()` is idempotent and runs on **either**
> `done` or `error`, so a failed run re-enables the button without waiting for the
> terminator. `MAX_DETAIL = 300` chars for any `tool_output` preview (a whole PDF comes
> back through `read_context`).
> `STEP_LABELS` maps tools to plain language, including **`GrantFitReport` → "Composing the
> report"** — the structured-output step arrives as a tool call named after the schema, and
> would otherwise show up as a raw class name.
> **Two real behaviours the live run exposed, which WI-6/WI-7 must not undo:**
> (1) gemini-2.5-flash sends each `tool_call` as one event with complete JSON args, not
> fragments — but the fragment accumulator is kept, since WI-1 emits `tool_call_chunks`
> for models that do stream them.
> (2) The agent issues **several tool calls before any returns**, and their outputs can come
> back **in a different order than the calls went out**. Since `AnalysisEvent` carries no
> tool-call id, an output cannot be matched to its call once two calls of the same tool are
> in flight. The page therefore pairs an output with its call only while that tool has
> exactly one call open, and otherwise gives the result its own "… — result" line rather
> than captioning the wrong question. **If precise pairing is ever wanted, the fix is to add
> the call `id` to `AnalysisEvent` in `stream.py` — a WI-1 change, deliberately not made
> here.**
> The `report` event is only acknowledged with a "Report ready." line; rendering the fields
> is WI-6's job.
> Verified in a real headless Chromium against a real end-to-end run (see the item report).

**Do:** replace the placeholder `index.html` with the real page (inline CSS/JS, no build step):
- File input (accepting the WI-3 suffixes), PI URL input (`type=url`, required),
  optional grant-call text input, Analyse button.
- On submit: POST to `/api/upload`, then open an `EventSource` on `/api/analyse`.
- Progress panel translating `tool_call` events into plain language rather than raw names —
  `read_context` → "Reading the document…", `profile_researcher` → "Researching the PI…",
  `web_research` → "Searching the web: <the question>", `save_report` → "Saving the report…".
- Disable the button and show elapsed time while running; re-enable on `done` or `error`.
- Truncate long `tool_output` text in the log (`read_context` returns a whole PDF).

**Done when:** a real end-to-end run shows progress lines appearing over several minutes.

`feat(web): upload form and live progress log`

---

## WI-6 — Render the report

**Do:** on the `report` event, render every `GrantFitReport` field:
- PI, grant call, proposed direction.
- `grant_to_pi_match_pct` as a labelled bar plus `match_rationale`.
- `pi_strengths_and_track_record`.
- Competitors as cards or a table: group, institution, their strengths, vs PI, and **attack** /
  **avoid** visually distinguished — that contrast is the point of the report.
- `relevant_past_grants` as a list, linkifying bare URLs.
- A "Download JSON" button (client-side blob from the event payload) and the path
  `save_report` wrote, if the run produced one.

**Done when:** a full run renders a readable report with no field omitted.

`feat(web): render the grant-fit report`

---

## WI-7 — Failure states

The agent reports failures as *strings*, so nothing raises and the UI can stall looking healthy.

**Do:**
- Detect tool outputs starting with `gemini error:`, `read failed:`, `lookup failed:`,
  `save failed:` and surface them as a visible warning in the log, not silently.
- Pre-flight on `/api/health`: if `GOOGLE_API_KEY` is unset, show a banner on page load —
  every web tool will fail without it.
- Handle recursion-limit exhaustion (no `report` event ever arrives) with a clear message.
- Handle the browser closing mid-run: cancel the worker.
- README section: install `.[web]`, run `agentic-ai serve`, screenshot or description.

`feat(web): surface tool failures and add setup docs`

---

## WI-8 (optional) — Wire `--call` into the analyst prompt

Unrelated to the UI but adjacent: `_SYSTEM` in `analyst.py` never mentions the target grant
call — it reaches the model only through the task string, so `--call "CRP"` is weaker than it
looks. Add an explicit instruction and a test.

`fix(analyst): honour the target grant call in the system prompt`
