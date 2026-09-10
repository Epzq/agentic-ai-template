# Demo Spec — Research Opportunity Intelligence (2-day vertical slice)

**Goal:** a working, watchable, honest end-to-end run in 2 days.
**Relationship to other docs:** `requirements_design.md` is the product requirement. `plan.md` is the ~15-day production design. **This document is the 2-day subset**, and it deliberately builds *less* than `plan.md`. Where the two disagree, this document wins until the demo ships.

> **Revision 2** — corrected after a full cross-audit against `requirements_design.md` and `plan.md`. Changes: the direction-generation hole is closed (§5), papers are actually read (§5 step 7b), author works are actually fetched (§5 step 2b), AC4/AC10 restated to match the contract they test (§3), two new ACs force real literature evidence, and the hour budget is honest (§7).

> **SDD note.** Feeding `plan.md` to an implement loop produces the 15-day product. This file exists so the implement phase has a scope it cannot wander out of. §3 (acceptance criteria) and §4 (non-goals) are the contract.

---

## 1. The one-sentence deliverable

> Paste a grant call and a researcher's page, watch the system read real sources for ~4 minutes, and get 3 ranked research directions where **every citation comes from a page the system downloaded or a database record it retrieved** — never from the AI — and **the ranking re-orders live as you move the weight sliders**.

## 2. What the demo must prove

Three claims. Everything else is scaffolding.

| # | Claim | How the demo shows it |
|---|---|---|
| **C1** | *It is not a chatbot guessing.* | Live activity timeline: "searching OpenAlex…", "pulling record for Chen et al. 2025…", "12 citing papers since 2023". Sources counter climbing. |
| **C2** | *It cannot fabricate sources.* | Every citation chip resolves to a record Python minted at retrieval time. The LLM's output schema has **no URL field**. |
| **C3** | *The ranking is transparent, not a vibe.* | Nine per-criterion scores visible; weight sliders re-rank instantly, in-browser, with no API call. |

If a viewer leaves remembering only "the citations are real and the sliders work," the demo succeeded.

---

## 3. Acceptance criteria

Testable. Each is pass/fail.

| ID | Criterion |
|---|---|
| **AC1** | Given a grant PDF (uploaded) or URL, plus a researcher profile URL, pressing **Run** produces a rendered report in **≤ 6 minutes** |
| **AC2** | The report contains **exactly 3** ranked directions, each with a problem statement and an evidence-backed gap |
| **AC3** | Every direction cites **≥ 2 evidence IDs**, and every ID in the final report resolves to a stored record |
| **AC4** | Every evidence record carries `retrieved_at` **and** provenance appropriate to its type:<br>• `webpage` → non-null `url` + `http_status == 200`<br>• `grant_doc` → non-null `page` + the document's `sha256`<br>• `api_query` → the full request URL + the status returned<br>• `paper` → non-null `derived_from` pointing at an `api_query` record that itself has a logged 200<br>**No record carries a URL the system did not either fetch or receive inside a fetched API response.** |
| **AC5** | **No LLM output schema in the codebase contains a `url` or `source_title` field.** Enforced by a unit test that walks the Pydantic models |
| **AC6** | Moving any weight slider re-orders the directions in **< 100 ms with zero network requests** (verify in devtools Network tab) |
| **AC7** | The activity timeline streams **≥ 15 events** during a run and remains visible after completion |
| **AC8a** | The server replays all prior events to a newly-opened event stream |
| **AC8b** | Refreshing the browser mid-run reconnects to the same run and restores the timeline (the run id is in the URL) |
| **AC9** | If the profile URL is unreachable, the run **completes with a visible warning** rather than crashing |
| **AC10a** | Unit test: an LLM output citing an unknown evidence ID has that ID **removed** and emits `warning{code: unresolvable_evidence_id}` |
| **AC10b** | Unit test: if dropping IDs leaves a direction below 2 resolvable IDs, the call is retried once, then the direction is flagged `thin_evidence` in the UI |
| **AC11** | Each direction cites **≥ 1 record with `source_type == "paper"`** and **≥ 1 with `source_type == "grant_doc"`**; the run's store holds **≥ 12 distinct `paper` records** |
| **AC12** | `topic_trend` and `citing_count` produced a numeric result for every direction, and each gap statement cites the evidence ID of that result |
| **AC13** | Every link in `report.md` resolves to a stored evidence record's URL; no URL in the file originated from an LLM response |
| **AC14** | `POST /api/probe` on the CRP URL returns **≥1 question**, detecting both call periods, in **< 20 s with zero LLM calls**; the chosen answer appears in the grant brief and the run never blocks for input |

> **AC11 exists because without it, every other AC is satisfiable by a run that fetched zero papers.** Two quotes from the grant PDF would satisfy AC3.

---

## 4. Non-goals — explicitly NOT in the 2-day build

Listed so the implement phase cannot drift into them. All are specified in `plan.md` for the real build.

- ❌ Author identity **disambiguation** (candidate margin, ORCID/DBLP cross-check, the tripwire) — the demo resolves an author and **labels it "unverified" in the UI**
- ❌ The 4-signal `verify_gap` — do **two** signals: citing-count since the seed year, and the topic year-curve
- ❌ Reading paper **full text** — the demo reads OpenAlex abstracts only (§5 step 7b), never `arxiv.org/html` or Europe PMC
- ❌ Entailment gate (claim-vs-quote checking)
- ❌ Competitor & collaborator stage — `competitive_differentiation` and `collaboration_potential` are scored `null` and rendered as "not assessed"
- ❌ Fuzzy quote matching — exact substring only, log failures, never drop
- ❌ Tool-call cache, run history, PDF/DOCX export, auth
- ❌ Playwright / `r.jina.ai` escalation — if a plain fetch fails, report it (AC9)
- ❌ SQLite — in-memory + JSONL on disk
- ❌ Token-level streaming of model reasoning — tool events only

---

## 5. Demo architecture

**Key simplification: there is no tool-calling loop.** Four structured LLM calls with Python-owned control flow.

```
POST /api/runs
  │
  ├─ 1.  Python  ingest_grant(src)  = ingest_source(src, GRANT)         → e1..
  │              (+ follows up to 2 linked call documents — see below)
  ├─ 2.  Python  ingest_profile(url) = ingest_source(url, PROFILE)       → e..
  ├─ 2b. Python  extract_identity(profile page) -> (name, domain)   [deterministic]
  │              resolve_author(name, domain)
  │              → top OpenAlex author  +  fetch_author_works(limit 40) → e..
  │
  ├─ 3.  LLM #1  grant pages         → GrantBrief    (requirements, criteria, quotes)
  ├─ 4.  LLM #2  profile + works     → Capabilities  (expertise, methods, domains)
  ├─ 5.  LLM #3  brief × caps        → 3 CANDIDATE directions + 3 queries each
  │                                     (titles + rationale ONLY — no gap text yet)
  │
  ├─ 6.  Python  run every query on OpenAlex      → WorkRefs            → e..
  ├─ 7a. Python  topic_trend + citing_count per direction               → e..
  ├─ 7b. Python  get_work on the top ~4 most-cited works per direction
  │              → source_type="paper" rows carrying the abstract       → e..
  │
  ├─ 8.  LLM #4  candidates + evidence catalogue →
  │              per direction: evidence_backed_gap, 9 scores (ordinal),
  │              narrative fields, evidence_ids                    ← sees the evidence
  │
  ├─ 9.  Python  compute_ranking(scores, weights)                  ← no LLM
  └─ 10. Python  render report.md from a Jinja template            ← no LLM
```

### Ingestion is one self-detecting function

> `ingest_grant(src)` and `ingest_profile(url)` are **thin named wrappers** over the single
> `ingest_source(src, policy)` below — readable call sites, one implementation, one place to fix bugs.

The user pastes a URL or uploads a file and should never have to say what it is. `ingest_source()`
handles both inputs and every artefact it reaches, dispatching on **`Content-Type`, never on file
extension** — the CRP page's document links end `…​.pdf?download=`, so extension matching finds
**zero PDFs on a page that has seven**.

```
ingest_source(url_or_path, policy) -> DocumentSet
  │
  ├─ Content-Type: text/html  ─────────────────────────────────────────────
  │     L1  trafilatura over lxml.make_links_absolute(html)
  │     L2  embedded framework payload (see registry below)
  │     L3  harvest links from BOTH the DOM and the L2 payload,
  │         then recurse — depth 1 only
  │     if L1+L2 < 600 chars or text/html ratio < 1%  -> warning{thin_extraction}
  │
  ├─ application/pdf  ──> pymupdf4llm page_chunks; one evidence row per page,
  │                        page = md.get("page_number") or md.get("page")
  ├─ application/zip  ──> unzip in memory, recurse into each .pdf inside
  └─ anything else    ──> skip + warning{unsupported_type}
```

**L2 — embedded payload registry.** Modern sites put real content in a JSON blob rather than the
DOM. Recovering it is *parsing*, not *rendering*, so it does not need a browser and does not
violate the no-Playwright non-goal.

| Framework | Marker | Status |
|---|---|---|
| Next.js App Router | `self.__next_f.push([1,"…"])` → `"wysiwyg"` blocks | **verified** on rgp.gov.sg — recovers the grant-call dates that trafilatura cannot see |
| Next.js Pages Router | `<script id="__NEXT_DATA__">` | add if a target needs it |
| Nuxt | `window.__NUXT__` | add if a target needs it |
| Generic | `<script type="application/ld+json">` | cheap, worth always trying |

**Policy is the only thing that differs between the two inputs:**

| | grant | profile |
|---|---|---|
| follow links | document links (pdf/zip/docx), ZIPs ranked first | same-site pages matching `/publication\|research\|people/` |
| max artefacts | 6 | 2 |
| unzip | yes | no |
| depth | 1 | 1 |

⚠️ **Ranking links by keyword only works when URLs are readable.** On rgp.gov.sg every href is an
opaque UUID, so text-based ranking scores nothing — rank by **type** (zip → pdf → other) first.

⚠️ **No single source is complete.** On the CRP call the dates are page-only and the objectives,
eligibility, evaluation criteria, budget and duration are PDF-only. The grant brief must merge every
layer, not stop at the first that returns something.

`backend/spikes/probe_grant_url.py` implements L1–L3 end to end and is the reference for WI-1.4.

### Pre-flight clarification (Tier 1)

Ambiguity in the *inputs* is resolved **before the run starts**, never during it.

```
Step 1  [ grant URL ] [ profile URL ]            -> POST /api/probe
          |
          v  ~18s measured, fully deterministic, ZERO LLM calls
Step 2  "We found 2 calls on this page:"
          (o) Frontier CRP   23 Mar - 18 May 2026
          ( ) CRP36          14 Sep -  9 Nov 2026
          ( ) Not sure - analyse the whole programme
        [ Start run ]                            -> POST /api/runs {..., answers}
          |
          v  the 6-minute run, which NEVER blocks
Report
```

**Why not mid-run questions.** A run that suspends on an in-process `asyncio` task dies to a closed
tab, a sleeping laptop, or one file save under `--reload`, and its resume path is exercised only by a
full-length run — so it is the least-tested code in the repo, failing exactly when it matters. Asking
before the run costs nothing because nothing is running yet. Ambiguity discovered *during* a run uses
Tier 2 instead: proceed on the best guess and render it as a correctable banner (the identity case).

**Detectors are deterministic Python rules, never "LLM, what are you unsure about?"** — that
generates unbounded questions and cannot be tested. Each rule has a fixed question, fixed options,
and a defined default if skipped.

| Detector | Fires when | Question | Default if skipped |
|---|---|---|---|
| `multiple_call_periods` | >1 `…Grant Call Period:` match | which call? | analyse whole programme |
| `multiple_schemes` | >1 scheme acronym named | which scheme? | all schemes |
| `thin_profile` | profile L1+L2 < 600 chars | paste a better URL? | continue, `applicant_confidence=low` |
| `no_eligibility_found` | no doc mentions eligibility | upload the call PDF? | continue, mark `not_specified` |

⚠️ **Never ask what retrieval can answer.** *"Which of these 7 PDFs is the call document?"* is the
tool offloading its job — those PDFs are free to fetch, so it reads them. Only ask what genuinely
lives in the user's head: which call they are applying to, and whether we found the right person.

The probe result is cached on the run, so answers are recorded as evidence-bearing inputs rather
than as an invisible side channel.

**Three corrections from revision 1, all load-bearing:**

1. **Step 5 produces candidates only.** In revision 1 the directions *and their gaps* were authored with zero literature in context, which made AC2's "evidence-backed gap" a fiction. Gap prose is now written at step 8, with the evidence catalogue in context.
2. **Step 2b exists.** Revision 1's `LLM #2  profile + works` referenced `works` that nothing ever fetched.
3. **Step 7b exists.** Revision 1 never read anything about a paper beyond its title and year. `get_work` singleton lookups are **free and uncapped** on OpenAlex, so ~12 of them (4 per direction × 3) cost nothing and are what make AC11's ≥ 12 `paper` rows honest. ⚠️ `search_literature` mints `source_type="api_query"` + lightweight `WorkRef`s — **only `get_work` mints `source_type="paper"`**, because only it carries an abstract.

**Why no tool loop:** it removes `thought_signature` round-tripping, `TOO_MANY_TOOL_CALLS`, and `request_limit` tuning — the three things most likely to eat a day. Control flow is a plain function, so every step emits an event trivially.

**Upgrade path (day 3+):** add the tool loop to the gap stage first, and only there.

### Stack

| | Choice |
|---|---|
| Python | **3.12 exactly** — `python3.12 -m venv .venv`. (Verified: `pymupdf4llm` 0.3.4 + `pymupdf` 1.28.2 *do* install and work on 3.14, but pin 3.12 so the whole dependency set is on a supported line.) |
| Backend | FastAPI, `sse-starlette`, raw `google-genai` (no LangChain) |
| Ingest | `httpx` + `lxml` (`make_links_absolute`) + `trafilatura`; `pymupdf4llm` **1.28.2** (pulls `pymupdf-layout`) |
| Scholarly | OpenAlex via `pyalex` — **free API key required, get it first** |
| Store | In-memory dicts + a JSONL event log and a JSON report per run |
| Frontend | Vite + React 19 + TypeScript + MUI; `react-markdown`; **score matrix = hand-rolled CSS grid** |
| Models | Flash-class for calls 1–3; Pro-class for call 4 |

> ⚠️ **`@mui/x-charts` Heatmap is a paid Pro component** (verified on mui.com — Pro-plan badge). The demo's matrix is **3 directions × 9 criteria = 27 cells** (two columns render "not assessed" per §6.4): a CSS grid of `<Box>`s with a single-hue `backgroundColor` scale and a `Tooltip` per cell. ~40 lines, no dependency, no licence.

### Reuse from `agentic-ai-template-main`

| Take | Reason |
|---|---|
| `config.py` — pydantic-settings pattern | Clean; adopt as-is |
| `documents.py` — file loader | Starting point; **swap `pypdf` → `pymupdf4llm`** for page numbers (AC4) |
| `backend/tests/` layout, ruff/mypy, CI | Free quality floor |

| Leave | Reason |
|---|---|
| `ask_gemini()` as the research layer | Returns prose with model-authored URLs — violates **C2/AC5** directly |
| `GrantFitReport` | One direction, no gaps, `match_pct` is a single LLM number |
| LangChain / LangGraph | Can't run on a Google key without an extra package; event emission is trivial hand-rolled |

---

## 6. Contracts

### 6.1 Evidence (Python mints, LLM cites)

```python
class Evidence(BaseModel):
    id: str                  # "e17" — short + sequential (models copy these reliably)
    source_type: Literal["grant_doc", "webpage", "paper", "api_query"]
    url: str | None
    title: str
    authors: list[str] = []
    year: int | None
    page: int | None          # grant_doc
    sha256: str | None        # grant_doc
    quote: str | None
    summary: str              # <=400 chars, shown in the chip hover
    derived_from: str | None  # paper -> the api_query row it came from
    http_status: int | None
    retrieved_at: datetime
```

**Rule (AC5): no LLM output model has a `url` or `source_title` field.** The model receives a numbered catalogue and returns IDs.

**Unresolvable IDs (AC10a/AC10b):** a `mode="after"` validator **drops** the ID and emits `warning{code: unresolvable_evidence_id}`. Python then re-checks the per-direction floor; below 2, retry the call once, then flag the direction `thin_evidence`.

### 6.2 Endpoints

```
POST /api/uploads           multipart, size+MIME capped  → {upload_id, sha256}
POST /api/probe             {grant_url? | grant_upload_id?, profile_url}
                            → {probe_id, questions[], detected{}}   ~18s, no LLM
POST /api/runs              {grant_url? | grant_upload_id?, profile_url, probe_id?, answers?}
                            → {run_id}; 422 if neither grant source is present
GET  /api/runs/{id}                                       → snapshot JSON
GET  /api/runs/{id}/events                                → text/event-stream
GET  /api/runs/{id}/report.md                             → markdown (Jinja, no LLM)
```

**The frontend pushes `/runs/{id}` into history on start** and rehydrates from the snapshot + event stream on mount. Without this, AC8b fails before replay is ever reached.

### 6.3 Events

```
run.started        {inputs}
stage.started      {stage}
stage.finished     {stage, ms}
tool.started       {tool, args_summary}
tool.finished      {tool, ms, summary, evidence_added:[ids]}
evidence.added     {id, source_type, title, url}
identity.resolved  {author_id, display_name, institution, confidence:"unverified"}
warning            {code, message}        ← AC9, AC10a surface here
run.finished       {}
run.failed         {code, message}
```

Every event carries a monotonic `seq`. Replay + subscribe happen under one lock:

```python
async with run.lock:
    for ev in run.events:
        q.put_nowait(ev)      # AC8a
    run.subs.add(q)
```

`run.emit()` is built on **Day 1** as a plain list-append + JSONL writer, so the Day-1 CLI produces `backend/fixtures/run-001.jsonl` for free. Day 2 only wires that list to SSE.

### 6.4 Ranking (pure Python — no LLM)

```python
CRITERIA = ["grant_alignment", "scientific_novelty", "importance", "applicant_fit",
            "feasibility", "competitive_differentiation", "collaboration_potential",
            "impact_potential", "evidence_strength"]

overall = sum(w[c] * scores[c].value for c in CRITERIA if scores[c] is not None)
```

- **Flat default weights** in the demo (grant-derived weights are `plan.md` §7.3).
- `competitive_differentiation` and `collaboration_potential` are `None` (non-goal §4) — excluded from the sum and rendered "not assessed". Weights renormalise over the scored seven.
- Each score is `{value, provenance: "judged", evidence_ids, rationale}` — never a bare float, so a heatmap cell can click through to its chips.
- Scores + weights ship to the browser as JSON; the slider recomputes with the identical formula (AC6).

---

## 7. Task breakdown

**Honest budget: ~16 hours — two long days, or three comfortable ones.** Revision 1 claimed 14 h for materially more work; that was wrong.

### Day 0 — 90 min, before any code

One real call per load-bearing assumption, **printing raw responses**. ✅ **All six done** — implemented as `backend/spikes/check_demo_pair.py` (3) and `backend/spikes/probe_grant_url.py` (5, 6); 1, 2 and 4 verified ad hoc and recorded in `execution-plan.md` WI-0.2:

1. OpenAlex search + `group_by=publication_year` + `awards.*` filter name — **needs the free API key**
2. OpenAlex `filter=cites:{W},from_publication_date:{d}` composite, and a free singleton `get_work`
3. `resolve_author`: ROR `?query.advanced=domains:"{your demo domain}"`, then OpenAlex `/authors?filter=display_name.search:{name}&sort=works_count:desc` — **assert the top-ranked candidate is the right person.** ⚠️ Do **not** filter on `last_known_institutions.ror`: verified live, that filter excluded a 417-work researcher whose canonical record has no institution and returned only 1–2-work stub duplicates. Already implemented in `backend/spikes/check_demo_pair.py` — just run it.
4. A Gemini structured-output call with `response_json_schema`
5. `pymupdf4llm.to_markdown(pdf, page_chunks=True)` → **print `sorted(chunk['metadata'].keys())`** and record the real key
6. `trafilatura` + `make_links_absolute` on a real lab page → confirm relative hrefs resolve

> Items 3 and 5 are already verified: ROR plain `query=` returns **0** for a domain while `query.advanced=domains:` returns 1 and yields the full `https://ror.org/…` form that OpenAlex's filter requires; and the `page_chunks` metadata key **is `page`** (1-indexed), with no `page_number` key. Re-run them anyway — they cost 2 minutes and they are the two that fail *silently*.

### Day 1 — backend (~8 h)

| h | Task | Done when |
|---|---|---|
| 1.0 | Skeleton, `config.py`, `.env`, **evidence store**, `run.emit()` + JSONL writer | `pytest` green; AC5 + AC10a tests pass |
| 1.5 | `ingest_source` — Content-Type dispatch + HTML layers L1–L3 + ZIP recursion (see §5) | The CRP URL yields the landing page, the Next.js flight text **with the call dates**, and 7 PDFs incl. `F-CRP Call Information Sheet (2026).pdf` |
| 1.0 | `extract_identity(html,url) -> (name, domain)` + `ingest_profile` — seed page + up to 2 links matching `/publication\|/research\|/people` | Returns text, absolute links, and a `(name, domain)` pair from a fixture page |
| 1.5 | OpenAlex client: `resolve_author` (rank, don't filter — see `backend/spikes/check_demo_pair.py`), `fetch_author_works`, `search_literature`, `get_work`, `topic_trend`, `citing_count` | Every result mints evidence with `derived_from` (AC4, AC11) |
| 2.5 | The 4 LLM calls + Pydantic schemas + evidence-catalogue serialisation + anchored rubrics | Schemas validate; scores spread across the 0–10 range |
| 0.5 | `compute_ranking` + `report.md` Jinja template | CLI writes `report.json`, `report.md`, `backend/fixtures/run-001.jsonl` (AC2, AC13) |

### Day 2 — API + frontend (~8 h)

| h | Task | Done when |
|---|---|---|
| 1.0 | FastAPI, run registry, `POST /api/uploads`, `POST /api/runs`, snapshot | 422 on a missing grant source |
| 1.5 | SSE + locked replay + run id in the URL | AC7, AC8a, AC8b pass |
| 0.5 | `?fixture=1` replayer with a speed multiplier | Frontend unblocked from the Day-1 JSONL |
| 1.5 | React + MUI shell, input form, **live activity timeline** | Timeline streams during a real run |
| 3.0 | Report view: 3 direction cards, **CSS-grid score matrix**, evidence chips, weight sliders, "unverified researcher" banner | AC2, AC3, AC6, AC11 pass |
| 0.5 | Warning surfacing + a full AC walk-through | AC9 passes; every AC checked off |

**If you fall behind, cut in this order** (mirrors `execution-plan.md`): score matrix → plain per-criterion list · PDF upload → URL-only grant input · `report.md` export · `ingest_profile`'s extra links → seed page only · timeline richness → flat event list. **Never cut:** the evidence store, AC5's test, the weight sliders, the hand-authored report fixture, or the fixture replayer — the last two are what save you if Day 1 runs long.

---

## 8. Demo-day protocol

1. **Do a real cold run beforehand.** Timings shown must be honest.
2. **Keep that run's JSONL + report JSON as the fixture.** `?fixture=1` replays it — the fallback if wifi or a rate limit bites.
3. **Pick the grant and researcher deliberately:** a call with a real PDF, and a researcher with ≥20 OpenAlex-indexed works in a field with live literature. A thin profile makes the system look weak when it is being honest.
4. **Show one failure on purpose** — a bad profile URL producing a clean warning (AC9).
5. **Say what is stubbed:** identity is unverified, gap verification is 2 signals not 4, papers are read as abstracts not full text, and there is no competitor analysis. Claiming otherwise invites the one question you cannot answer.

---

## 9. Decisions deferred to after the demo

| # | Decision | Notes |
|---|---|---|
| 1 | LangChain or hand-rolled loop | Demo hand-rolls. Revisit only if provider-swapping becomes real |
| 2 | Where the first tool-loop goes | The gap stage, and nowhere else at first |
| 3 | SQLite vs in-memory | Needed once run history or resume matters |
| 4 | Confirm Gemini model IDs + pricing in AI Studio | `plan.md` §3 figures are research-derived |
| 5 | Is the target funder Singaporean? | No public NRF/A\*STAR award API — route via OpenAlex funder IDs |

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| OpenAlex anonymous limit (~100 list calls/**day**) exhausts in one run | **Get the free key on day 0.** Blocking. |
| The 3 candidate directions are unusable on a niche field | Choose the demo pair deliberately (§8.3); `search_literature` returning < 5 works per direction emits a warning |
| Frontend dev blocked on 5-min backend runs | Day-1 JSONL fixture + Day-2 replayer, before the report view |
| Scores compress (everything 6–8) so sliders look inert | Anchored rubrics in LLM #4; **verify the spread before building the sliders** |
| SSE arrives in one lump in dev | Vite proxy buffering — point `EventSource` straight at `:8000` with CORS in dev |
| Two concurrent runs collide | Run registry is keyed by `run_id`; the demo does not need more, but do not use module-level mutable state |
