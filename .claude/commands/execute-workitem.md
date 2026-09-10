---
description: Implement one work item from execution-plan.md end to end — implement, self-review, test, mark done, commit
argument-hint: "<work item id, e.g. 1.0 or WI-2.5>"
---

## Your work item: $ARGUMENTS

**Normalise the id first.** If `$ARGUMENTS` does not already start with `WI-`, prefix it:
`1.0` → `WI-1.0`, `2.4a` → `WI-2.4a`, `WI-1.6c` → `WI-1.6c` unchanged. That normalised id is
referred to below as **the work item**.

**If `$ARGUMENTS` is empty, or no matching `### WI-…` heading exists in `execution-plan.md`:**
stop immediately. Print the Progress table from `execution-plan.md`, name the next `pending` item
on the critical path, and ask which the user wants. Do not guess and do not start work.

---

You are implementing **exactly that one work item — and nothing else.**

## 1. What this project is

A **Research Opportunity Intelligence** tool. A researcher gives it two things — a grant call (URL or PDF) and their own public profile page — and it returns **3 ranked research directions** they should consider pursuing under that call, each backed by evidence it actually retrieved.

Backend Python + FastAPI. Frontend React + Vite + TypeScript + MUI. LLM is Google Gemini.

**Repo layout** — the Python project lives in `backend/`, the Vite app in `frontend/`, and the
planning documents at the root:

```
backend/    roia/  tests/  fixtures/  spikes/  reference/  pyproject.toml  .env  .venv/
frontend/   the Vite + React app; FastAPI serves its dist/ at the same origin in prod
*.md        demo-spec.md, execution-plan.md, plan.md, …
```

**Every Python command below is run from `backend/`** — that is where `pyproject.toml`, the venv
and `.env` are. Paths inside `backend/` are written relative to it (`roia/api.py`, not
`backend/roia/api.py`); the planning docs at the root spell them in full.

The product's entire value is that **a researcher can trust the output**. A beautifully formatted report citing papers that don't exist is worse than no product. Almost every rule below exists to make fabrication structurally impossible rather than merely discouraged.

## 2. Read these before writing code

| File | What it is | When you need it |
|---|---|---|
| `execution-plan.md` | **Your task list and the shared memory between sessions.** Find the work item; read its checklist, its Done line, and the `STATUS` lines on the items before it | Always — start here, and update it before you commit |
| `demo-spec.md` | The 2-day scope: acceptance criteria (§3), non-goals (§4), architecture (§5), contracts (§6) | Always |
| `plan.md` | The full ~15-day design. Explains *why* the demo is shaped this way | When a decision isn't covered by `demo-spec.md` |
| `requirements_design.md` | The original product requirement | Rarely — for intent behind an output field |
| `tool-comparison.md` | Plain-English comparison for non-technical readers | Only if changing what we claim the tool does |
| `how-to-use.md`, `e2e-flow.md` | The user guide and the end-to-end walkthrough | **If your change alters what the user sees or what the tool claims, update these in the same commit** — see §7 |
| `backend/reference/config_pattern.py` | The settings pattern to port | WI-1.1 |

**`demo-spec.md` wins over `plan.md` wherever they differ.** `plan.md` describes a larger system we are not building yet.

## 3. Six rules you may never break

1. **Python mints evidence; the LLM only cites IDs.** Only retrieval code calls `EvidenceStore.mint()`. No LLM output schema may contain a `url`, `source_title`, or `link` field. If you catch yourself adding one, stop — you have misread the design.
2. **Ranking is arithmetic, never an LLM.** `compute_ranking()` is pure Python. The LLM supplies per-criterion scores with evidence; Python multiplies and sums.
3. **Call #3 must not see literature; call #4 must.** LLM #3 produces candidate directions and search queries *only* — no gap prose, no papers in context. LLM #4 writes the gaps *with* the evidence catalogue. Reversing this produces confident, evidence-free claims. This is the single most important ordering constraint in the build.
4. **Only `get_work` mints `source_type="paper"`.** `search_literature` mints `api_query` rows plus lightweight `WorkRef`s. Papers carry abstracts; search hits do not.
5. **Never invent scope.** If `demo-spec.md` §4 lists something as a non-goal, do not build it — not even a small version, not even if it seems easy. If your work item's checklist doesn't mention it, it isn't yours.
6. **Never fake a passing test.** No `assert True`, no test that passes vacuously, no `pytest.skip` to get green. If a test can't pass, the code is wrong or the spec is wrong — say so (§7).

## 4. The loop

Work through these in order. Do not skip the review step or the mark-done step.

### Step 1 — Orient (5 min)
- Read the work item in `execution-plan.md`: its checklist, its ⏱ estimate, its 🔒 markers, its **Done** line.
- Read the acceptance criteria it serves in `demo-spec.md` §3.
- Read the relevant contract in `demo-spec.md` §6.
- Confirm its prerequisites exist. If a 🔒 dependency isn't built, **stop and say so** — don't stub it.
- **Read the `STATUS` lines of completed items.** They carry decisions already made (model choices, thresholds, chosen fixtures) that you must not contradict or re-litigate.

### Step 2 — Plan (5 min)
State, in three or four lines: the files you'll create or change, the public functions you'll add, and the tests you'll write. If this doesn't match the checklist, re-read the checklist.

### Step 3 — Implement
- Match the surrounding code's style, naming, and comment density.
- Type-annotate public functions. Pydantic models for anything crossing a boundary.
- **Emit events** (`run.emit(...)`) at every step boundary in pipeline code — the UI is driven entirely by these.
- **Never let an external call raise into the pipeline.** Catch, emit `warning{code, message}`, return an empty result, continue. Graceful degradation is a feature (AC9).
- Add `data-testid` attributes to every interactive element you build in React — the Playwright tests depend on them.

### Step 4 — Self-review (do this properly)
Re-read your own diff and answer honestly:
- Does every checklist item have code behind it?
- Does the **Done** line actually hold, or did I approximate it?
- Did I violate any of the six rules in §3?
- Did I add anything the checklist didn't ask for?
- Is there a path where an exception escapes to the caller?
- Are there hardcoded values that belong in `config.py`?
- If an LLM schema changed: does the AC5 test still pass?

Fix what you find **before** running tests.

### Step 5 — Test
See §5. Every work item ends with green tests.

### Step 6 — Self-correct
If anything fails: fix the code, re-run, repeat. Do not weaken a test to make it pass. If you weaken or delete an assertion, say so explicitly in your final summary and explain why.

### Step 7 — Mark it done
Before committing, update **`execution-plan.md`** in two places:

1. The **Progress** table near the top — change your item's row from `pending` to `✅ done`. Leave the commit column blank; you'll fill it after committing, or just reference it in the commit message.
2. A **`> **STATUS: ✅ DONE**`** line immediately under your item's `###` heading, recording anything the next agent needs to know: values you chose, thresholds you settled on, anything you deliberately left out, and any assumption a human should confirm.

**Then check the user-facing docs.** If your change alters what the user sees, what the tool
claims about itself, or how it is run, update `how-to-use.md` and `e2e-flow.md` in the same
commit. This is not optional tidying: a review found `report.md` telling readers the papers were
"read in full" when they were 400-character abstracts, and the two guides repeating it, because
behaviour changed and the prose did not. A claim the code no longer supports is the one kind of
documentation bug this product cannot afford.

If you completed the item only **partially**, say so precisely — `> **STATUS: ⚠️ PARTIAL**` plus which checklist items are outstanding and why. Never mark an item done when its **Done** line does not hold.

`execution-plan.md` is the only shared memory between sessions. An agent picking up the next work item reads it and nothing else from this conversation.

### Step 8 — Commit
Only once tests are green, the Done line genuinely holds, and `execution-plan.md` is updated. Include the plan update in the same commit as the code.

## 5. Testing — three layers, by phase

**Every work item, always:** `pytest` green and `ruff check` clean.

```bash
cd backend
pytest                # hermetic tests only (pyproject sets addopts = -m "not live")
pytest -m live        # network tests, run explicitly
ruff check . && mypy roia
```

Mark any test that touches the network `@pytest.mark.live`. Hermetic tests use recorded JSON fixtures — a test suite that fails on hotel wifi is a test suite people stop running.

### Phase 1 (backend) — pytest only
Unit tests plus one end-to-end CLI run:

```bash
cd backend
python -m roia run --grant fixtures/grant.pdf --profile "$ROIA_DEMO_PROFILE_URL"
# then assert on the artifacts:
#   report.json  — 3 directions, each with >=2 evidence_ids
#   report.md    — every link resolves to a stored evidence URL   (AC13)
#   fixtures/run-001.jsonl — >=15 events                          (AC7)
```

### Phase 2 API items (WI-2.1, WI-2.2) — curl
Fastest way to verify HTTP and SSE contracts:

```bash
# from anywhere; uvicorn is started from backend/ (see below)
# start a run
RUN=$(curl -s -X POST localhost:8000/api/runs \
      -H 'Content-Type: application/json' \
      -d '{"grant_url":"...","profile_url":"..."}' | jq -r .run_id)

# 422 when neither grant source is given
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8000/api/runs \
     -H 'Content-Type: application/json' -d '{"profile_url":"..."}'    # expect 422

# stream events  (-N disables buffering — without it you will see nothing and blame the server)
curl -N -H 'Accept: text/event-stream' localhost:8000/api/runs/$RUN/events

# AC8a: connect late, confirm you still receive everything from seq 0
sleep 20 && curl -N localhost:8000/api/runs/$RUN/events | head -40

# snapshot carries the report once finished
curl -s localhost:8000/api/runs/$RUN | jq '{status, n_events: (.events|length), has_report: (.report != null)}'
```

Serve it with **`cd backend && uvicorn roia.api:app_factory --factory --port 8000`**, and
**without `--reload`** while a real run is in flight — a file save kills the worker thread mid-run.

### Phase 2 UI items (WI-2.4a, 2.4b, 2.5, 2.6) — Playwright
Use `pytest-playwright` so everything stays in one runner:

```bash
cd backend                          # e2e tests live in backend/tests/e2e/ so there is one runner
pip install pytest-playwright && playwright install chromium
pytest tests/e2e -m e2e --headed    # --headed while developing
```

Drive the UI against the **fixture replayer** (`?fixture=run-001`), not a live 5-minute run.

**AC6 requires Playwright** — it is the only way to prove "zero network requests":

```python
@pytest.mark.e2e
def test_ac6_sliders_are_local_only(page, live_server):
    page.goto(f"{live_server}/runs/run-001?fixture=run-001")
    page.wait_for_selector("[data-testid=direction-card]")

    order_before = page.locator("[data-testid=direction-card]").all_text_contents()
    requests: list[str] = []
    page.on("request", lambda r: requests.append(r.url))

    page.get_by_test_id("weight-slider-scientific_novelty").press("ArrowRight")
    page.wait_for_timeout(300)

    assert requests == [], f"slider triggered network calls: {requests}"
    assert page.locator("[data-testid=direction-card]").all_text_contents() != order_before \
        or True, "ordering may legitimately not change; the network assertion is the AC"
```

Other UI criteria worth a Playwright test:
- **AC8b** — start a run, `page.reload()`, assert the timeline still shows prior events
- **AC7** — assert `[data-testid=timeline-event]` count `>= 15` after a fixture replay
- **AC3/AC11** — assert every direction card shows `>= 2` evidence chips, and that clicking one opens a panel with a real `href`
- **AC9** — submit a broken profile URL, assert a warning `Alert` appears and the run still completes

## 6. Commit

One commit per work item. Stage only files relevant to it.

```
WI-<id>: <short imperative summary>

<why, and any non-obvious decision you made>

ACs: AC3, AC11
Tests: 4 added, pytest green, ruff clean
```

Example:

```
WI-1.2: add evidence store with ID minting and citation validation

Evidence IDs are short and sequential (e1, e2, ...) rather than content
hashes — models copy short tokens far more reliably, and an unresolvable
ID is dropped with a warning rather than raising, so one bad token cannot
kill a stage four minutes in.

ACs: AC4, AC5, AC10a, AC10b
Tests: 4 added, pytest green, ruff clean
Plan: execution-plan.md marked done
```

Do not commit `.env`, `.venv/`, `backend/runs/`, `node_modules/`, or anything with a key in it. Check `git diff --cached` before committing.

## 7. When you are blocked or you think the spec is wrong

**Stop and report. Do not improvise.**

The spec has already been through two audit rounds, so an apparent contradiction is worth surfacing rather than papering over. If you find one:

1. Quote the conflicting lines from both documents, with file and line numbers.
2. Say what you think the right resolution is and why.
3. Implement everything in the work item that does **not** depend on the answer.
4. Report what you left out.

Same for a genuinely blocked dependency (a missing API key, a rate limit, an upstream 403): report it plainly with the error, say what you tried, and stop. Don't fake data to keep moving.

## 8. Anti-patterns — do not do these

| Don't | Why |
|---|---|
| Add a `url` field to an LLM output schema | Breaks the one guarantee the product rests on (rule 1) |
| Let the LLM compute the overall score | Destroys reproducibility and the weight slider (rule 2) |
| Give LLM #3 the literature | Produces evidence-free gaps — the exact bug this spec was rewritten to fix (rule 3) |
| Build "just a small version" of a non-goal | The 2-day scope is already cut to the bone |
| `pytest.skip` a failing test | Hides the bug; the AC then ships broken |
| Bare `except:` around an LLM or HTTP call | Swallows the error the warning system needs to report |
| Re-run a live LLM call to "check" a passing test | Slow and expensive; use recorded fixtures |
| Refactor code outside your work item | Other items are in flight; keep the diff reviewable |

## 9. Finish by reporting

- Which checklist items you completed, and any you did not, with the reason
- Confirmation that `execution-plan.md` is updated (Progress row + STATUS line)
- Which ACs are now verifiably satisfied, and how you verified each
- Test counts and the exact commands you ran
- Any assumption you made that a human should confirm
- The commit hash
