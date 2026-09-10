---
description: Turn a change request into an agreed work item — understand the app, surface every conflict and risk, ask before deciding anything, then hand off to /execute-workitem
argument-hint: "<what you want changed, e.g. show the call deadline on each direction card>"
---

## The request: $ARGUMENTS

**If `$ARGUMENTS` is empty:** print the last few rows of the Progress table in
`execution-plan.md`, note that all 22 planned items are done, and ask what they want changed.
Then stop. Do not guess at a request.

---

You are turning a change request into an **agreed, written work item**. You are not writing the
code — `/execute-workitem` does that, and you call it at the end.

> **The rule that governs this whole command: nothing is decided by you alone.**
> Every conflict, every ambiguity, every risk goes to the user *before* a line of code is
> planned. If you find yourself thinking "they probably meant…", stop and ask.

## 1. What this app is

**Research Opportunity Intelligence.** A researcher gives it a grant call (URL or PDF) and their
public profile page; it returns three ranked research directions, each backed by evidence it
actually retrieved. Backend Python + FastAPI in `backend/`, React + Vite + TypeScript + MUI in
`frontend/`, Google Gemini for the model.

The product's entire value is that **the output can be trusted**. A beautifully formatted report
citing papers that do not exist is worse than no product. Most of the constraints below exist to
make fabrication structurally impossible rather than merely discouraged.

**What is built is the demo** (`demo-spec.md`, 22 work items, all done). `plan.md` describes a
larger ~15-day tool that was **not** built. If the request is already designed in `plan.md`, say
so — it may change the shape of the work considerably.

## 2. Phase 1 — Understand, before you have an opinion

Read, in this order. Do not skip to the code.

| File | What you are looking for |
|---|---|
| `demo-spec.md` | §3 the 16 acceptance criteria, §4 the **non-goals**, §5 architecture, §6 the API and data contracts |
| `execution-plan.md` | The work item that owns the area you're about to touch, and its `STATUS` line — it records decisions already taken and measured. Also **§The review pass** and **§Known and not fixed** at the end |
| `e2e-flow.md` | The run end to end, so you know which stage the request lands in |
| `how-to-use.md` | What the user is currently promised |
| `README.md` | Orientation and how to run it |
| `plan.md` | Whether the full design already answers this, and how |
| `requirements_design.md` | The original intent, if the request is about *what the output should say* |

Then read the **code that actually implements the area** — `backend/roia/pipeline.py` is the whole
run in one file and is usually the right starting point. Documents drift; code does not.

**Do not skim.** A change proposed against a misread of the current design wastes the user's time
in the most annoying possible way: it looks reasonable right up until it is implemented.

## 3. Phase 2 — Assess: what could this break?

Work through every row. Most will be "no". The ones that are "yes" are what you take to the user.

### The six rules — a request that breaks one needs an explicit decision, not a workaround

1. **Python mints evidence; the LLM only cites IDs.** No LLM output schema may declare `url`,
   `source_title` or `link` — `LLMOutput.__pydantic_init_subclass__` raises at class-definition
   time. And no LLM-authored *string* may contain a URL: `strip_urls` removes them and warns.
   **Does this request need the model to produce a source?** If so it conflicts with AC5/AC13 and
   the answer is almost certainly to mint an evidence row in Python instead.
2. **Ranking is arithmetic, never a model.** `compute_ranking()` is pure Python and is mirrored
   **operation for operation** in `frontend/src/ranking.ts` so the weight sliders recompute in the
   browser with no network call (AC6). **Any change to the arithmetic must change both files in
   the same commit** — they diverged once and the card showed 5.63 above a `report.json` saying
   5.62. A sweep test in `backend/tests/test_report.py` fails if they drift.
3. **LLM #3 must not see the literature; LLM #4 must.** Call #3 proposes directions and search
   queries only. Call #4 writes the gaps with the evidence catalogue in front of it. Reversing
   this produces confident, evidence-free claims — the exact bug the spec was rewritten to fix.
4. **Only `get_work` mints `source_type="paper"`.** `search_literature` mints `api_query` rows.
5. **Never invent scope.** If `demo-spec.md` §4 lists it as a non-goal, building "a small version"
   is still building it. Say so and let the user decide.
6. **Never fake a passing test.** No vacuous assertion, no `pytest.skip` to get green.

### Blast radius — which of these does the request touch?

| If it touches… | Then it also touches… |
|---|---|
| An API route or response shape (`demo-spec.md` §6.2) | `frontend/src/api.ts`, `types.ts`, and the tests in `backend/tests/test_api.py` |
| The `Report` model (`backend/roia/report.py`) | `frontend/src/types.ts`, the golden `backend/fixtures/report-sample.json`, `test_report.py`, and the browser tests |
| The ranking arithmetic | **Both** `ranking.py` and `ranking.ts`, plus the sweep test and the browser-agreement test |
| An LLM prompt or output schema | The **recorded fixtures** in `backend/fixtures/llm/`. Re-recording costs a real Pro call (~100 s, real money) and invalidates the golden report values built on it — flag this as a cost before agreeing |
| A new `warning{code}` | `HUMAN` in `frontend/src/Warnings.tsx`. A test fails if a code has no human sentence |
| Evidence minting or provenance | AC4's per-`source_type` rules in `backend/roia/evidence.py`, which are enforced, not trusted |
| Anything in the run's hot path | **AC1: the whole run must finish inside 360 s.** Real runs are 112–158 s; the assessment call alone has been measured at up to 411 s at the wrong thinking level |
| The pre-flight probe | **AC14: under 20 s**, and it is already ~17.5 s. There is very little headroom |
| The SPA or its routes | The `?fixture=run-001` replay path, which is the demo-day fallback and must keep working with no keys |

### Also ask yourself

- **Does it contradict a `STATUS` line?** Those record measurements and decisions. Re-litigating
  one without new evidence is how a build goes backwards.
- **Does it conflict with something already listed in §Known and not fixed?** If so the request
  may be *fixing* a known limitation — good, say so.
- **Does it make the report claim more than it retrieved?** The most important question in this
  file. `report.md` once said the papers were "read in full" when they were 400-character
  abstracts. If the request makes any such claim, it needs rewording before it needs code.
- **Is it a UI change?** Then it needs `data-testid` attributes, or the Playwright tests cannot
  reach it.

## 4. Phase 3 — Report and ask. **This is a hard stop.**

Write, in this order:

1. **What I understand you want** — one paragraph, in your own words. If this is wrong, everything
   after it is wrong, so make it easy to correct.
2. **How it fits the app today** — which stage, which files, what currently happens there.
3. **Conflicts** — every rule, non-goal, acceptance criterion or recorded decision it runs into.
   Quote the file and line. For each: what the conflict is, and what the options are.
4. **Risks and side effects** — what could break, what gets slower, what has to change in
   sympathy, what it costs (a re-recorded fixture is real money and real time).
5. **Open questions** — everything you would otherwise have to assume.
6. **What I'd suggest, and why** — you are expected to have a recommendation. Give it plainly,
   with the trade-off stated. A recommendation is not a decision.

Then **ask**, using `AskUserQuestion` for the choices that change what gets built. Put your
recommendation first and mark it *(Recommended)*.

**Do not continue past this point until the user has answered.** Not "I'll proceed with the
obvious reading" — the obvious reading is exactly what this gate exists to catch. If they answer
some questions and not others, ask again about the rest.

If there are genuinely **no** conflicts, no risks and nothing ambiguous — a copy change, a colour,
a label — say so in two lines and confirm you have it right. Still confirm. Never skip the gate;
just make it short when it deserves to be short.

## 5. Phase 4 — Write the work item

Only after the user has confirmed. Add it to `execution-plan.md` in **two** places, matching the
shape of every item already there.

**The id:** the planned build used `WI-0.x`, `WI-1.x`, `WI-2.x` and is finished. Post-plan work
continues at **`WI-3.0`**, then `WI-3.1`, and so on. Check the file for the highest `WI-3.x` and
take the next.

**1. A row in the Progress table** near the top:

```
| 3.0 <short name> | pending | — |
```

**2. The item itself**, appended in a `## Phase 3 — After the plan` section (create it once, after
Phase 2), in the house format:

```markdown
### WI-3.0 — <short imperative name> ⏱<estimate> 🔒<what it affects, if anything>

> **Requested:** "<the user's request, quoted>"
>
> **Agreed:** <what was decided at the Phase 3 gate, including which option the user chose and
> anything they explicitly ruled out. This is the record of the conversation — the agent that
> implements it sees this and nothing else from that discussion.>
>
> **Conflicts resolved:** <each conflict from Phase 3 and how the user settled it. If a rule or a
> non-goal is being deliberately relaxed, say so here in as many words.>
>
> **Risks accepted:** <what the user agreed to live with.>

- [ ] <one concrete, checkable step>
- [ ] <another>
- [ ] <the tests that must exist — name the invariant each one protects>
- **Done:** <a single sentence that is unambiguously true or false when the item is complete>

**ACs:** <the acceptance criteria this serves or must not break>
```

**The `Done` line is the contract.** Write it so that "is this done?" has one answer. "Improve the
report" is not a Done line; "the call deadline appears on every direction card and a browser test
asserts it" is.

## 6. Phase 5 — Hand off

Tell the user the item is written, then invoke:

```
/execute-workitem 3.0
```

That command implements exactly that one item end to end — implement, self-review, test,
self-correct, mark done, commit. **You do not write the code yourself.** The separation is the
point: this command is where thinking and agreement happen, that one is where the change happens,
and the work item in between is the written record of what was agreed.

If the user would rather review the work item before it is built, stop after Phase 4 and say the
command they can run when ready.

## 7. Do not

| Don't | Why |
|---|---|
| Start editing code | This command produces an agreed work item, not a diff |
| Assume what an ambiguous request meant | The Phase 3 gate exists precisely for this |
| Skip the gate because the change "looks small" | The rounding bug that made the browser disagree with the backend was a one-line change |
| Bury a conflict in a list of caveats | If it changes what gets built, it goes in `AskUserQuestion` |
| Relax one of the six rules quietly | If a rule is being broken, that is the headline of your Phase 3 report |
| Build a `demo-spec.md` §4 non-goal because it "seems easy" | Say it is a non-goal and let the user choose |
| Promise the full `plan.md` behaviour | The demo is a cut-down version; be clear which one you are proposing to build |
| Write a vague `Done` line | The implementing agent will decide for itself what done means |

## 8. Finish by reporting

- The work item id and where it now lives in `execution-plan.md`
- What was agreed at the gate, and anything the user ruled out
- Any conflict that was resolved by relaxing a rule — call this out plainly, it matters
- Whether you handed off to `/execute-workitem` or stopped for review
