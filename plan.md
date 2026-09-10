# Research Opportunity Intelligence Agent — Implementation Plan

**Status:** Draft for discussion
**Supersedes:** the architecture sections of `requirements_design.md` (§5, §7–§12, §14, §15, §22). The *requirements* in that document (scope, output fields, evidence rules, ranking criteria, non-goals) still stand and are the contract this plan implements.

---

## 1. What changed, and why

`requirements_design.md` describes six "agents". They are not agents. An agent is a thing that *decides*. These six have a fixed dependency order, never negotiate, and cannot reject each other's output — §14.2 of the spec admits this outright ("the dependency graph is deterministic"). It is a five-node pipeline with six prompt files, and the "Coordinator" is a `for` loop with a state dict.

Three changes follow.

| # | Change | Why |
|---|---|---|
| 1 | **One agent definition, six bounded runs, one evidence store** | Six LLM personalities cost six system prompts, six re-statements of the evidence discipline, and a lossy re-summarisation at every hop. Every inter-agent handoff is a chance to paraphrase a citation into something it no longer supports. |
| 2 | **Deterministic macro-flow; LLM autonomy only inside a stage** | Which stage runs next has a known answer. Which paper to read next, whether to widen the year window, whether the search returned enough — those genuinely depend on what came back. |
| 3 | **Web UI, not CLI** | The two highest-value corrections in this system (confirm the researcher's identity; adjust ranking weights) are one click each in a browser and impossible in a batch CLI. |

### 1.1 The "one agent, many tools" question, answered

**Right:** collapse the six agents. One `Agent` definition, one tool registry, one evidence store, one prompt surface. Within a stage, let the model pick tools freely.

**Wrong, in three specific ways:**

1. **"One agent" must not mean one unbounded `run()` over the whole job.** A full run is 40–70 tool calls. Long before the end the model starts summarising its own earlier tool results, and the moment it does, claim text is a paraphrase of a paraphrase — the citation still resolves but no longer supports the sentence. Fix: **six bounded runs** (grant, applicant, gaps, competition, scoring, narrative), each with a typed output and a request limit, each under ~60k tokens.
2. **Not all ~25 tools visible at once.** Google's own function-calling doc caps the recommended active set at 10–20; chance-corrected measurement (arXiv 2605.24660) shows selection accuracy *improving* when the candidate list is shortened (76.8% vs 60.9% on medium-difficulty queries). Fix: **stage-scoped toolsets** of 4–8, via `allowed_function_names`.
3. **"Each tool uses an LLM" is right for compression, wrong as a default.** LLM-in-tool is correct for turning a 40-page PDF into structured requirements. It is wrong for anything reproducible — above all the ranking, which §12 defines as a weighted sum with sensitivity analysis. That is arithmetic. If an LLM does the multiplication you lose reproducibility, you cannot honestly expose the weights, and you cannot offer the weight slider.

**The resulting shape:**

```
Python owns:  the stage order, all retrieval, all arithmetic, all IDs, all numbers
LLM owns:     which tool to call next inside a stage, extraction, and judgement
```

---

## 2. High-level architecture

```
┌───────────────────────────────────────────────────────────────────────┐
│  BROWSER — React 19 + Vite + MUI                                      │
│  Input form → live run timeline (SSE) → report + evidence + weights   │
└────────────────────────────┬──────────────────────────────────────────┘
                             │  POST /api/runs · GET /api/runs/{id}
                             │  GET /api/runs/{id}/events   (SSE)
┌────────────────────────────▼──────────────────────────────────────────┐
│  FastAPI (single uvicorn process, serves the built SPA at same origin)│
│                                                                        │
│   run_pipeline()  ── plain async Python, 5 awaits ──────────────┐     │
│                                                                  │     │
│   ┌──────────────┐  ┌──────────────┐                            │     │
│   │ E1 GRANT     │  │ E2 APPLICANT │   asyncio.gather            │     │
│   └──────┬───────┘  └──────┬───────┘                            │     │
│          └────────┬────────┘                                     │     │
│              ┌────▼──────────┐                                   │     │
│              │ E3 GAPS       │                                   │     │
│              └────┬──────────┘                                   │     │
│              ┌────▼──────────┐                                   │     │
│              │ E4 COMPETITION│                                   │     │
│              └────┬──────────┘                                   │     │
│              ┌────▼──────────┐                                   │     │
│              │ E5 SCORING    │  Pro, no tools                    │     │
│              └────┬──────────┘                                   │     │
│              ┌────▼──────────────────────┐                       │     │
│              │ RANK  (pure Python)       │  ← no LLM             │     │
│              └────┬──────────────────────┘                       │     │
│              ┌────▼──────────┐                                   │     │
│              │ E6 NARRATIVE  │                                   │     │
│              └───────────────┘                                   │     │
│                                                                  │     │
│   ONE Agent definition ──────────────────────────────────────────┘     │
│   (system prompt + tool registry + hand-rolled google-genai loop)      │
│   per episode: different instructions · toolset · output schema        │
│                                                                        │
│   EVIDENCE STORE (Python-owned)   TOOL CACHE   EVENT LOG                │
└────────────────────────┬───────────────────────────────────────────────┘
                         │
        OpenAlex · ROR · Crossref · arXiv · Europe PMC · grants.gov
        httpx+trafilatura · pymupdf4llm · r.jina.ai
```

Six **episodes**, not six agents. Same `Agent` object each time; what varies is `instructions`, `output_schema`, and `allowed_function_names`. (Grant, applicant, gaps, competition run tool loops; scoring and narrative run with zero tools.)

---

## 3. Tech stack

Versions verified 2026-09-05. Re-check before pinning.

### Backend — Python 3.12 exactly

> Use `python3.12 -m venv .venv`, not the system `python3` (3.14 on this dev box). Verified: `pymupdf4llm` 0.3.4 does install and work on 3.14, but pin 3.12 so the whole dependency set sits on a supported line.

| Layer | Choice | Version | Note |
|---|---|---|---|
| LLM SDK | `google-genai` | `>=2.22,<3.0` | 3.0 removes AFC from `Models.generate_content` — pin the ceiling |
| API | `fastapi` + `uvicorn` | 0.141 / 0.52 | one worker, no `--reload` in demo |
| SSE | `sse-starlette` | 3.4.10 | `EventSourceResponse`, heartbeats, disconnect detection |
| Jobs | `asyncio.create_task` + run registry | stdlib | **not** Celery/arq/RQ — throughput is ~1 job/min |
| DB | SQLite (WAL) via `aiosqlite` | stdlib | events, evidence, documents, stage outputs, tool cache |
| Validation | `pydantic` | v2 | `response_json_schema=Model.model_json_schema()` |
| HTTP | `httpx` | 0.28.1 | `AsyncClient`, per-host semaphores |
| Rate limit | `aiolimiter` | 1.2.1 | per-host token buckets |
| Retry | `tenacity` | 9.1.4 | transport errors / 429 / 5xx only |
| HTML | `trafilatura` + `lxml` | 2.2.0 | markdown, links, tables |
| PDF | `pymupdf4llm` | **1.28.2** | `page_chunks=True`; pulls `pymupdf-layout`. Read the page number defensively — see T4 |
| Fuzzy match | `rapidfuzz` | latest | quote verification |
| Scholarly | `pyalex` 0.21, `arxiv` 4.0.1, plus thin `httpx` wrappers | | no maintained client exists for ROR / Europe PMC / NIH / DBLP |

### Frontend — React 19.2 + Vite 8 + TypeScript + MUI

Built to static files, served by FastAPI at the same origin. One deploy, one process, no CORS, no SSE proxy hop.

| Concern | Choice |
|---|---|
| Components | `@mui/material` v7 + `@mui/icons-material` |
| Charts | `@mui/x-charts` (**bars/lines only** — its Heatmap is Pro-licensed; the score matrix is a hand-rolled CSS grid) |
| Markdown | `react-markdown` 10 + `remark-gfm` 4 + `rehype-sanitize` 6 |
| State | TanStack Query for REST + a `useRunStream` hook wrapping `EventSource` |
| Routing | React Router — run id and weight vector live in the URL so a report is shareable |

> **Note on MUI vs Tailwind/shadcn.** MUI is a fine choice and the theming/data-grid story is stronger. The one thing it costs: Vercel's **AI Elements** shadcn registry ships ready-made Task / Chain-of-Thought / Tool / Sources / Inline-Citation components that map almost exactly onto this app's progress timeline and citation chips. On MUI you build those from `Stepper`, `Timeline`, `Chip`, `Popover` — budget **half a day** for it. Not a reason to switch; just don't cost it at zero.

### Models

Verified against `ai.google.dev` on 2026-09-05 — **confirm in AI Studio before relying on pricing.**

| Role | Model | $/1M in-out | Where |
|---|---|---|---|
| Agent brain (tool loops) | `gemini-3.8-flash` | 0.75 / 3.75 | E1–E4. 1M context, thinking low/med/high |
| Cheap extraction | `gemini-3.5-flash-lite` | 0.30 / 2.50 | limitation extraction, entailment gate, schema shaping |
| Heavy synthesis | `gemini-3.1-pro-preview` | 2.00 / 12.00 | scoring + narrative only |

**On "Gemini 3.1 Pro is the best one" — worth checking.** Per the pricing page, `gemini-3.8-flash` (released 2026-09-02) is newer, has a 1M-token context, is on the free tier, and costs **~2.7× less input / ~3.2× less output** than `gemini-3.1-pro-preview`, which is paid-only. Pro is the right call for the ~10 hard judgement calls; using it for the ~200 mechanical extractions would cost 7–10× more for no accuracy gain. **Tier the models; make the model a per-episode config value, never a global constant.**

```python
EPISODES = {
  "grant":      Ep(model=FLASH,      thinking="low",  tools=GRANT_TOOLS),
  "applicant":  Ep(model=FLASH,      thinking="low",  tools=PROFILE_TOOLS),
  "gaps":       Ep(model=FLASH,      thinking="medium", tools=SCHOLAR_TOOLS),
  "competition":Ep(model=FLASH,      thinking="low",  tools=COMPETE_TOOLS),
  "score":      Ep(model=PRO,        thinking="high", tools=[]),
  "narrative":  Ep(model=PRO,        thinking="medium", tools=[]),
}
```

### Runtime choice: hand-rolled loop over `google-genai`

**Not** Pydantic AI, LangGraph, or Google ADK.

- Pydantic AI 2.40 raises `UserError` when Gemini built-in tools meet function tools, and implements structured output via tool-calling rather than native `response_json_schema` — losing constrained decoding exactly on the discriminated unions this app uses.
- LiteLLM normalises away `grounding_metadata` spans, `url_context_metadata` status, and `thought_signature` round-tripping.
- LangGraph/ADK/CrewAI are graph DSLs for a 5-node graph that is 30 lines of `await`.

The loop is ~150 lines. Budget **2–3 days and start it day 1** — it is the critical path.

```python
# The three things that will otherwise kill this loop:
# 1. Append response.candidates[0].content VERBATIM to contents. Never reconstruct
#    it — Gemini 3 hard-400s on a missing thought_signature. Serialize only via
#    .model_dump(). This is the #1 killer of hand-rolled Gemini 3 loops.
# 2. automatic_function_calling=AutomaticFunctionCallingConfig(disable=True)
# 3. tool_config.include_server_side_tool_invocations=True IF you ever mix
#    built-in tools with function declarations.
```

---

## 4. The integrity model

This is the part that makes the product trustworthy, and it is the part most likely to be cut under time pressure. It is not one mechanism; it is six cheap ones that each close a different hole.

### 4.1 Python mints, the LLM cites

Only retrieval code creates evidence. Every fetch returns short sequential IDs:

```python
class Evidence(BaseModel):
    id: str                 # "e17" — short + sequential, NOT a content hash
    sha: str                # internal durable key
    source_type: Literal["grant_doc","webpage","paper","author","award","api_query"]
    grade: Literal["metadata_only", "content_verified"]     # see 4.3
    url: str | None
    title: str
    authors: list[str] = []
    date: str | None
    page: int | None
    quote: str | None       # verbatim span, when we actually read text
    quote_status: Literal["exact","fuzzy","unverified"] | None
    summary: str            # <=400 chars — required by requirements_design.md §17
    confidence: Literal["high","medium","low"]   # §17; medium for OCR/fuzzy rows
    locator: str | None     # section id, or "page:char_start-char_end" (§17)
    extractor: str          # "trafilatura" | "pymupdf4llm" | "ocr" | "openalex"
    derived_from: str | None  # e.g. a paper row -> the api_query row that returned it
    retrieved_at: datetime
```

The model sees a numbered catalogue and cites IDs. **No output schema anywhere has a `url` or `source_title` field.**

> **Use `e17`, not `ev_a91f3c02b7d1`.** Models transpose long opaque identifiers at a non-trivial rate, and the failure is *silent content loss* — you cannot tell a genuinely thin claim from six fumbled IDs. Short sequential tokens are far more copyable. Before dropping an unresolvable ID, attempt Levenshtein-1 repair against the allow-list and log every repair as a first-class event.

### 4.2 Quote verification — three-state, fuzzy, never silently dropping

Every extracted requirement and limitation carries a verbatim quote. Python checks it against the bytes we fetched.

**Exact substring matching will fail on 30–50% of correctly-copied quotes** from a real funder PDF — ligatures (ﬁ/ﬀ), soft hyphens, `insti-\ntution` line breaks, curly quotes, en/em dashes, non-breaking spaces, two-column ordering. A binary check would silently delete real mandatory requirements.

```python
def verify_quote(quote: str, page_text: str) -> tuple[Status, str | None]:
    n_q, n_p = normalize(quote), normalize(page_text)   # NFKD, dehyphenate \n,
                                                        # collapse ws, fold quotes/dashes
    if n_q in n_p:
        return "exact", extract_span(page_text, n_q)
    m = rapidfuzz.fuzz.partial_ratio_alignment(n_q, n_p)
    if m.score >= 90:
        return "fuzzy", page_text[m.dest_start:m.dest_end]   # store OUR span, not the model's
    return "unverified", None
```

On a fuzzy hit, **store the document's span as the canonical quote** — the evidence row becomes verbatim-true by construction. `unverified` is *kept* and rendered with an explicit warning badge, never dropped. Alarm in the UI if the drop/unverified rate for a document exceeds ~20% — that is the signal that extraction is broken.

### 4.3 Provenance ≠ entailment

This is the hole every "citation checker" leaves open. Quote-substring proves a source *exists*; nothing yet proves it *supports the claim*.

> `read_paper_sections` returns the verbatim span *"we evaluate only on IID partitions"* → evidence `e88`, quote-verified. The model then writes: *"No existing federated-unlearning method handles non-IID client drift"* `[e88]`. Every gate passes. The quote is real, `e88` exists, the fact cites evidence. **And the claim is a wild overreach from one paper's limitation to a field-wide gap** — which is precisely what §4 of the spec's non-goals forbids.

Three layers, all cheap:

1. **Render the quote inline under every FACT claim in the UI** — not behind a hover. Costs zero tokens; a human sees the mismatch instantly.
2. **One entailment gate per episode.** A single `flash-lite` call receives `(claim_text, quote)` pairs and returns `supports | partial | does_not_support`. Anything not `supports` is downgraded to `inference` and flagged. ~60 lines.
3. **Evidence grading.** `metadata_only` rows (a search hit whose abstract we never read) may support *"X has published 12 papers on Y since 2021"* and nothing else. A claim about a paper's **content** must cite ≥1 `content_verified` row.

### 4.4 Numbers are minted too

The same discipline that protects evidence IDs must protect **numbers** — otherwise the model retypes `12 citing papers` into its output and can transpose digits, average across gaps, or carry a figure from G1 to G3.

```python
# verify_gap writes a record and returns only an id
class VerdictRecord(BaseModel):
    id: str                    # "v3"
    citing_since: int
    citing_with_phrase: int
    corpus_size: int
    growth_curve: dict[int, int]
    oql: str                   # OpenAlex's own human-readable echo of the query
    falsification_hits: list[str]

class Gap(BaseModel):
    title: str
    verdict_id: str            # ← not the numbers themselves
```

The report renderer pulls every count, curve and query string **from the store**, never from LLM output.

### 4.5 Claim typing without an enum

Do **not** make the model emit `kind`. It costs an enum, a validator, and a full-model retry every time it slips.

```python
class Claim(BaseModel):
    text: str
    evidence_ids: list[str] = []
    # kind is DERIVED in Python:  fact if evidence_ids else inference
```

`unknown` is a separate flat `unknowns: list[str]` per stage. Same rendering, no retry class. Unresolvable IDs are dropped by a `mode="after"` validator that logs rather than raises — a stage should not die at minute four over one bad token.

### 4.6 Identity: non-blocking banner + a deterministic tripwire

A wrong researcher match poisons every downstream claim, and **every mechanical check still passes** — there is no symptom anywhere. So it needs its own check.

Resolution is deterministic: `lab domain → ROR → OpenAlex institution → author candidates`. The measured effect is large — `/authors?search=Wei Zhang` returns 10,923 candidates; adding `last_known_institutions.ror` returns **7**.

**Do not block the run on a modal.** A suspended in-process task dies to a closed tab or a sleeping laptop, and a 120-second auto-advance disarms the gate in exactly the situation it exists for. Instead:

- Take the top candidate and **continue**, emitting a correctable banner: *"Analysing **J. Chen**, NTU — not you? [pick another]"*.
- If corrected, re-run pinned to that person key (one input, one line).
- **Tripwire, run unconditionally (~30 lines):** normalised title overlap + topic Jaccard between the publications scraped off the lab page and the selected OpenAlex author's works. Require ≥2 near-exact title matches **or** Jaccard ≥ 0.5. Below threshold → `identity_confidence=low`, a persistent banner at the top of the report, and an `evidence_strength` cap on every direction.

---

## 5. Tool catalog

**23 tools, 4–8 visible per episode.** MVP ships the 19 marked ✅; the rest are v2. Every tool returns **evidence IDs plus a bounded summary**, never a raw document body.

### 5.1 Summary table

| # | Tool | Episode | LLM inside | Purpose in one line |
|---|---|---|---|---|
| **Cross-cutting** ||||
| T1 | `read_evidence` ✅ | all | ✗ | Pull bounded excerpts of evidence the model decides it needs |
| T2 | `record_unknown` ✅ | all | ✗ | Register a field as `not_specified` / `not_verified` / `source_unavailable` |
| T3 | `note` ✅ | all | ✗ | Emit a human-readable line into the run timeline |
| **Ingestion** (orchestrator-called, not LLM-selected) ||||
| T4 | `ingest_grant_call` ✅ | pre-E1 | ✗ | Grant URL / PDF / opportunity no. → page-indexed document |
| T5 | `ingest_researcher_site` ✅ | pre-E2 | ✗ | Bounded crawl of a lab site → page-indexed documents |
| **E1 — Grant** ||||
| T6 | `query_document` ✅ | E1,E2 | ✗ | Ask a question of an ingested doc; get verbatim spans + page numbers |
| T7 | `resolve_funder` ✅ | E1 | ✗ | Funder name → Crossref Funder ID + OpenAlex funder ID |
| T8 | `find_official_supplements` | E1 | ✓ | Locate the official FAQ / guidelines / amendments for a call |
| **E2 — Applicant** ||||
| T9 | `resolve_institution` ✅ | E2 | ✗ | Lab domain or institution name → ROR ID |
| T10 | `resolve_author_candidates` ✅ | E2 | ✗ | Name + ROR + topics → ranked author candidates with a margin |
| T11 | `fetch_author_works` ✅ | E2,E4 | ✗ | Hydrate an author's works: venues, years, topics, coauthors |
| **E3 — Gaps** ||||
| T12 | `search_literature` ✅ | E3,E4 | ✗ | Federated topic search → compact WorkRefs with evidence IDs |
| T13 | `get_work` ✅ | E3,E4 | ✗ | Hydrate one work by ID/DOI (free singleton lookup) |
| T14 | `read_paper_sections` ✅ | E3 | ✓ | Full-text ladder → Limitations / Future Work as verbatim quotes |
| T15 | `expand_citation_graph` ✅ | E3 | ✗ | `cites:` / `cited_by:` / `related_to:` traversal, bounded |
| T16 | `verify_gap` ✅ | E3 | ✗ | **The core tool.** Is this gap still open? Returns numbers + a verdict id |
| T17 | `topic_trend` ✅ | E3,E4 | ✗ | Publication-count-by-year curve for a topic phrasing |
| **E4 — Competition & collaboration** ||||
| T18 | `measure_field_intensity` ✅ | E4 | ✗ | Distinct institutions, HHI concentration, YoY growth |
| T19 | `find_active_groups` ✅ | E4 | ✗ | Who repeatedly publishes on this gap (`group_by=author.id`) |
| T20 | `profile_researcher` | E4 | ✗ | Hydrate a competitor/collaborator: affiliation, works, coauthors |
| T21 | `find_collaborator_candidates` | E4 | ✓ | Capability-gap-first search for people/labs that fill it |
| T22 | `search_funded_projects` | E4 | ✗ | NIH RePORTER / NSF / CORDIS / GtR money-flow evidence |
| **Ranking** — pure Python functions, **not** LLM tools ||||
| T23 | `compute_ranking` ✅ | — | ✗ | Constraints → objective criteria → weighted sum → Dirichlet sensitivity |

> **MVP adapters (required): OpenAlex, httpx+trafilatura, pymupdf4llm, ROR (identity), arXiv HTML (T14 tier 1). Crossref is required too (one keyless GET, for T7 `resolve_funder`). Deferred to v2: grants.gov, ORCID, DBLP, Europe PMC, NIH/NSF/CORDIS/GtR, Semantic Scholar.** The point stands: OpenAlex (works, authors, institutions, `group_by`, awards — it alone covers identity, literature, citation graph, field intensity *and* funder awards), the generic `httpx`+`trafilatura` fetcher, and `pymupdf4llm`. arXiv is the single secondary, for CS/ML recency and full text. **Cut `search_funded_projects` from v1** — `awards.funder_id` on OpenAlex covers the demo case. Eighteen API adapters, each with its own auth/pagination/rate-limit/failure semantics, is where this schedule dies.

### 5.2 Tool detail

Format: `name(input) → output` · purpose · notes.

---

**T1 `read_evidence(ids: list[str], max_chars: int = 2000) → list[{id, title, excerpt}]`** ✅
Pull bounded excerpts from the evidence store on demand. Cap ~6 IDs / ~12k chars per call.

> *Why this exists.* Every other tool returns IDs plus a ≤400-char summary — that is what keeps context under control. But a model that has only ever seen `("e17", "openalex", 400 chars)` **cannot write a specific gap statement**; it produces generic mush that name-drops IDs. `read_evidence` makes it *pull* what it needs rather than having everything pushed. Without this tool the whole design produces vague output.

---

**T4 `ingest_source(url_or_path, policy) → DocumentSet`** ✅ — *one self-detecting function; T5 is the same function with a different policy*

Dispatch on **`Content-Type`, never on file extension** (verified: rgp.gov.sg's document hrefs end `…​.pdf?download=`, so extension matching finds zero PDFs on a page with seven). `text/html` → layers 1–3 below; `application/pdf` → page chunks; `application/zip` → unzip in memory and recurse into each PDF; anything else → skip with `warning{unsupported_type}`.

Deterministic ladder, tried in order — **not** four LLM-selectable tools, or the model picks the wrong tier and burns minutes:

1. **Structured first.** If the URL is grants.gov or an opportunity number is given → `POST api.grants.gov/v1/api/fetchOpportunity` (keyless). Returns `awardCeiling`, `responseDate`, `applicantEligibilityDesc`, plus `synopsisDocumentURLs` to the official PDFs. *Field-name provenance beats page-number provenance.*
2. `httpx` GET → `lxml` → **`doc.make_links_absolute(final_url)`** → `trafilatura.extract(output_format='markdown', include_links=True, include_tables=True, favor_recall=True)`.
3. If extracted < 600 chars or text/html ratio < 1% → refetch via `https://r.jina.ai/{url}` (renders JS, defeats the TLS-fingerprint 403 that blocks nsf.gov; ~3s, free at this volume).
4. **Embedded framework payload.** Modern sites keep real content in a JSON blob, not the DOM. Verified on rgp.gov.sg (Next.js App Router): `trafilatura` returns 2,287 chars and **none of them is the grant-call deadline**, which sits inside `self.__next_f.push([1,"…"])` alongside six document links the DOM never exposes. Decode the flight chunks and pull their `"wysiwyg"` blocks. Registry: Next.js App Router (`self.__next_f`), Next.js Pages Router (`__NEXT_DATA__`), Nuxt (`window.__NUXT__`), JSON-LD. **This is parsing, not rendering — no browser required.**
5. **Harvest links from BOTH the DOM and the payload**, then recurse once. Rank by **type** (zip → pdf → other), not by keyword: on rgp.gov.sg every href is an opaque UUID, so text ranking scores nothing. The real F-CRP Call Information Sheet (21 pp) is a PDF **inside a ZIP**.
6. PDF → `pymupdf4llm.to_markdown(path, page_chunks=True)`, joined with `<<<PAGE {n} | doc_id={id}>>>` banners.

> ⚠️ **No single source is complete.** On the CRP call the dates are page-only; the objectives, eligibility, evaluation criteria, budget and duration are PDF-only. Merge every layer rather than stopping at the first that returns something.

> ⚠️ **`make_links_absolute` is not optional.** trafilatura 2.2.0 with `include_links=True` joins relative hrefs against scheme+host and **drops the base path** — `cv_web.pdf` on `cs.cmu.edu/~rsalakhu/` becomes `cs.cmu.edu/cv_web.pdf`, which 404s. Those fabricated URLs would land in the evidence table as citations.
> ⚠️ **`page_chunks=True` metadata key is version-dependent — detect it, never hardcode it.**
> Verified empirically, both behaviours are real:
> | Install | Path | Key | Extra top-level |
> |---|---|---|---|
> | `pymupdf4llm` 0.3.4, no `pymupdf-layout` | legacy | `page` | `tables`, `images`, `graphics`, `words` |
> | `pymupdf4llm` 1.28.2 + `pymupdf-layout` | layout | `page_number` | `page_boxes` |
>
> 1.28.2 pulls `pymupdf-layout` automatically and is what pip resolves on Python 3.12; 0.3.4 is what it resolved on 3.14. Always use:
> ```python
> page_no = md.get("page_number") or md.get("page")   # correct in both paths
> ```
> ⚠️ **PyMuPDF is AGPL-3.0** and the network clause covers a hosted web app. Keep a `pdfplumber` (MIT) implementation behind the same `(page_no, text)` interface so the swap is a config flag.

`doc_quality ∈ {ok, thin, image_only}` computed from chars-per-page and text-vs-image area. `image_only` routes to a Gemini vision pass **whose output is written into the document store**, so quote verification still works against it, with `extractor=ocr, confidence=medium` on every derived row. A scanned PDF must never silently produce an empty grant interpretation.

No chunking needed: a 17-page NSF solicitation is ~14.5k tokens; a 120-page Horizon Europe programme ~100k — both inside a 1M context.

---

**T5 `ingest_source(url, policy=PROFILE)` → `DocumentSet`** ✅ — the same function as T4, differing only in policy: follow same-site pages matching `/publication|research|people/` rather than document links, cap at 12 artefacts, and do not unzip.

Bounded same-site crawl. Frontier = same host **and** under the seed's directory prefix; fall back to same-host + hint regex (`/publications`, `/people`, `/research`, `/projects`, `/group`) if that yields < 3 pages. Honour `robots.txt` (`Protego`), 1 req/s politeness. Extract the frontier from **lxml anchors, never from the markdown**. Returns external-host signals (arxiv, github, scholar, orcid) for the identity step.

---

**T6 `query_document(doc_id: str, question?: str, section?: str, pages?: str) → list[{page, span, evidence_id}]`** ✅
BM25 retrieval over the page-chunked document, returning **verbatim spans with `doc_id` + page + char offsets**. The model asks questions of the PDF instead of holding it in context.

---

**T9 `resolve_institution(domain_or_name: str) → {ror_id, name, country, evidence_id}`** ✅
`GET api.ror.org/v2/organizations?query.advanced=domains:"{domain}"`. ⚠️ **The plain `query=` parameter does not index domains** — verified: `?query=ntu.edu.sg` returns **0 results**, `?query.advanced=domains:"ntu.edu.sg"` returns 1 → `https://ror.org/02e7b5302`. Fall back to `?query={institution name}` when no domain matches. **Return the full `https://ror.org/{id}` URL** — OpenAlex's `last_known_institutions.ror` filter rejects the bare id (returns 0 with HTTP 200). Keyless.

**T10 `resolve_author_candidates(name, ror_id?, topic_hints[]) → {candidates[], margin}`** ✅

> ⚠️ **`last_known_institutions.ror` must be a SCORING SIGNAL, never a hard filter.** Verified live: for a CMU professor with 417 indexed works, the ROR filter returned **8 records, none of them him** — his canonical record carries `last_known_institutions: NONE`, so the filter excluded it and surfaced only stub duplicates with 1–2 works. OpenAlex routinely fragments an author into one canonical record plus several stubs, and the canonical one often has no institution.
>
> Query by name only, then rank: **works count dominates** (log-scaled; real researchers have hundreds, stubs have 1–3), topic overlap with the profile page guards against a genuine namesake, institution match is a tiebreaker. `backend/spikes/check_demo_pair.py` implements this and is the reference.

`/authors?filter=display_name.search:{name}&select=id,display_name,orcid,works_count,topics,last_known_institutions&sort=works_count:desc`. The `topics` array comes back **inline**, so candidates are scored against the lab page's own research areas in the same call. Confirm with ORCID `/v3.0/{orcid}/employments` (works with **no token**) and, for CS, a DBLP PID check (its `@dc`/`@oc` counts flag dangerous homonyms). Returns `margin` = score gap between #1 and #2.

---

**T12 `search_literature(query, from_year?, to_year?, sources=['openalex'], limit=15) → list[WorkRef]`** ✅
`WorkRef = {evidence_id, openalex_id, title, year, venue, cited_by, doi, has_oa_fulltext}`. OpenAlex primary; arXiv for last-90-day CS/ML recency; Europe PMC for biomedical.

> 💰 **Cost discipline.** OpenAlex has billed on a credit/USD meter since 2026-02-13 and **requires a free key** (anonymous = ~100 list calls/*day*, which one run exhausts). Free key ≈ 10,000 list calls/day. Critically: **singleton lookups by ID or DOI are free and uncapped** while list queries are not. So **search once, hydrate many** — never page through results. Every `*.search` filter — `title_and_abstract.search`, `fulltext.search` and the deprecated `default.search` alias — bills at **$0.001**; plain list+filter and **all `group_by` requests** bill at $0.0001. So choose between title/abstract and full text on **recall**, not cost.
> ⚠️ OpenAlex renamed `grants.*` → `awards.*` in 2026. `filter=grants.funder:F…` now 400s. Every pre-2026 tutorial has this wrong.

**T14 `read_paper_sections(work_id, sections=['limitations','future_work','discussion']) → {sections{}, limitations:[{quote, section, evidence_id}]}`** ✅
Full-text ladder, all keyless, all verified working: `arxiv.org/html/{id}` (clean sectioned HTML for 2024+ submissions — the best CS/ML path, no PDF parsing at all) → Europe PMC `fullTextXML` (explicit `<sec sec-type="discussion">` boundaries) → PMC BioC JSON → `best_oa_location.pdf_url` / Unpaywall. Sets `grade=content_verified` on every row it mints.

---

**T16 `verify_gap(gap_statement, seed_work_ids, limitation_year) → {verdict_id, corpus_size, citing_since, citing_with_phrase, growth_curve, falsification_hits, oql[]}`** ✅

**The tool the product's credibility rests on.** Retrieval is 100% deterministic; the *label* is a separate judgement that must cite these numbers.

Four signals, in order:

1. **Corpus denominator (a gate, not a vote).** Total works matching the direction's topic query with **no date filter**. `corpus_size < 25` → verdict forced to `insufficient_evidence`, `evidence_strength` capped. Never `open`.
2. **Phrasing sanity (a gate).** Run the phrase globally with **no `cites:` filter**. Global hits < ~30 → return `unusable_phrasing` with the count; the model must broaden and retry. *Zero hits on an idiosyncratic phrasing is indistinguishable from an open gap.*
3. **Citation-anchored count.** `/works?filter=cites:{W},from_publication_date:{year},fulltext.search:{phrase}` — one round trip, ~$0.001. OpenAlex echoes the parsed query as `meta.x_query.oql` in plain English, which goes straight into the report as provenance.
4. **Falsification search (mandatory, weighted highest).** 3–4 LLM-generated queries — *"what would the title of a paper that SOLVED this be?"* plus two vocabulary variants and the likely method name — run as `title_and_abstract.search` with **no `cites:` filter**, deduped and hydrated.

> **Why signal 4 is mandatory.** A limitation stated in 2023 gets solved in 2025 by an adjacent community that never cites the 2023 paper and calls it *"statistical heterogeneity in client data"* instead of *"non-IID client drift"*. Signals 3 and 1 both miss it and both read as "open". Only a non-citation-anchored, vocabulary-diversified search finds it.

**Verdict enum (five values, abstain by default):** `open | closed | undetermined | insufficient_evidence | unusable_phrasing`, carried on `VerdictRecord` alongside `verdict_source: Literal["gate","llm"]` — the two gates above set it deterministically, the LLM may only set the first three.

The evidence-sufficiency floor (§6) requires a verdict of **exactly `open` or `closed`**; the other three block a direction from ranking. A gap may be asserted `open` only on **positive** evidence. Zero hits is `undetermined`, full stop — a zero count may only *fail to support* openness, never *prove* it.

> ⚠️ Do not put a threshold ladder inside this tool and call it deterministic. `562 works cite W, postdate the limitation, and discuss the phrase` reads equally as *"many people solved it"* (closed) and *"many people are still complaining about it"* (open). No threshold resolves that. Keep the **retrieval** deterministic and the **label** an LLM judgement that must cite these specific stored numbers — plus one `flash-lite` call over the top-5 most-cited citing works asking only *"does this work claim to address `<gap>`?"*, which is the one genuinely decorrelated signal.

---

**T18 `measure_field_intensity(query, since) → {distinct_institutions, distinct_pis, yoy_growth, hhi, evidence_id}`** ✅
Competitive intensity as arithmetic, not vibes. One `group_by` call is ~$0.0001 and returns exactly what's needed:

| Question | Query |
|---|---|
| Who is crowding this space | `group_by=authorships.institutions.id` |
| Is it heating up | `group_by=publication_year` |
| Which PIs specifically | `group_by=authorships.author.id` |
| Who funds it | `group_by=awards.funder_id` |

HHI over the institution counts gives concentration. Live example: `federated unlearning` by year → `2020:1, 2021:5, 2022:18, 2023:38, 2024:110, 2025:182, 2026:248` — a publishable growth curve from one request.

---

**T23 `compute_ranking(directions, scores, weights, constraints) → RankingResult`** ✅ — **pure Python, no LLM**

Detailed in §7.

---

## 6. End-to-end flow

Worked example: **grant** = an NRF Singapore call on trustworthy autonomous systems; **profile** = an NTU robotics lab page.

### Phase 0 — Intake (deterministic, ~10 s)

```
POST /api/runs {grant_url, grant_pdf?, profile_url}
  → run_id, status=running
  → T4 ingest_grant_call(url)      → doc_id=g1, 17 pages, quality=ok   → e1..e3
  → T5 ingest_researcher_site(url) → doc_ids=[p1..p7], 7 pages         → e4..e12
  SSE: run.started · tool.finished{ingest_grant_call} · evidence.added × 12
```

Both run concurrently. Failures here are **reported, never guessed** — an unreachable profile URL emits `warning{code: profile_unreachable}` and the run continues with `applicant_confidence=low`.

### Phase 1 — E1 Grant + E2 Applicant (parallel, ~60–90 s)

```python
grant, applicant = await asyncio.gather(
    episode("grant",     GRANT_PROMPT,     GrantIntel,       GRANT_TOOLS),
    episode("applicant", APPLICANT_PROMPT, ApplicantProfile, PROFILE_TOOLS),
)
```

**E1 — Grant** · tools: `query_document`, `resolve_funder`, `read_evidence`, `record_unknown`, `note`

| # | Call | In | Out |
|---|---|---|---|
| 1 | `query_document` | `g1`, "eligibility and PI requirements" | 4 spans, pp. 3–4 → `e13..e16` |
| 2 | `query_document` | `g1`, "evaluation criteria and weights" | 3 spans, p. 9 → `e17..e19` |
| 3 | `query_document` | `g1`, "budget ceiling, duration, deadline" | 3 spans, p. 2 → `e20..e22` |
| 4 | `resolve_funder` | "National Research Foundation Singapore" | Crossref `501100001381`, OpenAlex `F4320320709` → `e23` |
| 5 | `read_evidence` | `[e17,e18,e19]` | full criterion text |
| 6 | `record_unknown` | "industry_cofunding_ratio", "not stated" | — |

→ `GrantIntel` (Pydantic-validated). Then Python runs **quote verification** over every requirement and the **entailment gate** over every fact claim.

**E2 — Applicant** · tools: `query_document`, `resolve_institution`, `resolve_author_candidates`, `fetch_author_works`, `read_evidence`, `record_unknown`

| # | Call | In | Out |
|---|---|---|---|
| 1 | `query_document` | `p1`, "researcher name, role, institution" | "Prof. J. Chen, NTU" → `e24` |
| 2 | `resolve_institution` | `ntu.edu.sg` | ROR `02e7b5302` → `e25` |
| 3 | `resolve_author_candidates` | "J. Chen", ROR, topics from `p1` | 3 candidates, **margin 0.41** → `e26` |
| 4 | `fetch_author_works` | `A5012…`, since 2019, limit 40 | 38 works → `e27..e64` |
| 5 | `query_document` | `p4`, "lab equipment and platforms" | "2 Franka arms, 8×A100" → `e65` |

→ **Identity tripwire** (Python, unconditional): title overlap + topic Jaccard between `p2` (publications page) and the 38 works. Pass → banner shows the resolved identity as correctable. Fail → `identity_confidence=low` + report banner + evidence cap.

→ `ApplicantProfile`.

### Phase 2 — E3 Gaps (~2–4 min, the long pole)

Tools (8 — unknowns are collected in the output schema rather than via a tool): `search_literature`, `get_work`, `read_paper_sections`, `expand_citation_graph`, `verify_gap`, `topic_trend`, `read_evidence`, `note`

The model is given `GrantIntel` + `ApplicantProfile` and asked to intersect them. **Cardinality is data-dependent; the LLM drives the loop within a `request_limit`.**

```
 1  note                  "Intersecting 4 grant priorities × 6 capabilities → 5 candidate directions"
 2  search_literature     "trustworthy multimodal embodied agents", from 2022     → 15 WorkRefs  e66..e80
 3  topic_trend           same query, since 2019                                  → curve        e81
 4  get_work              W2995022099 (most-cited hit)                            → abstract     e82
 5  read_paper_sections   W2995022099                                             → 3 limitation quotes e83..e85
 6  read_paper_sections   W3104…                                                  → 2 quotes     e86..e87
 7  expand_citation_graph W2995022099, direction=cited_by, limit=25               → 25 refs      e88..e112
 8  verify_gap            "no runtime safety guarantee under sensor dropout",
                          seeds=[W2995022099], limitation_year=2023
                            ├ corpus_size            = 1,840        ✓ gate passes
                            ├ phrasing global hits   = 214          ✓ gate passes
                            ├ citing_with_phrase     = 12
                            ├ growth 38→110→182→248
                            └ falsification (4 queries, no cites: filter) → 2 candidate solvers
                                                                        → verdict_id=v1  e113
 9  read_evidence         [e113 + the 2 falsification hits]
10  get_work              the 2 candidate solvers                                 → e114..e115
11  verify_gap            direction 2 …                                           → v2
…   (repeat per direction; typically 18–30 calls total)
```

→ `GapReport { directions[], gaps[{title, direction_id, verdict_id, evidence_ids}], rejected[], landscape[] }`

> `landscape: list[{direction_id, subareas[], representative_work_ids[], current_state, trend_evidence_id}]` — populated from the `search_literature` + `topic_trend` calls E3 already makes. Without it, requirements §23-C (research landscape summary) has no data source at all.

**Evidence-sufficiency floor, enforced in Python at the E3→E4 boundary** (not by the model). A direction proceeds only with:

- ≥ N distinct evidence rows spanning ≥ 2 distinct sources, **and**
- ≥ 1 quote-verified limitation, **and**
- a recency verdict that is not `undetermined`.

Failures go to an **"insufficient evidence to recommend"** band with their actual counts shown. Nothing in this system may force five directions into existence — §21 of the spec requires exactly this refusal, and a digital-humanities call with 11 total hits is the case that proves it.

### Phase 3 — E4 Competition & collaboration (~1–2 min)

Tools: `measure_field_intensity`, `find_active_groups`, `search_literature`, `get_work`, `profile_researcher`, `find_collaborator_candidates`, `read_evidence`

Per surviving direction:

```
 1  measure_field_intensity  gap query, since 2023   → 31 institutions, HHI 0.06, YoY +1.7×   e116
 2  find_active_groups       gap query, since 2023   → top 8 PIs by count                     e117..e124
 3  profile_researcher       A5031… (top competitor) → affiliation, 12 recent works, coauthors e125
 4  find_collaborator_candidates
                             capability_gap="formal safety verification",
                             constraints={grant_requires_sg_lead: true}
                                                     → 3 profiles + 4 named candidates        e126..e132
```

→ `CompetitionReport { per_direction[{intensity_evidence_id, competitors[], overlap_class}], capability_gaps[], collaborator_profiles[], candidates[] }`

**Collaborators are searched capability-first.** Right: `need formal safety expertise → search formal robot safety labs`. Wrong: `search famous robotics professors`. Always `potential collaborator`, never `confirmed`.

### Phase 4a — E5 Scoring (~20–40 s, 1 call, no tools)

`gemini-3.1-pro-preview`, `thinking=high`, **zero tools**. Input: the four upstream reports plus the evidence catalogue. Output: per direction, an ordinal ranking on each judged criterion plus a `CriterionScore` carrying `evidence_ids` and a rationale (§7.2, §7.3). Also emits the weight ordinals.

> This episode exists in §3's `EPISODES` config but was missing from the flow, the timing table and the build order in an earlier draft. It is the producer of `compute_ranking`'s `scores` argument — without it that function has no input.

### Phase 4b — Ranking (pure Python, < 1 s)

**No LLM.** See §7.

### Phase 5 — E6 Narrative + assembly (~30–60 s)

One `gemini-3.1-pro-preview` call per ranked direction produces prose for `problem_statement`, `evidence_backed_gap`, `key_strengths`, `key_weaknesses`, `risks`, `recommendation`.

**Evidence is attached at the field level, not as inline tokens:**

```python
class DirectionSection(BaseModel):
    text: str
    evidence_ids: list[str]
```

> Chips render **beneath** the paragraph, from `evidence_ids`. Do **not** ask the model to embed `[[ev:e17]]` and `{{m:3}}` tokens inside free prose — constrained decoding cannot enforce token discipline inside a string, models drop and mis-cite them, and the failure mode is a visibly broken report. Field-level attachment is enforceable by the schema.

Every **number** in the report is injected by the renderer from the store via `verdict_id` / `intensity_evidence_id`. The model never retypes a count.

```
SSE: stage.finished{narrative} · artifact.ready{final_report} · run.finished
```

### Timing and cost budget

| Phase | Wall clock | Model calls | Notes |
|---|---|---|---|
| 0 Intake | 10–20 s | 0 | parallel |
| 1 Grant ‖ Applicant | 60–90 s | ~14 | parallel |
| 2 Gaps | 2–4 min | ~30 | the long pole |
| 3 Competition | 1–2 min | ~18 | |
| 4a Scoring | 20–40 s | ~1 | Pro, no tools |
| 4b Ranking | < 1 s | 0 | pure Python |
| 5 Narrative | 30–60 s | ~6 | Pro |
| **Total** | **~5–9 min** | **~70** | **~$0.80–1.60/run** |

> The cost driver is **context re-transmission**, not the number of calls: a tool loop re-sends the whole transcript every turn, so a 30-call episode at ~60k tokens bills far more than 30 × 60k ÷ 2. With `REPLAY_TOOLS=1` (§8.4) a warm re-run is ~$0.10.

OpenAlex spend is roughly $0.02–0.05 per run against a $1/day free-key budget — ~20–50 runs/day. Surface `meta.cost_usd` and the remaining-credit header in the UI; it is now a real resource.

---

## 7. The ranking engine

Moving the arithmetic into Python is necessary but **not sufficient for transparency** — done naively it just relocates the black box upstream into nine unanchored 0–10 scores. Four measures fix that.

### 7.1 Compute what is computable

Label every criterion's provenance and show it in the UI. **Two of the nine need no LLM judgement at all** — fewer than an earlier draft claimed, because `grant_alignment` and `competitive_differentiation` are genuine judgements once they stop double-counting the constraint gate:

| Criterion | Provenance | Source |
|---|---|---|
| `grant_alignment` | llm_judged | topical fit against the call's `priority_research_areas` / `objectives` / `preferred_characteristics`, citing the grant evidence IDs that establish each priority |
| `competitive_differentiation` | llm_judged | anchored rubric: how the applicant's approach differs from the active groups found in E4 |
| `evidence_strength` | **computed** | count of `content_verified` rows + quote-verification pass rate |
| `feasibility` | **computed** | capability overlap between direction needs and verified applicant resources |
| `scientific_novelty` | llm_judged | anchored rubric |
| `importance` | llm_judged | anchored rubric |
| `applicant_fit` | llm_judged | anchored rubric |
| `collaboration_potential` | llm_judged | anchored rubric |
| `impact_potential` | llm_judged | anchored rubric |

> **Two §3.2 output fields are reported but are NOT ranking criteria — do not conflate them with the scores above:**
>
> - **`competitive_intensity: LOW | MEDIUM | HIGH`** — computed in Python from `measure_field_intensity` (HHI + distinct institutions + YoY growth) against published thresholds. `competitive_differentiation` is the *judged* criterion; intensity is the *measured* fact. Requirements §3.2 asks for both.
> - **`confidence: high | medium | low`** per direction — computed in Python, **never LLM-emitted**, from: margin over the §6 evidence-sufficiency floor, the `verify_gap` verdict (`undetermined`/`insufficient_evidence` → cap at `low`), quote-verification pass rate, `identity_confidence` (low → caps every direction), and §7.5 score-perturbation stability. Required by §3.2, §23-D and §20's rule that *"a low-evidence candidate should receive confidence = low even if the LLM finds the idea plausible."* This is **not** the same as `evidence_strength`, which is a weighted score.

### 7.2 Elicit ordinal, not absolute

LLMs scoring 5 items × 9 criteria in one shot show **score compression** (everything lands 6–8, so weights barely matter), **position bias** (the first-listed item scores ~0.5 higher), and no cross-item calibration.

- Give each criterion an **anchored rubric** in the prompt: one sentence each for what a 2, a 5, and an 8 look like, with a concrete example.
- Ask the model to **rank the directions per criterion** (ordinal over 5 items — far more reliable than absolute scoring) and map rank position → score in Python. Keep the absolute score as a secondary signal only.
- Randomise direction order across criteria to break position bias.

**A score is never a bare float.** Requirements §12 is explicit: *"Each criterion score must point to supporting evidence from upstream reports."*

```python
class CriterionScore(BaseModel):
    value: float                     # 0-10
    provenance: Literal["computed", "judged"]
    evidence_ids: list[str]          # >=1 required for judged criteria
    rationale: str
```

Judged criteria must cite evidence in the scoring call's schema; computed criteria emit the IDs their arithmetic consumed (`intensity_evidence_id`, the `content_verified` row IDs behind `evidence_strength`). Heatmap cells click through to those chips — otherwise §6.7's black box has just moved one level down.

### 7.3 Weights: ordinal in, floats out

`derived_weights: dict[str, float]` as free LLM output is the single highest-leverage number vector in the report and would arrive unnormalised, summing to 1.07, with invented weights for criteria the call never mentions.

```python
# Model emits, per criterion, an ordinal + the quote justifying it:
{"grant_alignment": {"level": "high", "evidence_id": "e17"},
 "impact_potential": {"level": "medium", "evidence_id": "e18"},
 "collaboration_potential": {"level": "not_addressed", "evidence_id": None}}

# Python maps and normalises:
LEVEL = {"high": 3.0, "medium": 2.0, "low": 1.0, "not_addressed": 0.5}
weights = normalize({k: LEVEL[v["level"]] for k, v in ordinals.items()})
```

The report renders the mapping table explicitly — *grant criterion → our criteria → weight* — and labels the vector `grant-derived` or `default`. Free floats are arithmetic, and arithmetic belongs to Python.

### 7.4 Hard constraints are a gate, not a score

```python
class Constraint(BaseModel):
    rule: str
    status: Literal["pass", "fail", "unknown"]
    evidence_id: str | None
```

Any `fail` routes the direction to `rejected_or_weak` with a reason. It never receives a score that high novelty could outweigh. §19 requires exactly this.

### 7.5 Sensitivity — and its honest limit

```python
overall = sum(weights[c] * scores[c] for c in CRITERIA)     # weights sum to 1.0

# Dirichlet over the weight simplex, 2,000 samples → P(rank=1) per direction
# PLUS a ±1 perturbation on the llm_judged scores themselves.
```

> **Be honest about what Dirichlet-over-weights does and does not show.** If D1 and D2 score 7.41 and 7.28, resampling *weights* will report "D1 ranks first in 94% of samples" — because the *gap* is stable under reweighting. But the gap came from `novelty 8` vs `novelty 7`, which at temperature 1.0 could flip on a rerun. Weight-only sensitivity makes score noise look like robustness. So: **also perturb the `llm_judged` scores by ±1** and report both numbers separately. If the ordering is not stable under score perturbation, say so — "these two are too close to separate on current evidence" is a *more useful* answer than a confident #1.

### 7.6 The weight slider

Because `scores` and `weights` are stored as plain JSON, the frontend re-ranks **in the browser with the same formula** — instant, free, and provably consistent with the report. The weight vector lives in the URL, so a re-weighted view is shareable.

---

## 8. Backend contracts

### 8.1 HTTP

```
POST   /api/uploads                 → {upload_id, sha256}             multipart, size/MIME capped
POST   /api/runs                    → {run_id}                        start a run; 422 unless
                                                                      grant_url OR grant_upload_id
GET    /api/runs/{id}               → full JSON snapshot              for refresh/reconnect
GET    /api/runs/{id}/events        → text/event-stream               deltas, monotonic id:
POST   /api/runs/{id}/identity      → {}                              correct the resolved researcher
POST   /api/runs/{id}/cancel        → {}
GET    /api/runs/{id}/report.md     → text/markdown                   export, sections A–E
GET    /api/runs                    → [{run_id, status, created_at}]  history
```

**Snapshot + delta.** Never stream the result off the POST — you lose it on refresh. Client: `POST` → `GET` snapshot → open `EventSource` from `snapshot.last_seq`.

### 8.2 Event vocabulary

Emit typed events, not free text. This single decision is what makes a good progress UI possible.

```
run.started              {run_id, inputs}
stage.started            {stage}
stage.finished           {stage, ms, ok}
tool.call.started        {tool, args_summary}
tool.call.finished       {tool, ms, ok, result_summary, evidence_added:[ids]}
evidence.added           {id, source_type, grade, title, url, retrieved_at}
identity.resolved        {candidates[], selected, margin, confidence}
warning                  {code, message}          ← §21 graceful degradation surfaces here
artifact.ready           {name, schema_version}
run.finished             {report_id}
run.failed               {code, message}
```

### 8.3 SQLite schema

```sql
runs          (run_id PK, created_at, status, grant_url, grant_pdf, profile_url, error, finished_at)
events        (run_id, seq INTEGER, ts, type, stage, payload_json, PRIMARY KEY(run_id, seq))
documents     (run_id, doc_id, page, sha256, url, text, doc_quality, extractor,
               PRIMARY KEY(run_id, doc_id, page))   -- one row per PAGE; index sha256 separately
evidence      (id, run_id, sha, source_type, grade, url, title, page, quote,
               quote_status, summary, confidence, locator, extractor, derived_from,
               retrieved_at, PRIMARY KEY(run_id, id))
verdicts      (id, run_id, kind, payload_json, PRIMARY KEY(run_id, id))
stage_outputs (run_id, stage, schema_version, json, created_at)
tool_cache    (inputs_hash, tool_name, args_canonical, result_json, created_at,
               PRIMARY KEY(inputs_hash, tool_name, args_canonical))
```

**The `events` table is the highest-leverage 40 lines in the backend.** It is simultaneously the SSE replay log, the debug trace, and the UI's progress state. Page refresh, network blip, and "show me what run #7 did" all become `WHERE seq > ?`.

### 8.4 Cache at the tool-call layer, not HTTP

An HTTP cache (hishel) is nearly useless here: at `temperature=1.0` the model issues **different query strings** on every run, so every scholarly call misses. Cache on `(inputs_hash, tool_name, canonical_args)` instead. ~30 lines, and with `REPLAY_TOOLS=1` it makes prompt iteration **free and deterministic** — you can tune the gaps prompt without spending a single OpenAlex credit or waiting four minutes. This is the real demo insurance.

### 8.5 SSE gotchas that will otherwise cost you an afternoon

- **Exclude `/events` from `GZipMiddleware`** — it buffers the stream and nothing reaches the browser for minutes. It looks exactly like a frontend bug.
- Set `Cache-Control: no-cache` and `X-Accel-Buffering: no`; nginx needs `proxy_buffering off` and `proxy_read_timeout` above your worst-case run length.
- Send a `:ping` heartbeat every 15 s — proxies idle-timeout at 60–120 s, well under a run.
- **Call `es.close()` on `run.finished`/`run.failed`** — `EventSource` reconnects forever otherwise, hammering a completed run.
- Native `EventSource` cannot send custom headers; auth must be a cookie or a signed token in the query string.

---

## 9. Frontend

Three routes: `/` (new run), `/runs/:id` (live + report), `/runs` (history).

### 9.1 Live run view — three zones

```
┌──────────────┬───────────────────────────────┬──────────────────┐
│ STAGE RAIL   │  ACTIVITY TIMELINE            │ EVIDENCE LEDGER  │
│ MUI Stepper  │  MUI Timeline, streaming      │ live "Sources    │
│              │                               │  (47)" counter   │
│ ✓ Ingest     │  ⏵ search_literature          │ ┌──────────────┐ │
│ ✓ Grant      │    "trustworthy embodied…"    │ │ e80 · paper  │ │
│ ✓ Applicant  │    → 15 works · 1.2 s         │ │ Chen 2025    │ │
│ ⏵ Gaps       │  ⏵ read_paper_sections        │ │ ✓ verified   │ │
│ ○ Competition│    W2995022099 → 3 limits     │ └──────────────┘ │
│ ○ Ranking    │  ⏵ verify_gap  …              │       ⋮          │
└──────────────┴───────────────────────────────┴──────────────────┘
```

The activity log **persists after completion as an audit trail** — exactly right for a provenance tool. Never a fake percentage bar; show real counts.

> **`report.md` and the report view must both carry requirements §23's five sections:** **A** grant summary (purpose, scope, eligibility, ceiling/duration, evaluation priorities), **B** applicant capability summary, **C** research landscape summary, **D** the ranked directions, **E** directions not recommended and why. A, B and D/E are recoverable from `GrantIntel` / `ApplicantProfile` / the ranking at render time. **C is not** — see the note in §5 Phase 2.

### 9.2 Report view

- **Ranked direction cards**, expandable, each with a per-criterion score strip.
- **Score matrix: a 5 × 9 heatmap** rendered as a **hand-rolled CSS grid of 45 `<Box>`s** with a single-hue `backgroundColor` scale and a per-cell `Tooltip` (~40 lines). ⚠️ `@mui/x-charts`'s Heatmap is a **paid Pro component** — verified on mui.com. Radar is the trap — 9 axes × 5 overlaid polygons is unreadable, and axis order implies a false adjacency. Grouped bars are the second trap — 45 bars. A heatmap reads at a glance and scales.
- Each criterion column header carries its **provenance badge** (`computed` / `judged` / `default`).
- **Weight sliders** (9 × MUI `Slider`) re-ranking live in the browser. A "reset to grant-derived" button. The weight vector syncs to the URL.
- **Citation chips** render beneath each paragraph from `evidence_ids`; click opens the evidence panel; hovering a source highlights every chip citing it.
- **The quote is rendered inline under every FACT claim**, not hidden behind a hover — this is a correctness mechanism (§4.3), not a decoration.
- **`FACT` / `INFERENCE` / `UNKNOWN` encoded by shape *and* text**, not colour alone. An explicit "no source" badge where applicable.
- Header counter: **"47 claims · 41 sourced · 6 inferred · 0 unsupported"**.
- Markdown fields go through `react-markdown` + `remark-gfm` + `rehype-sanitize`. **Do not add `rehype-raw`** — v10 escapes raw HTML by default and its `urlTransform` already blocks `javascript:` URLs, so the LLM-markdown XSS surface is closed for free.

### 9.3 Dev loop

The frontend developer must not wait 6 minutes and $0.30 per iteration. Ship a **fixture mode** on day 1: one recorded run's event log replayed from JSON at an adjustable speed multiplier, behind `?fixture=1`. Falls straight out of the `events` table.

---

## 10. Failure and degradation

Every row surfaces as a `warning` SSE event and a visible badge in the report. Nothing here silently degrades.

| Failure | Response |
|---|---|
| Grant page 403 / JS-only | ladder → `r.jina.ai` → Playwright; if all fail, `source.unavailable`, ask the user for a PDF |
| Scanned PDF | detect `image_only` at ingest → Gemini vision pass → **write output into the document store** so quote verification still works; mark `extractor=ocr` |
| Profile URL unreachable | continue with `applicant_confidence=low`, visible banner |
| Author identity ambiguous | proceed with top candidate + correctable banner + tripwire; `identity_confidence=low` caps evidence strength |
| OpenAlex credits exhausted | serve from `tool_cache`; surface remaining budget in the UI before it bites |
| Semantic Scholar 429 | circuit-break; it is enrichment only, never on the critical path |
| Model hits `request_limit` | **finalize the stage from the evidence store**, do not fail. Inject "you have N rounds left, begin converging" at 60% of budget |
| Schema too large → 400 | drop `response_json_schema`, run the loop bare, shape with a separate zero-tool `flash-lite` call |
| No credible gap found | return **"No high-confidence research gap identified from the available evidence"** with the counts that led there. Do not force a recommendation |
| No suitable collaborator | return the required **profile**, never an invented name |

---

## 11. Build order

**Invert the instinct to build infrastructure first.** Every milestone below produces something a person can look at.

| Day | Milestone | Ships |
|---|---|---|
| **0** | **API spikes** — 90 minutes (done for the demo: see `backend/spikes/check_demo_pair.py` and `backend/spikes/probe_grant_url.py`) | One real call at each load-bearing assumption, printing raw responses: the composite `cites:` + `fulltext.search` query, an OpenAlex `group_by`, the `awards.*` filter name, a ROR domain lookup, `grants.gov fetchOpportunity`, arXiv HTML for a 2023 and a 2025 paper, and **a 4-tool-call Gemini loop to prove `thought_signature` round-tripping works**. Do this before committing to any of it. |
| **1–2** | **Ugliest possible vertical slice** | Hardcoded grant PDF + hardcoded lab URL → fetch → OpenAlex search → **one** LLM call → 3 directions with quoted evidence → a static HTML page. No SSE, no identity, no store, `print()` for progress. It will be bad **and it will run start to finish.** |
| **3** | Agent loop + evidence store | The real `google-genai` tool loop; `Evidence` minting; quote verification with fuzzy tier; short sequential IDs |
| **4** | Backend skeleton + SSE | FastAPI, `events` table, `Last-Event-ID` replay, `tool_cache` + `REPLAY_TOOLS`, fixture generator |
| **5** | E1 + E2 real | Grant and applicant episodes, identity resolution + tripwire, MUI shell with live timeline |
| **6–7** | E3 gaps | `search_literature`, `read_paper_sections`, `verify_gap` with all four signals, evidence-sufficiency floor |
| **8** | E4 + E5 scoring + ranking | Competition episode, the E5 scoring call (ordinal + rubrics + `CriterionScore`), `compute_ranking`, constraints, Dirichlet + score perturbation |
| **9** | Report UI | Direction cards, heatmap, weight sliders, citation chips, inline quotes, export |
| **10** | Entailment gate + polish | The `flash-lite` entailment pass, warning surfacing, run history |

**The thing that must be true on day 2:** the pipeline is closed. Every later milestone is then an in-place quality improvement on a working system, not a bet that the last integration will land.

> **Honest schedule note.** The full scope above is ~15 working days at a normal pace, not 10. If the deadline is shorter, cut in this order: `search_funded_projects` → `find_collaborator_candidates` (return profiles only, no named candidates) → `find_official_supplements` → the entailment gate → run history. **Do not cut** the evidence store, quote verification, the sufficiency floor, or the identity tripwire — those are the product.

---

## 12. Open decisions

| # | Question | My recommendation |
|---|---|---|
| 1 | Confirm current Gemini model IDs and pricing in AI Studio | The research says `gemini-3.8-flash` is newer, cheaper and 1M-context vs `gemini-3.1-pro-preview`. Verify before pinning — this is past my reliable knowledge. |
| 2 | Get an **OpenAlex API key** (30 s, free) | Blocking. Anonymous access is ~100 list calls/day; one run exhausts it. |
| 3 | Gemini tier | Search grounding **is** available on the free tier for Gemini 3.x Flash (5,000 grounded requests/month, then $14/1,000). But `gemini-3.1-pro-preview` has **no free tier at all** — every scoring and narrative call is billed from request one. Free-tier RPD is unpublished; check the AI Studio dashboard before demo day. |
| 4 | Is a Singapore funder the target? | There is **no public machine-readable API** for NRF/A\*STAR/MOE awards (IGMS is login-gated). Route Singapore funding intelligence through OpenAlex funder records — NRF is `F4320320709`, MOE `F4320320751`. |
| 5 | Will this be hosted publicly? | If yes, PyMuPDF's AGPL network clause applies — use the `pdfplumber` path. |
| 6 | How many directions must the report return? | Spec says 3–5. Recommend: **as many as clear the evidence floor, up to 5**, with an explicit "insufficient evidence" band for the rest. |

---

## 13. What I would push back on in the original spec

1. **§7 Coordinator agent** — delete it. Six `await`s in a function.
2. **§12 "Ranking Agent"** — not an agent, and mostly not an LLM. One scoring call, then arithmetic.
3. **§15 project structure** — `app_agents/` with six modules becomes `agent/` (one loop) + `tools/` + `schemas/` + `pipeline.py`.
4. **§22 "CLI first, web UI later"** — inverted. The two highest-value corrections in this system are one click each in a browser and impossible in a batch CLI. Keep a CLI entry point for testing; design for the browser.
5. **§16's reliance on Google Scholar / IEEE / ACM** — off the table (no API, ToS, bot walls). You lose almost nothing: IEEE and ACM deposit DOIs into Crossref, which OpenAlex ingests, and DBLP has the best CS conference coverage anywhere. What you genuinely cannot get is their paywalled full text — so limitation-reading leans on arXiv HTML and Europe PMC.
6. **§16's Semantic Scholar dependency** — measured unreliable without a key today, and key applications run ~1 month and refuse free email domains. Keep it behind a circuit breaker for its two unique assets (`tldr`, Recommendations API).
7. **Papers with Code is dead** — `paperswithcode.com` 302s to Hugging Face. Any spec text referencing its API is stale.
