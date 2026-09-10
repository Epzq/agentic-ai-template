# Execution Plan — Demo Build

**Implements:** `demo-spec.md` (rev 2). Every work item names the acceptance criteria it serves.
**Rule:** every work item ends with a **green `pytest`** (or a visibly working screen). Never leave the tree broken between items.

> **Revision 2** — re-costed and restructured after a verification pass. The headline change: **this is ~27 h of work, not 16 h.** Revision 1 labelled it two days by pricing every item at its happy path. See §Budget.

**Legend** — `WI-n` work item · `[AC…]` criteria served · ⏱ estimate · 🔒 blocks · **CORE** = in the 2-day cut, **PLUS** = day 3

> **Repo layout (since WI-2.3).** The Python project lives in **`backend/`** and the Vite app in
> **`frontend/`**; the planning documents stay at the root. Paths in this file are written from the
> root (`backend/roia/api.py`); paths inside the backend's own docstrings and `backend/fixtures/README.md`
> are relative to `backend/`. **Every Python command runs from `backend/`** — `pyproject.toml`, `.env`
> and `.venv/` are there. `backend/roia/paths.py` resolves `fixtures/`, `runs/` and `.env` from
> `__file__`, so `pytest`, `uvicorn` and `python -m roia` no longer care where they were launched.

> **`⚠️ Carried over from WI-x.y`** on a checklist bullet means an earlier item found something *this* item
> must handle. It is written here, in the item that does the work, rather than only in the STATUS line of the
> item that found it — that line is invisible to whoever picks this up. **🔴** marks the ones that break
> something if missed, including two tests deliberately written to fail when the work lands (WI-1.6a, WI-1.6d).

---

## Budget — read this first

| | Stated in rev 1 | Honest |
|---|---|---|
| Phase 0 | 90 m | **2 h** |
| Phase 1 (backend) | 8 h | **14 h 45** |
| Phase 2 (API + frontend) | 8 h | **10 h** |
| **Total** | 16 h | **~27 h ≈ 3.5 days** |

(Item estimates sum to 25 h 45; call it 26 h. Add your own debugging buffer on top — these are build times, not calendar times.)

**Every work item is CORE.** There is no item you can drop and still have a demo — the scope was already cut once, in `demo-spec.md` §4. What *is* optional are five checklist bullets marked **PLUS**, which together buy back about 4 hours:

| PLUS bullet | Item | Saves |
|---|---|---|
| Score matrix (27-cell CSS grid) → plain per-criterion list | WI-2.5 | ~1 h 30 |
| PDF upload endpoint → URL-only grant input | WI-2.1 | ~30 m |
| `report.md` Jinja export | WI-1.7 | ~30 m |
| Timeline richness → flat event list | WI-2.4b | ~1 h |
| `ingest_profile` extra links → seed page only | WI-1.4 | ~30 m |

So: **~23 h stripped, ~27 h full.** Neither is two days. **Decide on day 0, in writing** — not at 9 pm on day 2 — whether you are running this as a tight 3-day build or a comfortable 4-day one.

`demo-spec.md` §7 already concedes "two long days, or three comfortable ones." This is the same statement with the arithmetic shown.

---

## Progress

Update this table **and** the item's `STATUS` line as each work item is committed. `pending` items have not been started.

| WI | Status | Commit |
|---|---|---|
| 0.0 Fix the demo pair | ✅ done | `e8e821f` |
| 0.1 Keys and environment | ✅ done | — |
| 0.2 API spikes | ✅ done | `b5baec3`, `f857a7e` |
| 1.0 Report fixture | ✅ done | `d6352d7` |
| 1.1 Skeleton + config | ✅ done | `cf3cdd9` |
| 1.2 Evidence store | ✅ done | `f6875c3` |
| 1.3 Event emitter | ✅ done | `f3a9c3b` |
| 1.4 Ingestion | ✅ done | `7502dac` *(3 layers, per `backend/spikes/probe_grant_url.py`)* |
| 1.4b Pre-flight probe | ✅ done | `19e0a96` |
| 1.5 OpenAlex client | ✅ done | `bd3be1e` |
| 1.6a LLM plumbing + #1/#2 | ✅ done | `242b51f` |
| 1.6b LLM #3 candidates | ✅ done | `57768a9` |
| 1.6c LLM #4 + rubrics | ✅ done | `f8ad9d9` |
| 1.6d Pipeline orchestration | ✅ done | `8ea2aa4` |
| 1.7 Ranking + report | ✅ done | `ae29406` |
| 2.1 FastAPI shell | ✅ done | `53f3806` |
| 2.2 SSE | ✅ done | `d8358a0` |
| 2.3 Fixture replayer | ✅ done | `c87b39b` |
| 2.4a React shell + routing | ✅ done | `adb42de` |
| 2.4b Live timeline | ✅ done | `6341d0b` |
| 2.5 Report view | ✅ done | `a796aa5` |
| 2.6 Warnings + AC walk-through | ✅ done | `978e7d6` |

**All 22 work items are done.** Work that happened *after* the last one is in
**§After the plan** below — check there before assuming the table is the whole story.

**Cross-cutting commits** (no single item owns them): `b1946c4` closed WI-0.0's Done line and corrected the
`pymupdf4llm` page key · `a2899c4` moved every deferred note into the item that will act on it · `7bb6089` settled the
grant input as a URL rather than the local PDF.

---

## Phase 0 — Prerequisites (~2 h)

### WI-0.0 — Fix the demo pair **CORE** ⏱30m 🔒0.2, 1.4, 1.5, 1.6
> **STATUS: ✅ DONE** — `e8e821f`. Demo pair frozen:
> - **Profile** `https://basurafernando.github.io/` — Basura Fernando, 189 works, 9,082 citations, top topic 6,614 works since 2022. Verified by `backend/spikes/check_demo_pair.py`.
> - **Grant** `https://www.rgp.gov.sg/nrf-ar/crp` — NRF **Frontier** CRP (F-CRP). Target scheme chosen: F-CRP.
>   Everything is reachable from that one URL with no browser, via three layers (see `backend/spikes/probe_grant_url.py`):
>   trafilatura → 2,287 chars (objectives, schemes, eligibility); Next.js flight data → 3,090 chars
>   (**the call period, 23 Mar – 18 May 2026**, which trafilatura cannot see); linked documents → 7 PDFs
>   including `F-CRP Call Information Sheet (2026).pdf`, 21 pp / 36,717 chars, no OCR needed.
>   Also cached as `backend/fixtures/grant.pdf` so tests are hermetic.
>   ⚠️ F-CRP is **open-topic**, so `grant_alignment` scores against objectives and eligibility rather than
>   a named priority list. If a sharper alignment signal is wanted later, T-CRP publishes themes.
>
> Good pairing: a Singapore national call against an A\*STAR/NTU researcher, so eligibility genuinely applies rather than being trivially satisfied.

Nothing else is real until these two inputs are chosen and frozen.
- [x] Download one grant call to `backend/fixtures/grant.pdf` — a real PDF, multi-page, with stated eligibility and evaluation criteria
- [x] Pin one researcher profile URL as `ROIA_DEMO_PROFILE_URL` in `.env`
- [x] **Verify in the OpenAlex UI**: that researcher has **≥ 20 indexed works**, and a plausible direction query returns **≥ 15 works from 2022+**
- ✅ **Done:** both fixtures committed; the OpenAlex counts written into `backend/fixtures/README.md` *(written at WI-1.0 — the Done line had been ticked without it)*
> `demo-spec.md` §10 names "the 3 candidate directions are unusable on a niche field" as a top risk. Failing this check on day 0 costs 30 minutes; discovering it at WI-1.6 is fatal.

### WI-0.1 — Keys and environment **CORE** ⏱30m 🔒everything
> **STATUS: ✅ DONE**. Both keys live-verified. OpenAlex: 10,000 credits/day, $1/day. Gemini: **paid tier confirmed** — `gemini-3.1-pro-preview` returned valid structured output (10.5 s, thinking=high, 798 thought tokens). **Model decision: Pro for LLM #4, `gemini-3.8-flash` for #1–#3** (2.0 s vs 10.5 s; Pro is worth it on the one call that does cross-direction scoring). `.venv` rebuilt on **Python 3.12.3**; the full dependency set imports cleanly.
- [x] Free **OpenAlex** key → `openalex.org/settings/api`
- [x] Fresh **Gemini** key → `aistudio.google.com/apikey`
- [x] **Decide the LLM #4 model now.** `plan.md` §12 records that `gemini-3.1-pro-preview` has **no free tier** — every scoring call bills from request one. Either enable billing, or deliberately drop LLM #4 to Flash-class and write down the trade-off.
- [x] `python3.12 -m venv .venv` — **not** the system 3.14
- ✅ **Done:** `.env` populated and gitignored; the model decision recorded in `README`

### WI-0.2 — API spikes **CORE** ⏱1h30 🔒1.4, 1.5, 1.6
> **STATUS: ✅ DONE** — all six checks pass; no blockers. Verified live:
> - OpenAlex `group_by=publication_year` and `group_by=authorships.institutions.id` both **$0.0001**
> - `awards.funder_id` → **200**; the old `grants.funder` → **400**, confirming the 2026 rename
> - `cites:{W},from_publication_date:` → 3,307; adding `fulltext.search:` → 597 at **$0.001**, with `meta.x_query.oql` echoing the query in English for the report
> - singleton `get_work` → **free** (`cost_usd: None`)
> - Gemini `response_json_schema` on both `gemini-3.8-flash` (2.0 s) and `gemini-3.1-pro-preview` (10.5 s)
> - `pymupdf4llm` page key resolved defensively; `trafilatura` + `make_links_absolute` verified in `backend/spikes/probe_grant_url.py`
>
> ⚠️ **Caveat for WI-1.5:** OpenAlex abstract coverage is not 100% — an older seed work returned no `abstract_inverted_index` while three 2024 works returned 1,245–1,636 chars. `fetch_top_works` must over-fetch and keep the first `n` *with* abstracts.
>
> The two spikes written (`check_demo_pair.py`, `probe_grant_url.py`) cover this item; a separate `verify_apis.py` is unnecessary.
Six checks, each printing the **raw** response. Do not proceed until all six pass.

| # | Check | Assert |
|---|---|---|
| 1 | OpenAlex search + `group_by=publication_year` + an `awards.funder_id` filter | non-zero counts; `meta.cost_usd` present |
| 2 | `filter=cites:{W},from_publication_date:{d}` **and** a free singleton `get_work` | both 200; singleton costs 0 credits |
| 3 | ROR `?query.advanced=domains:"{your demo domain}"` → OpenAlex `/authors?filter=last_known_institutions.ror:https://ror.org/{id}` | **count > 0** ⚠️ fails silently otherwise |
| 4 | **The exact model LLM #4 will use**, with a real `response_json_schema` | validated object; note the latency and whether billing was required |
| 5 | `pymupdf4llm.to_markdown(backend/fixtures/grant.pdf, page_chunks=True)` → `print(sorted(c['metadata'].keys()))` | key is `page_number` **or** `page` depending on whether `pymupdf-layout` is installed — read it as `md.get('page_number') or md.get('page')` |
| 6 | `trafilatura` + `lxml.make_links_absolute` on the demo profile URL | relative hrefs resolve to 200 |

> Checks 3 and 5 are pre-verified (ROR plain `query=` → **0 hits**; the key **is `page_number`** on this machine — an earlier note here said `page`, corrected at WI-1.0). Re-run anyway — they are the two that fail *silently*. Check 4 is the one that can invalidate the model choice.

---

## Phase 1 — Backend (~14 h 45)

### WI-1.0 — Hand-authored report fixture **CORE** ⏱30m 🔒2.5
> **STATUS: ✅ DONE** — `backend/fixtures/report-sample.json`. **Every value in it is real and was retrieved live on 2026-09-05**: the three
> grant quotes are exact substrings of `backend/fixtures/grant.pdf` pages 1 / 2 / 12 (sha256 `a043080206…`, verified); the six papers are real
> OpenAlex works with their real IDs, authors, years and abstracts; every `api_query` row's `url` is a request that actually returned 200,
> and its counts and year-curves are that response. Nothing is invented — a fixture that cites papers which don't exist is the exact failure
> this product is built to prevent, and this file is what WI-2.5 renders on stage if Day 1 slips.
>
> **20 evidence rows, not ~14.** AC12 needs a `topic_trend` **and** a `citing_count` row per direction (6), and 2 papers per direction
> (rather than 1) is what makes the evidence panel look like a real report. Shape: 3 `grant_doc` (one per page, matching WI-1.4) +
> 1 `webpage` + 9 `api_query` + 6 `paper`, ids `e1`–`e20`. `e1`–`e5` are shared; `e6`–`e10` / `e11`–`e15` / `e16`–`e20` belong to D1 / D2 / D3
> and **no direction cites another's rows** — that is WI-1.6c's per-direction-catalogue rule, already frozen here.
>
> **Contract decisions WI-1.6c must reproduce and WI-2.5 can build against:**
> - `problem_statement` and `evidence_backed_gap` are **`{text, evidence_ids}`** (`plan.md` §5 `DirectionSection`), so WI-2.5 can hang chips
>   beneath each field as its checklist requires. `key_strengths` / `key_weaknesses` are plain `list[str]` — no chips.
> - A direction also carries `rank`, `overall`, `confidence` (`high|medium|low`), `thin_evidence: bool` (AC10b), a direction-level
>   `evidence_ids`, and `scores` with **all 9 criteria in `demo-spec.md` §6.4 order**, two of them `null`.
> - All 7 scored criteria use **`provenance: "judged"`** — §6.4 shows `"judged"` and §5 step 8 has LLM #4 emit all nine. `plan.md` §7.1 would
>   make `evidence_strength` and `feasibility` `"computed"`; that is post-demo. Keep the `Literal["computed","judged"]`.
> - **`overall` is rounded to 2 dp.** `compute_ranking()` (WI-1.7) must round identically or the golden test fails on float noise.
> - `weights` ships **all 9 keys flat at 1/9**; renormalising over the scored seven is `compute_ranking`'s job, so `overall` is exactly the
>   mean of the 7 values. The browser slider (AC6) uses the same formula.
> - `paper.url` is the **OpenAlex work URL**, not the DOI — it is the record we actually fetched, which keeps AC4 unambiguous, and the
>   OpenAlex page links out to the DOI anyway. `summary` is the abstract truncated to ≤400 chars per §6.1.
> - `grant_doc.url` is the ZIP the PDF came from
>   (`…/ee9b60cc-1ee9-4444-a2ba-327bd9b7fe56.zip?download=`) — that is the real provenance; the PDF has no standalone URL.
> - Top level also carries `run_id`, `generated_at`, `inputs`, `identity`. **`identity` is a judgement call** — `report.md` needs the
>   "Analysing X at Y — unverified" banner and a standalone `report.json` has no other source for it. If you'd rather it lived only on the
>   `identity.resolved` event, drop it here and in WI-1.7's template.
>
> **Numbers WI-1.6c and WI-1.7 can lean on.** Overalls **7.57 / 6.57 / 5.57** → spread **2.00** (WI-1.6c needs ≥1.5 ✅); **all 7** scored
> criteria have a per-criterion range ≥3 (needs ≥4 ✅); and **4 of 7** single-criterion weightings re-order the cards, so the sliders visibly
> move — this file is a working target for the C3 claim, not just a shape.
>
> **How it was verified.** A scratchpad invariant checker (not committed — there is no `roia` package or pytest config until WI-1.1)
> asserted: AC2 3 directions; AC3 ≥2 ids per direction and every cited id resolving; AC4 provenance by `source_type`, incl. each `paper`
> pointing at an `api_query` with a logged 200; AC11 ≥1 `paper` + ≥1 `grant_doc` per direction; AC12 each gap citing its own trend and
> citing rows; per-direction citation isolation; grant quotes exact-substring against the real PDF; every `summary` ≤400 chars; no
> `url`/`source_title`/`link` key and no URL string anywhere inside the `directions` block; and stored `overall` == recomputed.
> **WI-1.7 should re-run these as real pytest tests** with this file as the golden input.
>
> ⚠️ **Not done, by the Done line's own wording:** it has not been validated against the Pydantic models, because they don't exist yet.
> Validate at WI-1.2 (`Evidence`) and WI-1.6c (`Direction`, `CriterionScore`) and fix the fixture, not the models, if they disagree.
>
> ✏️ Two stale notes found while working, **both since fixed**: **(a)** WI-0.2 asserted the `pymupdf4llm` page key "is `page`" — on this
> machine `to_markdown(page_chunks=True)` returns **`page_number`** and no `page`; the line is corrected, and WI-1.4's defensive
> `md.get("page_number") or md.get("page")` covers either. **(b)** WI-0.0's Done line claimed the OpenAlex counts were written into
> `backend/fixtures/README.md`, which did not exist; it does now and carries the counts, the demo pair and every fixture in the directory.
Write `backend/fixtures/report-sample.json` **by hand**, before any code:
- [x] 3 directions, each with `problem_statement`, `evidence_backed_gap`, `confidence`, 9 `CriterionScore` objects `{value, provenance, evidence_ids, rationale}`
- [x] ~14 evidence rows including **≥ 1 `paper` and ≥ 1 `grant_doc` per direction**
- [x] `competitive_differentiation` and `collaboration_potential` set to `null`
- ✅ **Done:** it validates against the Pydantic models once WI-1.6 exists
> This is three things at once: **the frozen contract** WI-1.6's schemas must produce, the golden input for WI-1.7's ranking test, and **the thing that unblocks WI-2.5 if Day 1 slips.** The event JSONL does not contain a report — without this, the biggest frontend item has nothing to render.

### WI-1.1 — Skeleton + config **CORE** ⏱1h15 🔒all
> **STATUS: ✅ DONE** — `backend/pyproject.toml`, `backend/roia/` (11 modules), `backend/tests/` (15 tests). `pytest` green, `ruff check .` clean,
> `mypy roia` clean.
>
> **The layout is real files, not stubs.** `config.py` is the only one with code; the other nine carry a docstring naming the work item
> that owns them and the one or two constraints that are easy to get backwards there (e.g. `openalex.py` records that
> `search_literature` mints `api_query` and only `get_work` mints `paper`). `backend/tests/test_layout.py` imports all ten and asserts each has
> that docstring, so a module nobody created — or one with a syntax error committed mid-item — fails immediately rather than at the next
> item's first import.
>
> **`config.py`** — `Settings` + `get_settings()` (`lru_cache`, so importing `roia.config` never touches the environment and a test can
> clear it). `env_prefix="ROIA_"`, but the three **vendor credentials accept both spellings** via `AliasChoices`:
> `GEMINI_API_KEY` *and* `ROIA_GEMINI_API_KEY`, same for `OPENALEX_API_KEY` / `OPENALEX_MAILTO`. `backend/.env.example` documents them
> unprefixed because that is what the vendors call them and what people paste in. **Every field defaults to `""` / `False`** — a missing
> key surfaces where it is used, never at import, so the suite runs without credentials.
>
> Beyond the four fields the checklist named, `config.py` also reads **`model_fast`, `model_smart` and `dev`**. These are not new scope:
> all three already exist in `backend/.env.example` from WI-0.1, and without fields they would be documented-but-unread. Defaults hold WI-0.1's
> decision (`gemini-3.8-flash` for LLM #1–#3, `gemini-3.1-pro-preview` for #4) and a test asserts them, so a future edit cannot silently
> change models.
>
> **Pins are exact `==`**, at the versions WI-0.1/0.2 verified live — a transitive minor bump the morning of a demo is not a risk worth
> carrying. Dev extras: `pytest==9.0.1`, `ruff==0.15.4`, `mypy==1.19.0`. `pythonpath = ["."]` in the pytest config, so `import roia` works
> with **no editable install needed**.
>
> **`addopts = -m 'not live' -q`, and it was verified rather than assumed:** with a temporary `@pytest.mark.live` test in the suite, the
> default run reported `16 passed, 1 deselected` and `pytest -m live` reported `1 passed, 16 deselected`. Markers `live` and `e2e` are
> registered, so `-W error::pytest.PytestUnknownMarkWarning` stays clean.
>
> **ruff excludes `backend/spikes/`.** Under our rule set it reports **23 errors** there (long lines, grouped imports, named lambdas). Those are
> WI-0.0's and WI-0.2's committed verification scripts, deliberately compact; rewriting them to satisfy a linter added afterwards is the
> "refactor code outside your work item" anti-pattern. Un-exclude if a spike is ever promoted into `backend/roia/`. Settings: line-length 100,
> `select = E,F,W,I,UP,B,SIM`; mypy `disallow_untyped_defs = true` with `ignore_missing_imports` for `pyalex`, `trafilatura`,
> `pymupdf4llm` and `sse_starlette`, which publish no stubs.
>
> ✏️ **Two naming questions settled — don't re-open them.** (a) WI-1.6a's checklist says "`gemini.py`"; WI-1.1's layout says `llm.py`.
> **`llm.py` is the file that exists** — put `structured()` and `serialize_catalogue()` there, don't create a second module.
> (b) WI-1.4b's `probe()` has no `probe.py` in the layout, so it lands in **`ingest.py`**. Both are noted in the modules' own docstrings.
>
> ⚠️ **For a human, before the first live run:** `.env` still carries the placeholder `OPENALEX_MAILTO=you@example.com`. WI-1.5 puts that
> address in the User-Agent for OpenAlex's polite pool — set a real one. Everything else in `.env` reads correctly through `get_settings()`
> (both keys present, `demo_profile_url` pointing at the frozen WI-0.0 profile).
>
> Deliberately **not** added, so the next agent doesn't think they are missing: no `__main__.py` (WI-1.7's CLI), no `pytest-asyncio`
> (WI-2.2), no `python-multipart` (WI-2.1's upload endpoint, which is a PLUS bullet).
- [x] Layout: `backend/roia/{config,evidence,events,ingest,openalex,llm,llm_schemas,pipeline,ranking,report}.py`, `backend/tests/`, `backend/spikes/`, `backend/fixtures/`
- [x] Port `config.py` from the template; add `gemini_api_key`, `openalex_api_key`, `openalex_mailto`, `demo_profile_url`
- [x] Pin: `google-genai`, `pyalex`, `httpx`, `trafilatura`, `lxml`, `pymupdf4llm==1.28.2`, `sse-starlette`, `jinja2`, `tenacity`, `pydantic-settings`
- [x] `ruff` + `mypy` + `pytest`; **`addopts = -m "not live"`** so network tests stay out of the default run
- ✅ **Done:** `pytest` green; `ruff check` clean

### WI-1.2 — Evidence store `[AC4, AC5, AC10a, AC10b]` **CORE** ⏱1h15 🔒1.4, 1.5, 1.6
> **STATUS: ✅ DONE** — `backend/roia/evidence.py` + `backend/roia/llm_schemas.py`, **24 tests** (suite now 39). `pytest`, `ruff check .`,
> `mypy roia` all clean.
>
> **`EvidenceStore.mint(**fields) -> str`** returns `e1, e2, …`. Three behaviours worth knowing before you call it:
> - **`Evidence` is `extra="forbid"`.** A misspelt kwarg (`sha_256=`, `status=`) raises instead of being silently dropped — that is
>   exactly how a row would lose its provenance and quietly fail AC4.
> - **A rejected mint does not burn an ID.** The counter advances only after the row validates, so the sequence has no gaps. Verified.
> - **`mint()` raises rather than warns.** A malformed row is *our* bug, not an external failure, so the AC9 "catch and continue" rule
>   does not apply here. Retrieval code must not pass it junk.
>
> **AC4 is enforced in code, not trusted.** `Evidence` refuses `grant_doc` without `page`+`sha256`, `webpage` without `url` or with
> `http_status != 200`, `api_query` without `url`+`http_status`, `paper` without `derived_from`. `mint()` goes one step further and
> checks the `derived_from` target really is an `api_query` **with a logged 200**, which the model alone cannot see. WI-1.5: a paper
> derived from a 429'd query, or from a `grant_doc`, will raise.
>
> **`summary` is truncated at 400 chars, not rejected** (§6.1's cap). An OpenAlex abstract is routinely 1,200–2,200 chars; killing a run
> four minutes in over a chip-hover length rule would be self-inflicted. Trim is at a word boundary with an ellipsis, the same as the
> WI-1.0 fixture. **WI-1.5 therefore does not need to pre-truncate abstracts.**
>
> **AC5 is structural, not a convention.** `LLMOutput.__pydantic_init_subclass__` raises `TypeError` if a subclass declares `url`,
> `source_title` or `link` — at *class definition time*, so such a schema cannot even be imported. Inherited fields count.
> `llm_output_models()` walks subclasses **recursively** (the checklist's `LLMOutput.__subclasses__()` would miss anything under
> `CitesEvidence`, which is most of WI-1.6c).
> ⚠️ **Be honest about how strong the walk is today:** the only non-test `LLMOutput` subclass is `CitesEvidence`, so the "subclass set is
> non-empty" guard is currently satisfied partly by the test's own models. What actually holds AC5 right now is the definition-time
> `TypeError`, which is tested directly. The walk gains real teeth as WI-1.6a/b/c land.
>
> 🔴 **WI-1.6a will find a failing test, on purpose.** AC5's third clause ("every call in `llm.py` passes an `LLMOutput` subclass") has
> nothing to check yet, so rather than write a test that passes vacuously,
> `test_ac5_every_structured_call_in_llm_py_passes_an_llm_output_subclass` is an **AST tripwire**: it asserts `llm.py` does not yet
> define `structured`, and fails the moment it does. Verified both ways — a bare `def structured` fails it, and a call site passing a
> non-`LLMOutput` fails it by name. **WI-1.6a: extend that test to walk your real call sites; do not delete it.**
>
> **AC10a** — the `mode="after"` validator on `CitesEvidence` drops unresolvable IDs and calls `warn(unresolvable_evidence_id, …)`.
> Drops, never raises: one hallucinated token four minutes in should cost a chip, not the stage. It recurses through nested models, and
> **validating without a `CitationContext` is a no-op**, so fixtures and tests can build these models freely.
>
> **AC10b** — `call_with_evidence_floor(call, warn=…)` runs the call, retries **once** if any citing node came back under-cited, and
> keeps the retry **only if it is strictly better**, so a retry can never worsen the result. Returns `(output, thin_nodes)`; each
> surviving thin node emits `warning{code: thin_evidence}`. A clean first call costs no second round trip.
>
> ✏️ **Decisions the next items inherit:**
> - **The floor is per model**, not global: `CitesEvidence.evidence_floor: ClassVar[int] = 2` (AC3), and a subclass overrides it.
>   **WI-1.6c must set `evidence_floor = 1` on `CriterionScore`** (`plan.md` §7.2 says judged criteria need ≥1) or every score will be
>   flagged thin.
> - **Warnings are an injected `WarnFn = Callable[[str, str], None]`, not `run.emit`.** `events.py` is WI-1.3 and this module must not
>   depend on it. **WI-1.6d wires `run.emit` into the `warn=` slot** of `CitationContext` and `call_with_evidence_floor`.
> - `thin_evidence` is **not** a field on any LLM schema — Python owns it. `call_with_evidence_floor` hands back the thin nodes and
>   WI-1.6c sets the flag on its report-side model, matching `backend/fixtures/report-sample.json`.
> - Codes live in `evidence.py` as constants: `UNRESOLVABLE_EVIDENCE_ID`, `THIN_EVIDENCE`. `EVIDENCE_FLOOR = 2` and
>   `SUMMARY_MAX_CHARS = 400` are contract constants, deliberately **not** in `config.py` — they are ACs, not tunables.
> - `resolve_ids` **dedupes, preserving order** — a model citing `e4` twice meant it once.
>
> Deliberately left out: `EvidenceStore.of_type()` (no caller yet — WI-1.5 can add it when AC11 needs the paper count) and any
> concrete LLM schema (WI-1.6a/b/c own those).
- [x] `Evidence` model exactly as `demo-spec.md` §6.1 (incl. `derived_from`, `summary`, `sha256`, `http_status`)
- [x] `EvidenceStore.mint(**fields) -> str` returning `e1, e2, …` sequential
- [x] `resolve_ids(ids) -> (kept, dropped)`; a `mode="after"` validator mixin that drops unknown IDs and emits `warning`
- [x] **`class LLMOutput(BaseModel)` in `llm_schemas.py` — every LLM output model subclasses it**
- [x] **Test (AC5):** `for m in LLMOutput.__subclasses__(): assert not ({'url','source_title','link'} & set(m.model_fields))`, **plus assert the subclass set is non-empty** (guards a vacuous pass), plus assert every call in `llm.py` passes an `LLMOutput` subclass. ⚠️ `Evidence` is deliberately out of scope — it *has* a `url` by design
- [x] **Test (AC10a):** an output citing `e999` has it removed + warning emitted
- [x] **Test (AC10b):** dropping below 2 IDs triggers one retry, then `thin_evidence`
- ✅ **Done:** 4 tests green

### WI-1.3 — Event emitter + fixture writer `[AC7]` **CORE** ⏱30m 🔒1.6d, 2.2
> **STATUS: ✅ DONE** — `backend/roia/events.py`, **16 tests** (suite now 149 hermetic + 7 live). `pytest`, `ruff check .`,
> `mypy roia` all green. `backend/fixtures/run-000.jsonl` written: **25 events** covering 9 of the 10 types (everything but
> `run.failed`, which a successful run does not emit).
>
> **`Run.emit(type, payload=None, /, **fields)` takes both shapes** — a payload dict *and* keywords — because the slots
> it plugs into use both. `OpenAlexClient(emit=…)` passes `(type, payload)`; pipeline code reads better as
> `run.emit("stage.started", stage="ingest")`. One method, no adapters. Payload fields sit at the **top level** of the
> event (`extra="allow"`), not under a `payload` key, which is what §6.3 specifies and what SSE consumers expect.
>
> 🔑 **`run.warning` drops straight into every module already built.** Its signature is exactly
> `evidence.WarnFn = Callable[[str, str], None]`, and a test proves it end to end by handing `warn=run.warning` to
> `ingest_profile` against a 404 and reading the warning back off the run. **WI-1.6d wires:**
> `ingest_*(…, warn=run.warning)` · `OpenAlexClient(store, warn=run.warning, emit=run.emit)` ·
> `structured(…, warn=run.warning)` · `CitationContext(store=…, warn=run.warning)` ·
> `call_with_evidence_floor(call, warn=run.warning)`. No glue code needed anywhere.
>
> ✏️ **Two context managers beyond the typed constructors, and they earn it.** `with run.stage(name)` and
> `with run.tool(name, args)` emit the started/finished pair with **real elapsed ms** and close in a `finally`. The `ms`
> field cannot be produced correctly by a hand-written call site without timing boilerplate that will drift, and a
> missing `stage.finished` leaves the UI spinning on a step that already died — tested with a raising stage.
> `run.tool()` yields a list to append minted evidence IDs to, which becomes `tool.finished{evidence_added}`.
>
> **Failure behaviour** — a JSONL write that raises `OSError` (full disk, unwritable path) **drops file logging and
> keeps going**. The in-memory list is what SSE and the snapshot read from, and there is no one to warn about the
> emitter: that warning would be another event down the same path. Tested. A `Run` also **truncates its file on
> construction**, so a re-run never appends to a stale log.
>
> ⚠️ **`emit()` does not validate the type string.** A typo like `"stage.startd"` produces an event nobody renders.
> The typed constructors are the normal path and a test asserts they cover all ten §6.3 types; `emit()` stays the
> permissive escape hatch. If that bites, add the check there.
>
> `read_jsonl(path)` loads a recorded run back — **WI-2.3 replays these**, and a round-trip test asserts what was
> written loads identically. `run.warnings()` filters the log for WI-2.1's snapshot and WI-2.6's alerts.
>
> ⚠️ `backend/fixtures/run-000.jsonl` is **hand-built, not a real run** — WI-1.6d produces `run-001.jsonl` from the live
> pipeline and that is the one AC7 counts. run-000 exists so WI-2.3 and WI-2.4b have something to render before a real
> run is available.
- [x] `Run.emit(type, **payload)` → appends `{seq, ts, type, …}` to a list **and** a JSONL file
- [x] Full event vocabulary from §6.3 as typed constructors
- ✅ **Done:** a fake 10-event run writes `backend/fixtures/run-000.jsonl`

### WI-1.4 — Ingestion `[AC4, AC9]` **CORE** ⏱3h 🔒1.6
> **STATUS: ✅ DONE** — `backend/roia/ingest.py`, **27 tests** (suite now 66 hermetic + 2 live). `pytest`, `pytest -m live`,
> `ruff check .`, `mypy roia` all green.
>
> **The three layers work end to end on the real call, and the live tests prove it.** `pytest -m live` asserts the F-CRP
> **call period (23 Mar 2026)** is recovered — it exists *only* in the Next.js flight payload — **and** that "breakthrough
> potential" is recovered, which exists *only* inside a PDF inside a ZIP. Either assertion failing means a layer regressed.
> Hermetic equivalents run against `backend/fixtures/crp-page.html` + `backend/fixtures/profile-page.html`, recorded 2026-09-05.
>
> **Public API** — `ingest_source(src, policy, store, *, warn=None, client=None, min_interval_s=1.0) -> DocumentSet`, with
> `ingest_grant` / `ingest_profile` as thin wrappers, plus `extract_identity(html, url, *, warn=None) -> (name, domain)`,
> and `flight_text` / `embedded_payloads` / `rank_links` exposed because WI-1.4b's detectors will want them.
> `DocumentSet` carries `final_url`, `seed_html`, `artefacts[]`, `warnings[]`, with `.text` and `.evidence_ids` derived —
> **WI-1.4b: this is the object to reuse so ingestion is not repeated.**
>
> ✏️ **Two provenance decisions worth knowing, both about not lying in the store:**
> - **A local file is never minted as a `webpage`.** Nothing was fetched, so there is no honest `http_status`, and AC4 wants a
>   webpage row to *prove* a successful fetch. A local HTML file is recorded like a document instead: `grant_doc`, `page=1`,
>   with the file's real sha256. A fetched page carries its real status. This means `--grant backend/fixtures/grant.pdf` produces
>   `file://` URLs in `Evidence.url` — valid for AC13, but ugly in `report.md`.
>   ✅ **Resolved by the user (2026-09-05): demo and CLI runs pass the grant as a URL**, `https://www.rgp.gov.sg/nrf-ar/crp`.
>   Measured on that path: **55 evidence rows (1 `webpage` + 54 `grant_doc`), every URL `https://`, 18.6 s**, with both the
>   call dates and the evaluation criteria recovered. `backend/fixtures/grant.pdf` stays the hermetic test fixture and the offline
>   fallback if rgp.gov.sg is unreachable on the day.
> - **PDFs always mint `source_type="grant_doc"`**, whichever policy fetched them — the four source types in §6.1 have no
>   better slot, and the profile policy does not follow document links anyway.
>
> ✏️ **robots.txt is honoured for links we chose to follow, not for the URL the user handed us.** Asking permission to read
> the page someone explicitly pasted is the wrong reading of robots. Both demo hosts allow everything (`rgp.gov.sg` returns
> `Allow: /`; `basurafernando.github.io` has no robots.txt, and a 404 is treated as permission).
>
> **Throttle is 1 req/s per host**, `min_interval_s=0` in tests. A full grant ingest is ~8 requests, so ~8 s of politeness
> inside the 6-minute AC1 budget.
>
> **Nothing raises at the caller (AC9).** Verified for a 404, a connection error, a missing local file, a corrupt PDF, a bad
> ZIP, an empty 200 (`lxml.html.fromstring("")` raises `ParserError` — that was a real bug, now caught), a trafilatura
> failure, and a non-integer page number. `_Session.mint` wraps `EvidenceStore.mint`, so a row that cannot satisfy AC4
> becomes `warning{evidence_rejected}` rather than ending the run. Warning codes: `fetch_failed`, `unsupported_type`,
> `thin_extraction`, `identity_inputs_missing`, `robots_disallowed`, `evidence_rejected`.
>
> ⚠️ **`warn` is an injected `WarnFn`, still optional** — `run.emit` does not exist until WI-1.3. Warnings are *also*
> recorded on `DocumentSet.warnings`, so WI-1.4b can read them without wiring a callback.
>
> 🔧 **Two dependency changes:** `pymupdf==1.28.2` is now pinned explicitly — `to_markdown` will not take bytes or a file
> object, only a `Document`, and everything here arrives as bytes (an HTTP body, or a ZIP member in memory). And
> `lxml-stubs==0.5.1` was added to the `dev` extra rather than an `ignore_missing_imports` override; it immediately caught
> `make_links_absolute` being absent from the annotated return type, which is why `_parse_html` casts.
>
> **Thin extraction** fires below 600 chars recovered or a text/HTML ratio under 1% (`demo-spec.md` §5) — that is the signal
> that a page renders in the browser and we should say so rather than return silence.
- [x] `ingest_grant(src)` and `ingest_profile(url)` are **thin wrappers** over one `ingest_source(src, policy)`. PDF → `pymupdf4llm.to_markdown(page_chunks=True)`, one evidence row **per page** with `sha256` and `md.get("page_number") or md.get("page")`. URL → `httpx` → `lxml` → **`make_links_absolute(final_url)`** → `trafilatura.extract(...)`
- [x] **One self-detecting `ingest_source(url_or_path, policy)`** used for *both* inputs — the user never declares the type. Dispatch on **`Content-Type`, never extension** (`…​.pdf?download=` breaks `endswith`): `text/html` → L1–L3; `application/pdf` → page chunks; `application/zip` → unzip in memory, recurse into each PDF; else `warning{unsupported_type}`
- [x] **Port `backend/spikes/probe_grant_url.py` verbatim** for the HTML layers: L1 trafilatura; **L2 embedded payload** — Next.js App Router `self.__next_f.push([1,"…"])` → `"wysiwyg"` blocks (where the CRP dates live and trafilatura finds nothing), plus `__NEXT_DATA__`, `window.__NUXT__`, JSON-LD; L3 harvest links from **both** the DOM and the L2 payload, recurse depth 1
- [x] Rank links by **type** (zip → pdf → other), *not* keyword — rgp.gov.sg hrefs are opaque UUIDs so text ranking scores nothing
- [x] Policy: grant = document links, 6 artefacts, unzip yes. profile = same-site `/publication|research|people/`, 2 artefacts, unzip no
- [x] Merge every layer. **No single source is complete:** dates page-only, eligibility/evaluation/budget PDF-only
- [x] **`extract_identity(html, url) -> (name, domain)`** — name from `og:title` / first `<h1>` / `<title>`, trailing role text stripped; domain from the URL host. On failure → `warning{code: identity_inputs_missing}`
- [x] `ingest_profile(url)` — seed page + up to 2 links matching `/publication|/research|/people`; robots.txt honoured; 1 req/s
- [x] Any fetch failure → `warning{code}` + continue **(AC9)**
- [x] ⚠️ **Carried over from WI-1.2:** there is no `run.emit` yet (WI-1.3). Take a `warn: WarnFn | None` parameter — `Callable[[str, str], None]`, `(code, message)` — the same injection `CitationContext` uses. WI-1.6d wires the real emitter in.
- [x] ⚠️ **Carried over from WI-1.2:** `EvidenceStore.mint()` **raises** on a row that fails AC4 (`grant_doc` needs `page`+`sha256`), and `Evidence` is `extra="forbid"` so a misspelt kwarg raises too. Don't let a mint failure escape into the pipeline.
- [x] ⚠️ **Carried over from WI-1.1:** on this machine `to_markdown(page_chunks=True)` returns **`page_number`**, not `page` — the defensive read above is not optional.
- [x] **Tests:** `backend/fixtures/grant.pdf` mints N rows with pages 1..N; a relative href resolves absolutely; the demo profile fixture yields the expected `(name, domain)`; a 404 emits a warning and does not raise
- ✅ **Done:** 4 tests green
> `extract_identity` is on the critical path — step 2b cannot run without a name, and no other step produces one.

### WI-1.4b — Pre-flight probe + detectors `[AC14, AC9]` **CORE** ⏱1h 🔒2.1, 2.4a
> **STATUS: ✅ DONE** — `probe()` and the four detectors in `backend/roia/ingest.py`, **16 tests** (suite now 82 hermetic + 3 live).
> `pytest`, `pytest -m live`, `ruff check .`, `mypy roia` all green.
>
> **AC14 holds, measured not assumed.** The live test asserts the real pair completes in **< 20 s** — measured **17.5 s**
> (grant 17.1 s over 8 artefacts, profile 0.4 s) — and that both call periods are detected. ⚠️ **The margin is ~2.5 s.**
> About **8 s of that 17.5 s is the 1 req/s throttle**, so if AC14 ever goes red on a slower network that is the first lever
> to pull — parallelise or relax the throttle for the CDN host, **not** the artefact count, since the run reuses these
> documents.
>
> **Zero LLM calls, demonstrated three ways:** the mock transport records every request and the hosts touched are exactly
> the two inputs plus the document CDN; no URL contains `googleapis`; and an AST check asserts `ingest.py` imports nothing
> that could reach a model. The probe *cannot* call an LLM, rather than merely not doing so.
>
> **The four detectors, and what they actually do on the demo pair:**
> | Detector | Rule | Result |
> |---|---|---|
> | `multiple_call_periods` | ≥2 distinct `… Grant Call Period: …` | **fires** — CRP36 (14 Sep–9 Nov 2026) and 2026 Frontier CRP (23 Mar–18 May 2026) |
> | `multiple_schemes` | ≥2 scheme acronyms near a scheme-signal phrase | **fires** — F-CRP, T-CRP, CRP36 |
> | `thin_profile` | profile text < 600 chars | silent (24k chars) |
> | `no_eligibility_found` | no `eligib` anywhere readable | silent — the tool read the PDFs, which is the point |
>
> ✏️ **The scheme detector is precision-first, deliberately.** A bare acronym scan over this corpus returns PI, NRF, NUS,
> NTU, AI and TRL — noise that would produce a pointless question. The rule is: a **hyphenated or number-suffixed**
> acronym within 80 chars of `sub-category` / `funding scheme` / `scheme` / `Grant Call Period` / `Call-for-Proposals`.
> That yields exactly F-CRP, T-CRP, CRP36, and nothing at all on the profile page. **A scheme named by a plain
> unhyphenated acronym will be missed** — acceptable, because skipping defaults to "analyse all of them", which is the
> safe direction to be wrong in.
>
> **Answers are evidence-bearing, not a side channel.** Every `ProbeOption` carries the `evidence_ids` of where it was
> detected, attributed to the **page** it was found on: `_read_pdf` writes a `[p.N]` marker ahead of each page, so a match
> offset resolves back to that page's own `grant_doc` row rather than to "the PDF". `resolve_answers()` applies the
> default with `answered=False` when a question is skipped, and **falls back to the default for any value we never
> offered**, so a client cannot inject one. `answers_brief()` renders the block that goes into LLM #1's prompt.
>
> **`ProbeResult.grant` / `.profile` are `Field(exclude=True)`** — they hold the full `DocumentSet`s (~100k chars live) so
> the run can reuse the ingestion, while `model_dump()` returns exactly `{probe_id, detected, questions, warnings}`. A
> test asserts the JSON payload stays under 20 KB and carries no document text. `probe_id_for(grant, profile)` is a stable
> sha256 prefix, so WI-2.1's "cached by input hash" is a dict lookup.
>
> **AC9 arrives earlier now:** an unreachable profile URL becomes a `thin_profile` question *before* the run starts, with
> `fetch_failed` in `result.warnings`. Tested.
- [x] `probe(grant_src, profile_url) -> ProbeResult{probe_id, detected, questions[]}` — runs `ingest_source` on both inputs, **zero LLM calls**, target < 20 s
- [x] Four deterministic detectors, each with a fixed question, fixed options and a defined default: `multiple_call_periods`, `multiple_schemes`, `thin_profile`, `no_eligibility_found`
- [x] Answers are passed to `run_pipeline` and recorded as evidence-bearing inputs, not a side channel
- [x] ⚠️ **Never ask what retrieval can answer** — the tool reads all 7 CRP PDFs itself; it only asks which call the user is applying to
- [x] ⚠️ **Carried over from WI-1.4, measured:** ingesting the CRP URL pulls **54 `grant_doc` rows across *both* schemes** — CRP36 (call 14 Sep – 9 Nov 2026) and F-CRP (23 Mar – 18 May 2026) — because both ZIPs are linked from the one page. That is exactly what `multiple_call_periods` and `multiple_schemes` must disambiguate, and WI-0.0 froze **F-CRP** as the target. Without the probe, LLM #1 sees two calls and cannot tell which one the applicant means.
- [x] Reuse the probe's `DocumentSet` in the run so ingestion is not repeated
- [x] ⚠️ **Carried over from WI-1.4:** `DocumentSet` already carries `warnings[]`, `seed_html`, `final_url` and `.text` — read detections off it, don't re-fetch. `flight_text()`, `embedded_payloads()` and `rank_links()` are exported for the detectors. Pass `min_interval_s=0` in tests or each fetch costs a second.
- [x] ⚠️ **Carried over from WI-1.1:** the layout has no `probe.py` — `probe()` lives in **`ingest.py`**.
- [x] **Test (AC14):** the CRP URL yields ≥1 question detecting **both** call periods, no LLM call is made, and a chosen answer reaches the grant brief
- ✅ **Done:** test green; probe returns in < 20 s

### WI-1.5 — OpenAlex client `[AC4, AC11, AC12]` **CORE** ⏱2h30 🔒1.6d
> **STATUS: ✅ DONE** — `backend/roia/openalex.py` (`OpenAlexClient`), **23 tests** (suite now 103 hermetic + 5 live).
> `pytest`, `pytest -m live`, `ruff check .`, `mypy roia` all green.
>
> **API** — one class, constructed per run: `OpenAlexClient(store, *, warn=None, emit=None, client=None, settings=None,
> min_interval_s=0.1)`. Methods: `resolve_author(name, domain, *, profile_text="")`, `fetch_author_works`,
> `search_literature`, `fetch_top_works(refs, n=4)`, `topic_trend(query, since_year)`, `citing_count(work_id, since)`.
> Models: `WorkRef` (a search hit — id, title, year, citations, `derived_from`), `AuthorMatch`, `Measure(value, detail,
> evidence_id)`.
>
> ⚠️ **`fetch_top_works` takes `refs`, not `direction`** — the `Direction` model does not exist until WI-1.6b/c. Pass that
> direction's own `WorkRef`s; each already carries the `api_query` row it came from, so AC4 holds without extra plumbing.
>
> 🔴 **Two deliberate readings of the checklist. Both are defensible; both are worth a human glance.**
> 1. **`get_work` does not mint its own `api_query` row.** "Every call mints an `api_query` row" is applied to the *list*
>    calls that consume credits; each `paper` row is `derived_from` the **search query that surfaced it**. That is what
>    `backend/fixtures/report-sample.json` freezes (papers derive from `e6`/`e11`/`e16`), it keeps AC4 satisfied, and it avoids 12
>    contentless "GET /works/W…" rows inflating the Sources counter. The alternative — a row per singleton — is more
>    literal but noisier.
> 2. **Implemented with `httpx`, not `pyalex`.** `demo-spec.md` §5 Stack says "OpenAlex via `pyalex`", but AC4 needs the
>    **exact request URL** and the raw `meta.cost_usd` in the evidence row, and `pyalex` builds and hides both. Both WI-0.2
>    spikes already used `httpx` directly. `pyalex` stays pinned but unused — **drop it from `backend/pyproject.toml` or adopt it
>    deliberately**, don't leave the question open.
>
> **AC11 is real, and the fixtures prove why it needed care.** Recorded live: **3 of the 15 hits** for the demo query have
> **no `abstract_inverted_index` at all** (ranks 11, 12, 14 — 20% of a real page). Minting those as papers would claim a
> reading that never happened, and taking the top *n* blind would silently under-deliver. `fetch_top_works` therefore
> considers **4× the requested count** and keeps the first *n* that actually have an abstract; a test asks for 12 from that
> page and gets exactly 12. A guard test asserts those three are still abstract-less, so the hazard test cannot quietly
> stop proving anything if OpenAlex backfills them. The live test mints **≥12 distinct paper rows** across 3 directions.
>
> **AC4** — every list call mints an `api_query` row with the full request URL and the status. **The API key is stripped
> from that URL**, tested: a leaked credential in a shareable report is worse than a missing link. Every `paper` row sets
> `derived_from`, and `EvidenceStore.mint` independently refuses one that does not point at a 200-logged `api_query`.
>
> **AC12** — `topic_trend` returns `value` = total works in the window with the **year curve in `detail`**
> (`"Works per year: 2019 11, 2020 15, …"`); `citing_count` returns the count since a date. Both return
> `Measure(value=0.0, evidence_id=<the failed query's row>)` rather than raising or indexing into an empty list.
>
> **Identity** — ranked on `55·log(works) + 30·topic-overlap + 15·institution-match`, ported from `check_demo_pair.py`.
> `last_known_institutions.ror` is **scoring only, never a filter**. `profile_text` is a new keyword argument and supplies
> the topic-overlap term — **pass `DocumentSet.text` or that 30 points is dead**. Institution comes from a ROR lookup by
> domain, which returns nothing for `basurafernando.github.io` (a personal domain has no ROR record), so on the demo pair
> the ranking rests on works + topic overlap; the search returns exactly one candidate, so `margin` is 0.0 and that is
> correct, not a bug. An empty name from `extract_identity` returns `None` + `warning{author_unresolved}` and mints
> nothing.
>
> **Resilience** — `tenacity` retries 429 and 5xx three times with exponential backoff (both paths tested: a 503 gives up
> and warns after 3 attempts; a single 429 succeeds on the second). Throttle is **0.1 s (10 req/s, the polite-pool
> limit)** — *not* ingestion's 1 req/s, which would cost ~20 s of the AC1 budget for ~20 calls. Malformed responses
> (missing `id`, `meta: null`, a group with no `count`) are tested and degrade rather than raise.
>
> 🔧 **`get_work` now sends `select=`** for the six fields we read: a full work record is ~25 KB of locations, references
> and yearly counts, ~5 KB selected. 12 papers per run, so ~240 KB saved and the fixtures stay small.
> Also added `EvidenceStore.of_type()` (AC11's paper count has a caller now).
- [x] `resolve_author(name, domain)` — **port `backend/spikes/check_demo_pair.py` step 4 verbatim.** Query by name only; rank on `55·log(works) + 30·topic-overlap + 15·institution-match`. ⚠️ **`last_known_institutions.ror` is a scoring signal, NOT a filter** — verified live, filtering on it excluded a 417-work researcher and returned 2-work stubs. Emit `identity.resolved{confidence:"unverified", margin}`
- [x] ⚠️ **Carried over from WI-1.4:** `extract_identity()` supplies `(name, domain)` and returns `("", domain)` + `warning{identity_inputs_missing}` when the page offers no name — **handle the empty name**, don't assume one. On the demo pair it yields `("Basura Fernando", "basurafernando.github.io")`.
- [x] `fetch_author_works(author_id, limit=40)`
- [x] `search_literature(query, from_year, limit=15)` → `WorkRef`s. ⚠️ **mints `source_type="api_query"`, NOT `"paper"`**
- [x] **`fetch_top_works(direction, n=4)`** — rank that direction's WorkRefs by `cited_by_count`, `get_work` down the list (free singletons), mint one **`source_type="paper"`** row per work with the abstract as `summary` **(AC11: 3 × 4 = 12)**. ⚠️ **Abstract coverage is not 100%** — verified, an older seed work returned no `abstract_inverted_index` while three 2024 works returned 1,245–1,636 chars. Fetch *more* candidates than needed and keep the first `n` that actually have an abstract, else AC11 silently under-delivers
- [x] `topic_trend(query)` and `citing_count(work_id, since)` **(AC12)**
- [x] Every call mints an `api_query` row; every derived row sets `derived_from` **(AC4)**
- [x] **Empty-result safety:** every method returns empty rather than raising; `search_literature` emits `warning{code: thin_literature}` below 5 hits; trend/citing return `{value: 0, evidence_id}` and never index into an empty list
- [x] Per-host rate limit + `tenacity` retry on 429/5xx
- [x] ⚠️ **Carried over from WI-1.2:** **do not pre-truncate abstracts** — `Evidence.summary` caps itself at 400 chars at a word boundary. And `mint()` **raises** if a `paper` derives from anything but an `api_query` with a logged 200, so mint the query row first and pass its id.
- [x] ⚠️ **Carried over from WI-1.2:** `EvidenceStore.of_type()` was deliberately not built (no caller then). Add it here if AC11's paper count needs it.
- [x] ⚠️ **Carried over from WI-1.1:** `.env`'s `OPENALEX_MAILTO` is now a real address; read it from `get_settings()`, never hardcode.
- [x] **Hermetic test** against a recorded OpenAlex JSON: every derived row has `derived_from`. **Test:** a nonsense query completes without raising
- [x] `@pytest.mark.live` smoke test: a full 3-direction run mints **≥ 12 distinct `paper` rows**
- ✅ **Done:** hermetic tests green; `pytest -m live` shows ≥12 paper rows

### WI-1.6a — LLM plumbing + calls #1/#2 `[AC2]` **CORE** ⏱1h30 🔒1.6b
> **STATUS: ✅ DONE** — `backend/roia/llm.py` + `GrantBrief`/`Capabilities` in `llm_schemas.py`, **20 tests**
> (suite now 125 hermetic + 6 live). `pytest`, `pytest -m live`, `ruff check .`, `mypy roia` all green.
>
> **Verified call shape** (`google-genai==2.22.0`) — `client.models.generate_content(model, contents,
> config=GenerateContentConfig(response_mime_type="application/json", response_json_schema=Schema.model_json_schema(),
> thinking_config=ThinkingConfig(thinking_level=…), max_output_tokens, temperature))`. **Nested Pydantic models work**:
> the schema goes over with `$defs`/`$ref` and both models honour it. Note the SDK wants the **`ThinkingLevel` enum**, not
> a string — `_thinking_level()` converts and falls back to LOW rather than raising on a typo. Measured on the real
> inputs: **grant brief 6.0 s** (10,853 prompt / 1,928 output tokens), **capabilities 2.9 s** (9,117 / 603), both on
> `gemini-3.8-flash` at `temperature=0.0`.
>
> **AC14's last clause is satisfied and tested.** With `answers_brief(...)` in the prompt, LLM #1 returned
> `call_title="2026 Frontier CRP"`, `call_period="23 Mar 2026 (9am) to 18 May 2026 (4pm)"` — **not** CRP36's 14 Sep
> window, from a page that carries both. A hermetic test asserts the answers string reaches the prompt *and* that CRP36
> does not win; the live test re-checks it against the real page.
>
> ✏️ **`serialize_documents()` exists alongside `serialize_catalogue()`, and both are needed.** An evidence row's
> `summary` is capped at 400 chars, so a model handed only the catalogue would be extracting requirements from the first
> paragraph of each page. `serialize_documents` emits the **full page text with each page labelled by its own evidence
> ID**, so LLM #1 and #2 get real material and still cite rows a reader can open. `serialize_catalogue` stays what
> WI-1.6c calls **per direction**.
>
> ✏️ **Quote verification is implemented** (`verify_quotes`), because `demo-spec.md` §4 asks for exact-substring checking
> with failures logged and never dropped, and "each with a verbatim quote" is hollow without it. It found something real:
> on the recorded brief **7 of 16 quotes failed** — until I noticed 4 of those failures were caused by **our own
> markdown**. `pymupdf4llm` emits `**3 to 5 years**`; the model quotes the prose. `_squash` now strips the markup we
> added, and the count drops to **3 genuine failures**, all quotes that stitch bullet lists into one sentence. Those are
> reported via `warning{quote_unverified}` and **kept on the object** — dropping them would hide the problem. A test
> pins the count at 3, so a prompt change that makes the model paraphrase more will be noticed.
>
> 🔴 **Recorded LLM fixtures embed evidence IDs, so they embed the mint order.** `backend/fixtures/llm/*.json` was recorded
> against a store where **the grant is ingested before the profile** (§5 steps 1 then 2), which is why the profile row is
> `e23`. A test that ingests the profile alone shifts every ID and the recorded citations silently stop resolving — this
> already caught me once. **WI-1.6b/c: keep the same order when recording, or re-record.**
>
> **AC5's third clause is now binding, not a tripwire.** `test_ac5_every_structured_call_in_llm_py_passes_an_llm_output_subclass`
> walks the real call sites (positional **and** `schema=` keyword forms) and asserts each schema is an `LLMOutput`
> subclass; it also refuses a schema expression it cannot name. Proven by breaking a call site to `dict` and watching it
> fail. The subclass walk now covers 6 real models, so it is no longer propped up by test fixtures.
>
> **AC9** — `structured()` never raises. Tested against an SDK exception, an empty body, a `None` body, a schema
> violation and non-JSON: each returns `None` with `warning{llm_failed | llm_invalid_output}`. `grant_brief` and
> `capabilities` **skip the call entirely** when nothing was ingested, rather than spending money on an empty prompt.
> Unresolvable evidence IDs are dropped during validation via `CitationContext` (AC10a, tested end to end).
>
> ⚠️ **LLM #2 sees titles and years only.** `fetch_author_works` returns `WorkRef`s with no abstracts, and the prompt
> says so explicitly; a test asserts the works block is exactly one line per work. Its first recorded run returned
> **empty `evidence_ids` on every expertise entry** — fixed by naming the ID format in the prompt (`[e23]` → `e23`), and
> a test now asserts every entry is grounded.
>
> Deliberately left out: `usage_of()` (token counts) — no caller until WI-1.6d wants a cost line.
- [x] `gemini.py`: one `structured(prompt, schema, model, thinking) -> LLMOutput` using `response_json_schema`
- [x] **`serialize_catalogue(ids)` — called PER DIRECTION** with that direction's own query results + the grant rows + its trend/citing rows. Author works go only to LLM #2. ⚠️ A single 200-row undifferentiated catalogue degrades ID-citation accuracy and lets direction 1 cite direction 3's papers
- [x] **LLM #1** grant pages → `GrantBrief` (requirements + criteria, each with a verbatim quote)
- [x] 🔴 **Carried over from WI-1.4b:** LLM #1's prompt must include `answers_brief(resolve_answers(probe_result, answers))`. That string is the *only* path by which the applicant's chosen call reaches the grant brief — without it AC14's last clause is false, and on the demo pair the brief describes **two** calls with two different deadlines.
- [x] **LLM #2** profile + works → `Capabilities`
- [x] ⚠️ **Carried over from WI-1.5:** `fetch_author_works()` returns `WorkRef`s (id, title, year, citations) — **no abstracts**. LLM #2 gets titles and years, which is what §5 step 2b intends; do not imply it read them.
- [x] 🔴 **Carried over from WI-1.2 — you will inherit a deliberately failing test.** `backend/tests/test_llm_schemas.py::test_ac5_every_structured_call_in_llm_py_passes_an_llm_output_subclass` is an AST tripwire asserting `llm.py` does not yet define `structured`. It fails the moment you add it. **Extend it to walk your real call sites and assert each schema is an `LLMOutput` subclass — do not delete it.** That is AC5's third clause.
- [x] ⚠️ **Carried over from WI-1.1:** this checklist says `gemini.py`; the layout says **`llm.py`** and that is the file that exists. Don't create a second module.
- [x] ⚠️ **Carried over from WI-1.2:** every schema must subclass `LLMOutput`. Declaring `url`/`source_title`/`link` raises `TypeError` at import — that is AC5 working, not a bug.
- ✅ **Done:** both return validated objects against `backend/fixtures/`

### WI-1.6b — LLM #3, candidates only `[AC2]` **CORE** ⏱45m 🔒1.6c
> **STATUS: ✅ DONE** — `candidate_directions()` in `backend/roia/llm.py`, `Candidates`/`CandidateDirection` in `llm_schemas.py`,
> **8 tests** (suite now 132 hermetic + 7 live). `pytest`, `pytest -m live`, `ruff check .`, `mypy roia` all green.
> Recorded response in `backend/fixtures/llm/candidates.json` (2.7 s on `gemini-3.8-flash`).
>
> 🪤 **"gap" is a substring of "Singapore".** The guard that checks LLM #3 never asserts something about the field was
> written with plain substring matching, and it fired on **every** direction — because this is a Singapore call and
> every rationale says so. It cost a live-test failure that looked exactly like the model misbehaving. With word
> boundaries, **four consecutive fresh generations produced zero literature claims**; the model was fine all along.
> The matcher is now regex with `\b` anchors and has its own guard test. **WI-1.6c will want the same check on LLM #4's
> gap prose — reuse `literature_claims_in()` from `backend/tests/test_llm.py` and keep the boundaries.**
>
> **Rule 3 is enforced structurally, not by instruction.** `candidate_directions(brief, caps, *, warn, client,
> settings)` — **there is no parameter through which literature could arrive**, and a test asserts the parameter set is
> exactly that, because a new parameter here is precisely how papers get into call #3 by accident. `CandidateDirection`
> has exactly three fields (`title`, `rationale`, `queries`) and **is deliberately not a `CitesEvidence`** — citing
> evidence would imply there was evidence to cite, and at this point there is none. Two further tests: the prompt
> forbids claims about the field in so many words, and the recorded response contains **none** of 15 literature-claim
> phrases (`gap`, `under-explored`, `no one has`, `prior work`, …).
>
> ✏️ **`context=` is deliberately not passed to `structured()` here**, unlike calls #1 and #2. `Candidates` has no
> `evidence_ids` to resolve, so a `CitationContext` would validate nothing while implying citation checking was
> happening. That is the one place this call differs from WI-1.6a's carry-over, and it is on purpose.
>
> 🔑 **Query length is load-bearing and the prompt says so.** OpenAlex `title_and_abstract.search` is conjunctive: every
> extra word narrows hard. Verified in WI-1.5 — *"embodied AI assistant human action anticipation robot"* returns **0**
> works; *"intent prediction human robot collaboration"* returns **66**. The prompt asks for **3–6 plain words, no
> boolean operators, no quotes**, and a test enforces it on the recorded output. **All 9 recorded queries were run
> against the live API and every one returned a full page of 15 hits** — no dead directions.
>
> **AC2 is enforced by the schema:** `min_length=3, max_length=3` on both `directions` and each direction's `queries`,
> so the model is *told* nine queries via `minItems`/`maxItems` and a short response fails validation rather than
> quietly producing a two-direction report. A test feeds a 2-direction payload and asserts it becomes
> `warning{llm_invalid_output}` + `None`. ⚠️ **That means a length violation loses the whole stage** — WI-1.6c already
> has a per-direction fallback on its checklist; **WI-1.6d should decide whether call #3 gets a retry too.**
>
> The three directions it actually produced on the demo pair, for sanity: *Egocentric Action Anticipation for Predictive
> Human-Robot Collaboration*, *Multimodal Knowledge Graph Integration for Explainable Visual Reasoning*, *Unsupervised
> Domain Adaptation for Vision-Language Physical Task Understanding* — three genuinely different bridges between the
> call and the researcher, each rationale naming which requirement meets which capability.
- [x] **LLM #3** brief × caps → **3 candidate directions + 3 queries each**
- [x] ⚠️ **Titles + rationale ONLY. No gap text. No literature in context.**
- [x] ⚠️ **Carried over from WI-1.6a:** call `structured(prompt, YourSchema, model=settings.model_fast, context=CitationContext(store=…, warn=…), warn=…)`. Pass the schema **positionally or as `schema=`** and as a **named class** — the AC5 test walks these call sites and fails on anything it cannot resolve to an `LLMOutput`.
- ✅ **Done:** returns 3 candidates with 9 queries total
> **The single most important ordering constraint in this build.** Call #3 must not see literature; call #4 must. Reversing it is exactly the hole revision 1 of the spec had — gaps asserted with no evidence behind them.

### WI-1.6c — LLM #4 + rubrics + spread `[AC3, AC11]` **CORE** ⏱2h15
> **STATUS: ✅ DONE** — `assess_directions()` + `RUBRICS` in `backend/roia/llm.py`, five schemas in `llm_schemas.py`,
> **24 tests** (suite now 173 hermetic + 8 live). `pytest`, `ruff check .`, `mypy roia` green.
>
> 🎯 **Claim C3 passes with room to spare.** On the recorded run: **overall spread 4.71** (needs ≥1.5) and **7 of 7**
> scored criteria separate the directions by ≥3 (needs ≥4). A second test goes past the proxy and asserts the property
> the demo shows: **moving all weight to one criterion re-orders the cards**. Every direction cites **8–9 evidence IDs**
> including a `paper` and a `grant_doc` (AC11), **zero stray IDs** from another direction's catalogue, and gaps of
> 61–73 words. No warnings.
>
> **Final settings: `gemini-3.1-pro-preview`, `thinking="medium"`, `max_output_tokens=32_000` → 94 s**, 12,606 prompt /
> 3,026 output / 11,651 thought tokens, one call for all three directions.
>
> 🔥 **Three recorded runs failed before this one. Each failure is now a constant with a comment, and they are the most
> useful thing in this item:**
>
> | Symptom | Cause | Fix |
> |---|---|---|
> | Combined call failed validation, fell back to 3 calls, **323 s** | **Thinking tokens count against `max_output_tokens`.** 8,175 thought + 15,811 output = 23,986 ≈ the 24,000 cap → truncated mid-JSON | Cap raised, but see below |
> | One call ran past **411 s** — longer than AC1 allows for the *entire* run | Raising the cap to 48,000 just let the model write more | **Constrain the prose in the prompt**, not the cap: ≤120 words per section, 1–2 sentences per rationale, ≤3 strengths. Output fell 15,811 → 2,248 tokens |
> | Every `evidence_ids` came back **empty**, 30 `thin_evidence` warnings | `CitesEvidence.evidence_ids` has a default, so it is **optional** in the JSON schema — under length pressure the model omits it | **Redeclare it without a default** on `CriterionScore` and `DirectionSection` so it lands in `required`. "A score is never a bare float" has to be schema-enforced, not asked for |
> | Live test: a direction cited the call's **web page** but no `grant_doc` → AC11 fails | The prompt never required it | `grant_alignment` **must** cite a `grant_doc`; each direction must cite a `paper` |
>
> ⏱ **`thinking="high"` measured 84 s, 233 s and 411 s on the same prompt — too variable against AC1's 360 s for the
> whole run.** `medium` gives 94 s and a *better* spread (4.71 vs 3.0). WI-0.1 chose Pro for this call; the thinking
> level was never part of that decision. **A human may want to re-check this trade** — `high` is not obviously better here.
>
> **Scores are absolute values under anchored rubrics, elicited ordinally — not rank-mapped.** `plan.md` §7.2 says to
> map rank → score in Python, but **`demo-spec.md` §6.4's `CriterionScore` contract has no `rank` field** and
> `backend/fixtures/report-sample.json` carries varied per-criterion values a rank map cannot produce. demo-spec wins. The
> ordinal discipline lives in the prompt: *"first decide the order of the three directions on that criterion, then
> assign values consistent with that order."*
>
> **27 anchored sentences** for all 9 criteria, but **only the 7 scored ones are sent** — offering a rubric for a
> criterion the demo scores `None` invites the model to score it.
>
> ✏️ **Python derives the direction-level `evidence_ids`** as the union of what the direction's own fields cite. The
> first recorded run left it empty on all three while citing 3–6 IDs per section; asking the model to repeat itself is
> work it forgets. A `mode="after"` validator gathers the union after unresolvable IDs are dropped.
>
> **AC10b is wired into the pipeline, not just unit-tested:** a citing node under its floor triggers **exactly one**
> retry, the better result wins, and what stays thin emits `warning{thin_evidence}`. Separately, if the combined call
> fails validation or length it splits into **one call per direction** — which loses cross-direction calibration, so
> `check_spread()` runs either way and emits `warning{compressed_scores}` at runtime, not only in a test.
>
> 🔴 **For a human: `confidence` is LLM-emitted, and `plan.md` §7.1 says it never should be.** demo-spec is silent, so
> the governing document is not violated, and the output is coherent (it tracks `evidence_strength`). But plan.md's
> inputs for computing it are all demo non-goals. If you want it deterministic, derive it from `evidence_strength` in
> **WI-1.7** and drop the field.
>
> 📼 **The tests replay a cassette.** `backend/fixtures/openalex/cassette/` (31 files, 282 KB) keyed by
> `sha256(host + path + sorted params, minus api_key)[:16]` rebuilds a store **byte-identical** to the one
> `backend/fixtures/llm/assessment.json` was recorded against. A changed query misses and the test says so rather than matching
> the wrong response. A guard test asserts the replay still yields **12 papers**, so AC11 cannot quietly stop being
> exercised.

- [x] **LLM #4** candidates + per-direction catalogue → `evidence_backed_gap`, 9 ordinal scores, narrative, `evidence_ids`
- [x] 27 anchored-rubric sentences (9 criteria × what 2/5/8 look like)
- [x] 🔴 **Carried over from WI-1.6a:** `serialize_catalogue(ids, store)` is ready — call it **per direction** with that direction's own query rows + the grant rows + its trend/citing rows. Use `model=settings.model_smart` and `thinking="high"` (Pro, ~5 s/call). If you record a fixture, ingest the **grant before the profile** or the embedded evidence IDs will not resolve.
- [x] Explicit `max_output_tokens`. **Fallback decided now:** if validation or length fails, split into one call **per direction** (3 smaller calls)
- [x] 🔴 **Carried over from WI-1.2:** set **`evidence_floor: ClassVar[int] = 1` on `CriterionScore`** (`plan.md` §7.2: judged criteria need ≥1). The default is 2 for directions (AC3); leave it and `call_with_evidence_floor` flags every score as `thin_evidence`.
- [x] ⚠️ **Carried over from WI-1.2:** `thin_evidence` is **not** an LLM field — Python owns it. `call_with_evidence_floor()` returns the thin nodes; set the flag on the report-side model.
- [x] ⚠️ **Carried over from WI-1.0:** the output shape is already frozen in `backend/fixtures/report-sample.json` — `problem_statement` and `evidence_backed_gap` are `{text, evidence_ids}`, all 9 criteria present in §6.4 order with two `null`, `provenance` `"judged"`. Validate the fixture against your models and fix the **models** only if the fixture is wrong.
- [x] **Test (AC3, AC11):** golden fixture → 3 directions, each ≥2 resolvable IDs, ≥1 `paper` + ≥1 `grant_doc`; every cited ID belongs to that direction's own queries or the grant
- [x] **Test (score spread — this is claim C3):** `max(overall) - min(overall) >= 1.5`, and ≥4 of the 7 scored criteria have a per-criterion range ≥ 3
- ✅ **Done:** both tests green
> The spread test is ten minutes to write and is the only thing standing between you and sliders that move nothing on stage.

### WI-1.6d — Pipeline orchestration `[AC1, AC7, AC9, AC12]` **CORE** ⏱1h15 🔒1.7, 2.1
> **STATUS: ✅ DONE** — `backend/roia/pipeline.py`, **18 tests** (suite now 191 hermetic + 8 live). `pytest`, `ruff check .`,
> `mypy roia` green. **`backend/fixtures/run-001.jsonl` is a real end-to-end run: 131 events.**
>
> ⚠️ **Steps 9 and 10 are NOT here — they are WI-1.7's.** `run_pipeline` executes §5 **steps 1–8** and returns a
> `PipelineResult`; `compute_ranking` and the `report.md` render do not exist yet and stubbing them would be worse than
> leaving the seam clean. **WI-1.7 extends `run_pipeline` (or wraps it) to add stages `ranking` and `report`.**
>
> **What a real run produces** (`backend/fixtures/run-001.jsonl`, everything replayed except LLM #4):
> **131 events** — 52 `evidence.added`, 26 tool pairs, 8 stage pairs, 1 `identity.resolved`, 8 warnings —
> **52 evidence rows, 12 papers, 3 directions each citing 7 IDs including a `paper` and a `grant_doc`**, identity
> resolved as *Basura Fernando* (`unverified`, margin 0.0). **AC7 wanted ≥15; this is 131.**
>
> ⏱ **AC1: 114 s with the network replayed, LLM #4 live at 106 s of that.** A fully live run adds ingestion (~17 s) and
> the literature stage (~30 s) → **~160 s against the 360 s limit**. The eight stages, in order:
> `ingest · identity · author_works · grant_brief · capabilities · candidates · literature · assessment`.
>
> 🐛 **A real bug the tests caught: `run_pipeline` was not passing its `http` client to `OpenAlexClient`.** OpenAlex went
> to the live API while every other call was replayed — the cassette recorded nothing and no test could isolate it. Now
> **one client serves pages *and* OpenAlex**, routed by host, so a request missing from either fixture store fails loudly
> instead of quietly reaching the network.
>
> 🐛 **A second, in WI-1.3's STATUS rather than its code: `run.warning` does *not* satisfy `WarnFn` at the type level.**
> WI-1.3 proved it works at runtime and claimed the signatures matched; mypy disagreed the moment the pipeline wired
> them, because return types are covariant and a callable returning `Event` is not one returning `None`.
> **`WarnFn` and `EmitFn` are now `Callable[..., object]`** — which is what "we ignore the return" actually means.
> Everything else was correct: no adapters were needed anywhere.
>
> **AC9, three ways, all tested:** a 404 profile → `warning{fetch_failed}`, `identity=None`, and the grant half of the
> report still built; a refused LLM call → `warning{no_candidates}` and a finished run; a dead network → warnings and
> `run.finished`, never an exception. `_stage()` catches everything and reports it — one unreachable page must not cost
> the four minutes already spent.
>
> **AC12** — `topic_trend` and `citing_count` run **per direction**, both return a non-zero value with a resolvable
> `api_query` row, and **both rows are in that direction's catalogue**, which is the half that lets LLM #4 cite them.
>
> ✏️ **`_tool()` announces evidence by diffing the store.** `EvidenceStore.all()` is in mint order, so the rows added
> since the mark are exactly that tool's — no retrieval function had to learn about events. A test asserts every minted
> row is announced **exactly once**, because the Sources counter is driven by these and a double count is a visible lie.
>
> **LLM #3 gets one retry** (~3 s on Flash) before the stage is abandoned, since `Candidates` is `min_length=3` and a
> short response otherwise loses the whole stage. Tested.
>
> 🔑 **Probe reuse needs the store as well as the result:** `run_pipeline(..., probe=result, store=store)`. The probe
> minted its rows into a store the caller owns, and without it the evidence IDs the probe already showed the user in its
> questions would point at nothing. A test asserts the call's 21 pages are minted **once**, not twice.
>
> ⚠️ **`backend/fixtures/run-001.jsonl` carries 5 `fetch_failed` warnings** — the CRP page links seven documents and the test
> fixtures route only the one ZIP. That is honest (it is what happened) and it gives WI-2.6 real warnings to render, but
> a fully live run would not have them. The 3 `quote_unverified` warnings are the known stitched quotes from WI-1.6a.
>
> 📼 The cassette now also holds `/authors`, the ROR lookup and `author.id` works. **Evidence IDs are sequential, so
> `backend/tests/test_assessment.py` had to insert the two author-resolution calls between ingest and literature** — skipping
> them shifted every literature ID by two and the recorded assessment stopped resolving.
- [x] `run_pipeline(inputs, run)` executing `demo-spec.md` §5 steps **1 → 10** in order
- [x] ⚠️ **Carried over from WI-1.4b:** accept the `ProbeResult` and **reuse `result.grant` / `result.profile` instead of re-ingesting** — steps 1 and 2 are already done, and repeating them costs ~17 s of the AC1 budget and doubles the evidence store. Call `resolve_answers(result, answers)` once and pass it down.
- [x] 🔴 **Carried over from WI-1.5:** pass **`profile_text=<profile DocumentSet>.text`** to `resolve_author` or the 30-point topic-overlap term is dead and ranking is works-count only. Wire `run.emit` into the client's **`emit=`** slot so `identity.resolved{confidence:"unverified", margin}` reaches the UI, and its `warn=` slot for `thin_literature` / `openalex_failed`. Build **one** `OpenAlexClient` per run and `close()` it.
- [x] Fan-out: 3 directions × 3 queries → `search_literature(limit=15)`; `topic_trend` + `citing_count` per direction; `fetch_top_works(n=4)` per direction
- [x] **`run.emit()` at every step boundary** — `stage.*` and `tool.*` ⚠️ this belongs on Day 1, not Day 2, or the Day-1 CLI produces an empty fixture
- [x] ⚠️ **Carried over from WI-1.6b:** `Candidates` is `min_length=3, max_length=3`, so a short response from call #3 fails validation and returns `None` — **the whole stage, not a smaller report**. Decide whether to retry call #3 once (cheap: ~2.7 s on Flash) or fail the run with a clear warning. Run each direction's **3 queries** through `search_literature`, then `fetch_top_works(refs, n=4)` per direction for AC11's 12 papers.
- [x] 🔑 **Carried over from WI-1.3:** use `with run.stage(name)` and `with run.tool(name, args)` rather than emitting pairs by hand — they close in a `finally` and supply real `ms`. Wire `warn=run.warning` into `ingest_*`, `OpenAlexClient`, `structured`, `CitationContext` and `call_with_evidence_floor`, and `emit=run.emit` into `OpenAlexClient`; every signature already matches, so no adapters. `Run(run_id, jsonl_path="backend/fixtures/run-001.jsonl")` gives AC7 its file for free.
- [x] ⏱ **Carried over from WI-1.6c — the AC1 budget is tighter than it looks.** LLM #4 is **84 s** on Pro and **doubles to ~168 s** if AC10b's retry fires. With ingestion ~17 s and the literature stage ~30 s, a clean run is ~2¼ min against the 6-minute limit. Build the per-direction catalogue as `[*grant_ids, *that direction's search rows, *its papers, *its trend and citing rows]` — 31 rows each on the demo pair — and pass it as `DirectionEvidence(candidate=…, evidence_ids=…)`.
- [x] Per-step failures caught into `warning`, run continues **(AC9)**
- [x] 🔴 **Carried over from WI-1.2:** wire `run.emit` into the **`warn=` slot** of `CitationContext(store=…, warn=…)` and `call_with_evidence_floor(call, warn=…)`, and into `ingest`/`openalex`. Until that is done, `unresolvable_evidence_id` and `thin_evidence` are computed but never reach the UI — AC10a's warning silently does not appear.
- ✅ **Done:** `backend/fixtures/run-001.jsonl` contains **≥ 15 events (AC7)**
> `pipeline.py` was in the layout but owned by no work item in rev 1. Steps 6, 7a and 7b had functions and no caller.

### WI-1.7 — Ranking + report render `[AC2, AC6, AC13]` **CORE** ⏱1h
> **STATUS: ✅ DONE** — 🎉 **end-to-end from the command line.** `backend/roia/ranking.py`, `backend/roia/report.py`, `backend/roia/__main__.py`,
> plus stages 9 and 10 in `pipeline.py`. **27 tests** (suite now ~215 hermetic + 8 live).
>
> **A live run, start to finish:**
> ```
> python -m roia run --grant https://www.rgp.gov.sg/nrf-ar/crp --out runs/demo
>   run-20260906-025302   158s
>   directions : 3        evidence : 85 rows, 12 papers      events : 162
>   report     : runs/demo/report.json · runs/demo/report.md
> ```
> All **10 stages** now appear in the timeline: `ingest · identity · author_works · grant_brief · capabilities ·
> candidates · literature · assessment · ranking · report`. **158 s against AC1's 360 s.**
>
> **`compute_ranking` reproduces `backend/fixtures/report-sample.json` exactly** — 7.57 / 6.57 / 5.57 — because it rounds to the
> same 2 dp and renormalises over the scored seven, so flat weights give the plain mean of the seven rather than
> five-ninths of it. A criterion scored `None` is **excluded, not counted as zero**: "not assessed" must not drag a
> direction down. Tested at both extremes — all weight on one criterion returns that score; all weight on an unscored
> one returns 0.0 rather than dividing by zero.
>
> **Python owns `rank`, `overall` and `thin_evidence`** (rule 2), and a test asserts none of the three is a field on
> `DirectionDraft`. `thin_evidence` comes from the evidence floor, not from the model's opinion of itself. The report
> carries **all nine criteria in §6.4 order** with the two non-goals as `null`, so the UI renders "not assessed" rather
> than silently dropping a column.
>
> **AC13 is checked twice**: every markdown link resolves to a stored evidence URL, **and** every `http(s)` string
> anywhere in the file is a stored URL or one of the two inputs — a link is not the only way a fabricated URL could get
> in. Both run against the golden fixture and against a real CLI run.
>
> 🔴 **THE FINDING THAT MATTERS FOR DEMO DAY: LLM #4's score spread is not stable across runs.**
> | Run | Overall spread | Criteria with range ≥3 | Criteria that **re-rank** the cards |
> |---|---|---|---|
> | A | 0.71 | **7/7** | **6/7** — three different directions can each be made the winner |
> | B | 2.29 | 3/7 | **1/7** — one direction dominates and the sliders barely move |
> Both are real runs on the same inputs, minutes apart. **Run B would be a poor demo**: claim C3 is that the sliders
> re-rank, and on B they do not. Mitigation is `warning{compressed_scores}`, which now fires correctly on B — but
> **check the report before presenting, and re-run if the sliders are flat.** `backend/fixtures/report-sample.json` (WI-1.0) has
> a deliberately good spread and remains the safe input for WI-2.5.
>
> ✏️ **That finding corrected a false alarm in WI-1.6c's warning.** It fired on run A — spread 0.71 — while saying *"the
> weight sliders will barely re-rank"*, which was flatly untrue there: the winner simply rotated across criteria so the
> means cancelled. A small overall spread means the directions are **close on a flat weighting**, which can be the
> honest answer. The condition now measures what it claims: `reranking_criteria()` counts the criteria that actually
> change the card order, and the warning fires when fewer than 4 criteria separate the directions **or** fewer than 2
> re-rank them. Verified in both directions — silent on A, firing on B.
>
> **CLI** — `python -m roia run --grant URL [--profile URL] [--out DIR] [--events PATH] [--answer CODE=VALUE]
> [--skip-probe]`. It runs the pre-flight probe, prints the questions and the answers it will use, then the pipeline.
> **Exit code 1 when a run finishes but produces no directions** — a run that found nothing did not do its job.
> ⚠️ **`--events` defaults to `backend/fixtures/run-001.jsonl` and a run overwrites it**, as the task brief specifies; pass
> `--events` elsewhere to keep the committed fixture.
>
> ⚠️ **`confidence` is still LLM-emitted** (see WI-1.6c). Deriving it from `evidence_strength` here would mean dropping
> the field from `DirectionDraft`, and `LLMOutput` is `extra="forbid"`, so the recorded assessment fixture would stop
> validating and need re-recording — a Pro call for a change `demo-spec.md` does not ask for. **The change is two lines
> if a human wants it; say so and it goes in.**
>
> **WI-1.0's invariants are now real pytest tests**, with the golden fixture as input: AC3 (≥2 resolvable ids), AC4
> (provenance per `source_type`), AC11 (a paper and a grant doc per direction), AC12 (each gap citing its own trend and
> citing rows), per-direction citation isolation, the ≤400-char summary cap, and **no URL anywhere inside the
> `directions` block**.
- [x] `compute_ranking(scores, weights)` — flat weights; `competitive_differentiation`/`collaboration_potential` are `None`, excluded, weights renormalised over the scored seven
- [x] ⚠️ **Carried over from WI-1.5:** `Measure.detail` already holds the year curve and the citing sentence in renderable English — reuse it in `report.md` rather than re-deriving numbers the LLM must not retype.
- [x] 🔴 **Carried over from WI-1.6c:** `DirectionDraft` has no `rank`, `overall` or `thin_evidence` — **Python owns all three** (rule 2). Assemble the report-side `Direction` here: `rank` and `overall` from `compute_ranking`, `thin_evidence` from `len(evidence_ids) < 2`, and the two `NOT_ASSESSED` criteria inserted as `null` so `scores` carries all 9 keys in §6.4 order, as `backend/fixtures/report-sample.json` freezes it.
- [x] ✅ **DONE — the human said so.** `confidence` is now **derived, not LLM-emitted**. `ranking.confidence_for()` reads it off `evidence_strength` at that rubric's **own anchors** — `>= 8` high ("several papers' abstracts were retrieved, and a trend and a citing count both point the same way" — the anchor was reworded in the review pass, see §The review pass item 9), `>= 5` medium ("several records, none read beyond their titles"), below that low — so the thresholds come from `llm.py`'s RUBRICS rather than from taste. `thin_evidence` caps it at `low`, because a model can score `evidence_strength` 8 on citations that later fail to resolve. **`DirectionDraft` no longer has the field** and a tripwire test keeps it that way.
  **It changed nothing the model said:** all six directions across both recorded runs derive to exactly their recorded label, and `test_the_derived_confidence_reproduces_both_recorded_runs` asserts it. No Pro call was needed — `LLMOutput` is `extra="forbid"`, so the key was simply dropped from `backend/fixtures/llm/assessment.json`; a model given the new schema would not emit it, and no other recorded value moved. The card's chip carries a tooltip naming the score it came from.
- [x] `report.md` via a **Jinja template, no LLM**; evidence IDs → links resolved from the store **(PLUS)**
- [x] CLI: `python -m roia run --grant X --profile Y` → `report.json`, `report.md`, `backend/fixtures/run-001.jsonl`
- [x] 🔑 **Carried over from WI-1.6d:** `run_pipeline` already does §5 steps **1–8** and returns `PipelineResult` (store, brief, capabilities, identity, directions, catalogues, trends, citings). **Add steps 9 and 10 as two more stages** — `with run.stage("ranking")` and `with run.stage("report")` — so they appear in the timeline like every other step. The CLI builds a `Run(run_id, jsonl_path="backend/fixtures/run-001.jsonl")` and calls `probe()` then `run_pipeline(..., probe=…, store=…)`.
- [x] ⚠️ **Carried over from WI-1.4 (user decision):** run it with the grant **URL**, `--grant https://www.rgp.gov.sg/nrf-ar/crp`, not `backend/fixtures/grant.pdf`. A local file is minted as a `grant_doc` with a `file://` url (nothing was fetched, so there is no honest `http_status`), and `file://` links in `report.md` read badly. The URL path yields 55 rows, all `https://`, in ~19 s. Keep the PDF path working as the offline fallback.
- [x] **Test (AC13):** every link in `report.md` matches a stored evidence URL
- [x] **Test:** `compute_ranking` over `backend/fixtures/report-sample.json` is deterministic
- [x] 🔴 **Carried over from WI-1.0:** `overall` in the fixture is **rounded to 2 dp** — round the same way or the golden test fails on float noise. `weights` ships all 9 keys flat at 1/9 and renormalises over the scored seven, so `overall` is exactly the mean of the 7 values.
- [x] ⚠️ **Carried over from WI-1.0:** promote WI-1.0's invariant checks into real pytest tests here, with `backend/fixtures/report-sample.json` as the golden input: AC3 ≥2 resolvable ids per direction, AC4 provenance by `source_type`, AC11 ≥1 `paper` + ≥1 `grant_doc` per direction, AC12 each gap citing its own trend and citing rows, per-direction citation isolation, and no URL string anywhere inside the `directions` block.
- ✅ **Done:** 🎉 **end-to-end from the command line**

---

## Phase 2 — API + frontend (~10 h)

### WI-2.1 — FastAPI shell **CORE** ⏱1h30 🔒2.2, 2.4a
> **STATUS: ✅ DONE** — `backend/roia/api.py`, **21 tests**. Verified by curl against a real server, not only by `TestClient`.
>
> **The Done line, done with curl:**
> ```
> POST /api/runs  {"profile_url": …}            -> 422          (no grant source)
> POST /api/probe                                -> 1,233 bytes  (2 call periods, no document text)
> POST /api/runs  {grant_url, probe_id, answers} -> 201 run-001-1b51a29207db
> GET  /api/runs/{id}   … polled to completion   -> finished, 165 events, 3 directions, 85 rows
> kill the server, restart it, GET again         -> finished, 165 events, 3 directions  ✅
> ```
>
> 🐛 **A real race, found by an intermittent test and fixed properly.** `run_pipeline` emits `run.finished` **from inside
> the worker thread, before it returns**, so deriving `status` from that event alone left a window where the snapshot
> said `finished` while `report` was still `None` — and WI-2.4a navigates on exactly that signal, so the UI would have
> landed on an empty report. **The task, not the event, is now the authority**: `RunRecord.status` returns `running`
> while `task` is not `done()`. A rehydrated run has no task and falls back to its events, which is right because it
> finished before the process started. Tested deterministically rather than by polling hard.
>
> ⚡ **The pipeline runs in a worker thread — `asyncio.to_thread` inside `asyncio.create_task`.** `run_pipeline` blocks
> for minutes on HTTP and model calls; on the event loop it would stall every other request, including the SSE stream
> WI-2.2 is about to add. A test asserts `_execute` still uses `to_thread`, because this is the kind of thing a later
> refactor quietly undoes.
>
> **No module-level mutable state.** Runs, probes and uploads live on `app.state.roia`, built per application in the
> lifespan handler; a test creates two apps and asserts neither can see the other's runs.
> ⚠️ **`RUNS` is `dict[str, RunRecord]`, not `dict[str, Run]`** as the checklist wrote it — the record also carries the
> task, the report and any error, and status cannot be computed without the task (see the race above).
>
> **`POST /api/probe` returns the `ProbeResult` directly** and FastAPI serialises exactly `{probe_id, detected,
> questions, warnings}` — the `Field(exclude=True)` `DocumentSet`s never reach the browser. Measured on the real call:
> **1,233 bytes**. Cached by `probe_id_for(grant_src, profile_url)`, and a test asserts a second `Analyse` does not
> re-fetch. A run given that `probe_id` **reuses the probe's store**, so the call's 21 pages are minted once.
>
> ✅ **The PLUS upload endpoint is built.** `POST /api/uploads` refuses non-PDFs **by magic bytes, not the filename or
> the declared MIME type** — the same rule ingestion uses, for the same reason — and refuses anything over 25 MB at the
> door rather than four minutes into a run. `python-multipart==0.0.20` pinned. An uploaded call runs end to end and
> yields the same 21 grant pages.
>
> **Persistence** — on completion, `backend/runs/{run_id}/{report.json,events.jsonl,inputs.json}`. `_rehydrate` loads them at
> startup and **one unreadable directory does not stop the server booting** (tested). `_persist` swallows `OSError`:
> losing the archive is bad, losing the in-flight run because the disk filled would be worse.
>
> **CORS** is added only when `settings.dev` is true, for `localhost:5173` and `127.0.0.1:5173`. Tested both ways.
>
> ✏️ **`backend/roia/api.py` is a new module** — WI-1.1's layout was Phase 1 only and named no API module.
> Serve it with **`uvicorn roia.api:app_factory --factory --port 8000`**, and ⚠️ **without `--reload`** while a run is in
> flight: every file save kills the worker thread mid-run.
- [x] `POST /api/probe` → `{probe_id, questions[], detected{}}` — no LLM, cached by input hash
- [x] ⚠️ **Carried over from WI-1.4b:** return the `ProbeResult` directly — `grant`/`profile` are `Field(exclude=True)`, so FastAPI serialises exactly the four API keys and never the ~100k chars of document text. Cache the **whole object** (not the dump) under `probe_id_for(grant_src, profile_url)`, because the run needs the excluded `DocumentSet`s and the same `EvidenceStore`.
- [x] `POST /api/runs` → `{run_id}`; accepts optional `probe_id` + `answers`; **422** unless `grant_url` or `grant_upload_id`
- [x] `GET /api/runs/{id}` → **`{status, warnings, events, report | null}`** — WI-2.5 has no other source for the report
- [x] `POST /api/uploads` (multipart, ≤25 MB, PDF only) **(PLUS — CORE ships URL-only grant input)**
- [x] `RUNS: dict[str, Run]`; pipeline via `asyncio.create_task`; **no module-level mutable state**
- [x] On `run.finished` write `backend/runs/{run_id}/report.json` + `events.jsonl`; rehydrate `RUNS` from that directory on startup
- [x] **`CORSMiddleware` with `allow_origins=['http://localhost:5173']`** gated on a `ROIA_DEV` setting
- [x] ⚠️ **Carried over from WI-1.1:** `ROIA_DEV` already exists as `Settings.dev`. **`python-multipart` is not pinned** — add it to `backend/pyproject.toml` if you build the PLUS upload endpoint.
- ✅ **Done:** curl starts a run and polls to completion; a restart does not lose finished runs
> ⚠️ Run the backend **without `--reload`** while a real run is in flight — every file save otherwise kills it.

### WI-2.2 — SSE `[AC7, AC8a]` **CORE** ⏱1h30
> **STATUS: ✅ DONE** — `GET /api/runs/{id}/events` in `backend/roia/api.py`, fan-out in `backend/roia/events.py`,
> **13 tests** in `backend/tests/test_sse.py`.
>
> **AC8a, proved on a live run rather than argued.** Two `curl -N` tabs attached **25 s into a real
> 112 s run**, at which point 88 events already existed:
> ```
> tab A: 165 frames, seq 0..164, contiguous=True, last=run.finished
>        replayed in second 0: 88    arrived live after that: 77    stream open 87s
> tab B: 165 frames, seq 0..164, contiguous=True, last=run.finished
>        replayed in second 0: 88    arrived live after that: 77    stream open 87s
> both tabs saw identical event streams: True
> ```
> That is the Done line (two tabs), AC8a (all 88 prior events replayed) and AC7 (77 events streaming
> live) in one measurement. Both tabs closed themselves on `run.finished`.
>
> 🔒 **The lock is `threading.Lock`, not `asyncio.Lock`.** `emit` runs on the pipeline's **worker
> thread** while `subscribe` runs on the **event loop**, so an async lock would not have excluded them
> from each other at all. `Subscription.push` hands events over with `loop.call_soon_threadsafe`;
> `asyncio.Queue.put_nowait` straight from the worker thread is not thread-safe.
>
> 🐛 **`emit` was minting seq lock-free.** `seq=len(self.events)` then append is two statements: two
> threads could mint the same seq, and WI-2.4b dedupes on seq. Now inside the critical section.
>
> ✅ **The atomicity claim is tested, not asserted.** `test_replay_and_subscribe_are_one_critical_section`
> races a continuously-emitting thread against a subscribing stream. It was **verified by breaking the
> code**: splitting `subscribe` into two lock acquisitions dropped **232 events** into the gap and the
> test failed. An earlier version of the same test passed against that broken build — it let the emitter
> finish first, so nothing was ever raced.
>
> ⚠️ **Starlette's `TestClient` cannot test streaming.** It writes the whole response into a `BytesIO`
> and only returns once the app is done (`testclient.py:296,343`), so `client.stream()` on an SSE route
> **hangs until the run ends**. Anything about incremental delivery uses the **`live_server` fixture** in
> `backend/tests/test_sse.py` — real uvicorn, free port, `httpx.stream`. Reuse it; do not re-discover this.
>
> **On the wire:** `id: <seq>` and `data: <the whole event as JSON>`. **No `event:` name is set,
> deliberately** — a named SSE event never reaches `EventSource.onmessage`, only an
> `addEventListener` for that exact string, and the timeline switches on the payload's `type` field.
>
> **Headers:** `cache-control: no-cache, no-store` (the checklist asks for `no-cache`; `no-store` is
> sse-starlette's own default and is kept), `x-accel-buffering: no`, `connection: keep-alive`, and a
> `: ping` comment line every 15 s. **No `GZipMiddleware` is installed anywhere** — a compressor
> buffers, which would deliver the run in one lump at the end — and a test asserts it stays that way.
>
> **`Run` gained `snapshot()`, `subscribe()`, `unsubscribe()` and `subscribers`.** Anything not on the
> emitting thread must iterate `run.snapshot()`, never `run.events`; `get_run` and `_persist` were
> switched over.
>
> ⏸ **Known edge, deliberately not coded around.** `_ended_silently` closes a stream whose task died
> without a terminal event. It requires `record.task is not None`, so a run **rehydrated from disk with
> no `run.finished`** would stream forever. Unreachable today: `_persist` only runs in `_execute`'s
> `finally`, so a persisted run always carries a terminal event. **If that ever stops being true, add a
> `record.task is None` branch** — see the carry-over on WI-2.3.
>
> **`Last-Event-ID` is ignored on purpose.** AC8a is "replay *all* prior events to a newly-opened
> stream", so every connection starts at seq 0. This is why WI-2.4b's dedupe-on-seq is not optional.
- [x] `GET /api/runs/{id}/events` via `sse-starlette`; **replay + subscribe under one lock**
- [x] **No `GZipMiddleware` on this route**; `Cache-Control: no-cache`, `X-Accel-Buffering: no`
- [x] **Test (AC8a):** connecting after 5 events yields all 5, then live ones
- [x] 🔑 **Carried over from WI-2.1:** the app is built by `create_app(settings, runs_dir=…)` and its state lives on `app.state.roia` (`AppState.runs: dict[str, RunRecord]`). A record holds `run`, `task`, `report`, `error`; `record.run.events` is the list to replay from. Runs execute in a worker thread, so **the event list is appended to from another thread** — take a snapshot (`list(record.run.events)`) under the lock before yielding, rather than iterating it live.
- [x] ✅ **RESOLVED — `pytest-asyncio==1.4.0` is pinned** and `asyncio_mode = "strict"` is set. *The original note:* `pytest-asyncio` is **not** pinned — add it to the `dev` extra in `backend/pyproject.toml` before writing async tests. *(Pinned `pytest-asyncio==1.4.0`, `asyncio_mode = "strict"` — every async test needs an explicit `@pytest.mark.asyncio`.)*
- ✅ **Done:** two browser tabs on one run both stream
> Emit threading is **not** here — it landed in WI-1.6d on Day 1.

### WI-2.3 — Fixture replayer **CORE** ⏱30m
> **STATUS: ✅ DONE** — `backend/roia/replay.py` + two query params on the existing run endpoints,
> **19 tests** in `backend/tests/test_replay.py`.
>
> **The Done line, timed against a real server:**
> ```
> curl -sN '…/api/runs/run-001/events?fixture=run-001'            19s, 162 frames, 1 ping
> curl -sN '…/api/runs/run-001/events?fixture=run-001&speed=10'    2s, 162 frames
> curl -s  '…/api/runs/run-001?fixture=run-001'   finished, 162 events, 3 directions, 85 rows
> curl -s  '…/api/runs/x?fixture=run-000'         finished,  25 events, report null
> ?fixture=nope → 404 (naming what exists) · ?fixture=../pyproject → 422 · ?speed=0 → 422
> ```
> `no API calls` is a test, not a claim: `httpx.HTTPTransport.handle_request`,
> `AsyncHTTPTransport.handle_async_request` **and `socket.socket.connect`** are all made to raise,
> then a full run replays. (The seam is the transport, not `Client.send` — `TestClient` *is* an httpx
> client, so patching `send` would only catch the test's own request and prove nothing.)
>
> 🔑 **`?fixture=` works on BOTH endpoints**, and no run needs to exist:
> `GET /api/runs/{anything}/events?fixture=run-001&speed=10` streams it, and
> `GET /api/runs/{anything}?fixture=run-001` returns a `finished` snapshot **carrying the report**.
> WI-2.5 reads the report from the snapshot and nowhere else, so without the second half the
> replayer would be only half a fallback. Pass the browser's `?fixture=` straight through.
>
> ⏱ **`MAX_GAP_S = 3.0`, and it is not decoration.** `run-001` spends **100.2 s of its 132 s inside
> one LLM #4 call** — 76% of the run is a single silent wait. Replayed faithfully that is dead air;
> sped up enough to hide it, the other 161 events become an unreadable blur. Every gap is clipped to
> 3 recorded seconds, which is what lets `DEFAULT_SPEED = 1.5` land the run at 19 s. **The timings the
> UI displays are untouched** — `ts` and `ms` ride inside each event and are never rewritten; only the
> wall-clock pacing of the playback is compressed.
>
> 🔗 **A fixture is a pair**: `run-001.jsonl` **and `run-001.report.json`** (new — copied from the
> `backend/runs/demo/` report of that same run, per `demo-spec.md` §8.2). A test asserts the two describe one
> run: the 85 `evidence.added` ids and the 85 report rows are **identical and in the same order**.
> Regenerate one half without the other and the timeline would announce evidence the report has never
> heard of — invisible until someone clicks a chip.
>
> 🐛 **`run-000.jsonl` spells the grant `grant_url`; a real run spells it `grant_src`.** It was
> hand-built in WI-1.3 before `RunInputs` existed. Validating a fixture's recorded inputs strictly
> turned the demo-day fallback into a 500 the first time an old fixture was played, so
> `_recorded_inputs` reads them leniently. **Fixtures outlive schemas.**
>
> **Fixture names are whitelisted, not escaped** (`^[a-z0-9][a-z0-9-]{0,63}$`), in both the query
> parameter and `roia.replay`, so `?fixture=../../etc/passwd` is a 422 before anything touches the
> filesystem.
>
> 🧪 **`backend/tests/conftest.py` is new** — `app`, `live_server` (real uvicorn on a free port), `read_until`,
> `free_port`, `INPUTS`, lifted out of `backend/tests/test_sse.py` so both suites share one harness. Use it for
> the Playwright work rather than standing up another server.
- [x] `?fixture=run-001` replays the Day-1 JSONL over SSE with a speed multiplier
- [x] ⚠️ **Carried over from WI-1.3:** `events.read_jsonl(path)` loads a recorded run back into `Event` objects — use it rather than parsing lines. `backend/fixtures/run-000.jsonl` (25 events, hand-built) is available now so this can be built before `run-001.jsonl` exists.
- [x] 🔴 **Carried over from WI-2.2:** frame it **exactly** as the live stream does — `{"id": str(event.seq), "data": event.model_dump_json()}`, and **no `event:` name** — or the frontend needs a second parser. `roia.api._sse()` already does this; call it.
- [x] 🔑 **Carried over from WI-2.2:** if the replayer builds a `RunRecord` with `task=None`, its fixture **must end in `run.finished`** or the stream never closes — `_ended_silently` only fires when a task exists and is done. `backend/fixtures/run-001.jsonl` ends at seq 161 with `run.finished`; `run-000.jsonl` should be checked. Otherwise add a `record.task is None` branch to `_ended_silently` (see WI-2.2's STATUS).
- [x] ⚠️ **Carried over from WI-2.2:** `Run` now has `subscribe()` / `unsubscribe()` / `snapshot()`. Never iterate `run.events` from anywhere but the emitting thread.
- ✅ **Done:** a full run replays in 20 s with no API calls
> **Never cut.** It is both the frontend iteration loop and `demo-spec.md` §8's demo-day insurance. It does **not** block WI-2.4a — the shell, routing and form need no backend.

### WI-2.4a — React shell + routing **CORE** ⏱1h30 🔒2.5
> **STATUS: ✅ DONE** — `frontend/` (9 source files), `backend/roia/api.py::_mount_spa`,
> **7 hermetic tests** (`backend/tests/test_spa.py`) + **10 Playwright tests** (`backend/tests/e2e/`).
>
> 🔴 **READ THIS FIRST: the machine's default `node` is v18, and Vite 8 refuses it.** Vite 8.2.2 requires
> `^20.19.0 || >=22.12.0`. `frontend/.nvmrc` pins **22.23.2**; run **`nvm use`** in `frontend/` before any
> `npm` command or you get a confusing failure that looks like a broken lockfile. nvm's `default` alias on
> this machine is still 18.
>
> **Versions, pinned exactly (no `^`, no `~`) — the same rule `backend/pyproject.toml` follows:**
> vite 8.2.2 · @vitejs/plugin-react 6.1.1 · react/react-dom 19.2.8 · @mui/material + icons 9.4.0 ·
> @emotion/react 11.14.0 · @emotion/styled 11.14.1 · **react-router 8.3.1** · typescript 6.0.3 ·
> oxlint 1.81.0. Install is clean — **zero peer warnings**; every MUI peer is `optional: true`, and
> `@mui/material-pigment-css` is optional and not installed.
>
> ⚠️ **`react-router`, not `react-router-dom`.** `react-router-dom` stopped at 7.18.3; v8 ships only as
> `react-router` and its root exports `BrowserRouter`, `Routes`, `Route`, `useNavigate`, `useParams`,
> `useSearchParams` (verified against the installed `.d.ts`, not guessed). It also requires React ≥19.2.7.
>
> ⚠️ **TypeScript 6.0.3, not the `latest` 7.0.2.** npm's `latest` tag is on the TS 7 native port, but
> **create-vite's own react-ts template pins `~6.0.2`** — following the toolchain that is actually tested
> together beats chasing a tag.
>
> 🐛 **MUI 9 removed the system shorthand props from `Stack`.** `alignItems`, `justifyContent` and friends
> are gone from `StackOwnProps` (`node_modules/@mui/material/Stack/Stack.d.ts`); they must go through
> `sx={{ alignItems: 'center' }}`. `tsc` caught it. Expect this again in WI-2.4b and WI-2.5.
>
> **`strictPort: true` in `vite.config.ts`, deliberately.** CORS is open for exactly `localhost:5173`
> (`DEV_ORIGINS`), so a Vite that quietly fell back to 5174 because the port was busy would produce CORS
> failures that read as a backend bug. Fail loudly instead. **There is no dev proxy** — every call goes
> straight to `VITE_API_BASE`, which is what keeps the SSE stream in WI-2.4b unbuffered (§10).
>
> **Both topologies verified against real servers, not just tests:**
> ```
> prod   GET /                     200 text/html      GET /api/does-not-exist        404
>        GET /runs/run-001         200 text/html      GET /api/runs/x?fixture=…      200 application/json
>        GET /assets/index-*.js    200 text/javascript
> dev    :5173 -> browser called http://localhost:8000/api/… cross-origin, CORS ok,
>        162 events · 3 directions · 85 evidence rows · 4 warnings · zero console errors
> ```
>
> **AC14, driven in a real browser against the real probe** (not the stubbed one the e2e suite uses):
> 2 questions rendered (`multiple_call_periods`, `multiple_schemes`), both defaults pre-selected, both call
> periods on the page, and `POST /api/runs` carried
> `{probe_id: "pb_1b51a29207db", answers: {multiple_call_periods: "all_calls", multiple_schemes: "all_schemes"}}`.
>
> 🔴 **AC14's "< 20 s" clause is currently RED, and it is not this item's code.** The cold probe measured
> **27.1 s** (warm: 2.7 ms — it is cached by input hash). WI-1.4b measured 17.5 s and warned the margin was
> ~2.5 s; on this network it is gone. **The lever WI-1.4b named still applies:** ~8 s of it is the 1 req/s
> throttle, so `min_interval_s` on the probe's ingestion is the first thing to lower. Carried into WI-2.6,
> which owns the AC walk-through.
>
> **Scope held.** No polling in `RunPage` (WI-2.4b attaches the stream — a poll would be code it deletes
> immediately), no report rendering, no identity banner, no timeline. ⏸ **The form is deliberately NOT
> pre-filled with the frozen demo pair** — the pair is in the placeholders, and no document asks for more.
>
> ⚠️ **`pytest` no longer runs the `e2e` marker by default** (`addopts = -m 'not live and not e2e'`), because
> it needs chromium and a build. `pytest tests/e2e -m e2e` opts in, which is how the skill prompt invokes it.
> **`npm run build` first** — the `ui` fixture fails with that instruction if `frontend/dist/` is missing.
>
> 🐛 **An adversarial review pass found six real bugs, all fixed and all now tested.** Listed because
> five of them were silent — nothing failed, nothing logged:
> 1. 🔴 **Editing a form field after *Analyse* posted the new URLs with the OLD `probe_id`.** The run
>    would then reuse the previous probe's documents and evidence store while recording the new URLs as
>    its inputs — a report naming one call and citing evidence from another. Reproduced in a real
>    browser before fixing. The probe is now invalidated the moment the inputs diverge (derived during
>    render, so there is no live window), and the panel is replaced by `data-testid="stale-probe"`.
> 2. 🔴 **Pre-selected defaults were posted back as if chosen.** `resolve_answers` sets `answered=True`
>    when the posted value matches, and `answers_brief` then drops its "(not answered; default applied)"
>    qualifier — so LLM #1 was told the applicant *chose* "analyse the whole programme" when they never
>    touched the radio. **Only questions the applicant actually touched are sent now**; untouched ones
>    fall through to the server's own default. A consequence: *Start run* with nothing touched now posts
>    exactly what *Skip* posts, because they are the same act.
> 3. **A double-click on *Start run* started two runs.** `disabled` only applies on the next render. A
>    `useRef` in-flight latch closes it, and the test fires three clicks in **one JavaScript turn** —
>    three separate Playwright clicks cannot reproduce it, because the first navigates away.
> 4. **Re-picking the same PDF after removing it did nothing.** A file input keeps its previous value, so
>    no `change` event fires. The value is cleared on every selection now.
> 5. **The chip's remove control bubbled to the drop zone**, immediately re-opening the file picker.
>    Replaced with a distinct `grant-upload-remove` button that stops propagation.
> 6. **A file dropped anywhere but the zone navigated the browser away from the app**, discarding the
>    form. A window-level `dragover`/`drop` guard swallows it; the zone still receives the file because
>    its own handler runs first, in the target phase.
>
> ⚠️ **One of my own tests was vacuous, and it is worth knowing why.** `test_a_traversing_path_cannot_escape…`
> passed with the traversal guard **deleted**: `httpx` resolves dot segments client-side, so
> `GET /../secret.txt` only ever reached the server as `/secret.txt`. The traversal must be
> **percent-encoded** (`%2e%2e`) to survive the client and be decoded by Starlette after routing. Rewritten,
> then re-verified by deleting the guard and watching it fail.
>
> **Two mutations were used to prove the tests are real:** deleting the "do not start the run" rule failed
> `test_an_answer_asking_to_fix_the_input_starts_nothing`, and removing the SPA fallback failed two of
> `test_spa.py`. A third mutation (widening the effect's dep array) changed nothing and was the wrong
> mutation — a browser reload remounts regardless, which is what AC8b actually tests.
>
> ⚠️ **One e2e failure was observed and not reproduced**: a 5 s Playwright `expect` timeout on the
> running-state test, while 81 review agents were saturating the machine. **Ten consecutive clean runs**
> afterwards. Recorded rather than swept up — if it returns on an idle machine it is a real race.
>
> React 19 StrictMode double-mounts effects in dev, so the snapshot is fetched twice there; the
> `AbortController` handles it and production mounts once. Bundle: 484 kB, 152 kB gzipped.
- [x] Vite + React 19 + TS + MUI; FastAPI serves `frontend/dist/` at the same origin in prod
- [x] 🔑 **Carried over from the `backend/` + `frontend/` split:** create the Vite app in **`frontend/`** at the repo root, a sibling of `backend/`. In prod FastAPI mounts **`frontend/dist/`** — resolve it in `backend/roia/paths.py` (`BACKEND_DIR.parent / "frontend" / "dist"`), never from the CWD, and mount it only when the directory exists so the API still boots before the first `npm run build`. `.gitignore` already ignores `frontend/dist/`.
- [x] ⚠️ **Carried over from the split:** Playwright tests go in **`backend/tests/e2e/`** — `pyproject.toml`, the `e2e` marker and the venv all live in `backend/`, and the skill prompt wants one runner. Add `pytest-playwright` to the `dev` extra there, pinned `==` like everything else.
- [x] **`VITE_API_BASE`** — `http://localhost:8000` in dev, `''` in the build, so both topologies work with no code edit
- [x] Routes `/` and `/runs/:id` — **`navigate('/runs/'+id)` on start; rehydrate from the snapshot on mount (AC8b)**
- [x] 🔑 **Carried over from WI-2.3:** `/runs/:id?fixture=run-001` must work with **no backend run at all**. Pass `?fixture=` (and optional `&speed=`) straight through to **both** `GET /api/runs/{id}` and `GET /api/runs/{id}/events` — the snapshot then returns `status: "finished"` with the report attached, so the normal mount path needs no special case. `&speed=10` replays in ~2 s while iterating; the default takes 19 s.
- [x] 🔴 **Carried over from WI-2.1:** `POST /api/runs` returns **201**, not 200, and the body is `{run_id}`. The snapshot is `{run_id, status, inputs, warnings, events, report}` where **`status` is `running | finished | failed`** and `report` is non-null **only** once `status` is `finished` — that is now guaranteed, so navigate on `status`, not on seeing a `run.finished` event. `POST /api/uploads` exists (PDF only, ≤25 MB) and returns `{upload_id, sha256}`; pass `grant_upload_id` to `/api/runs` or `/api/probe`.
- [x] ⚠️ **Carried over from WI-2.2:** in dev, point `EventSource` **straight at `VITE_API_BASE`** (`:8000`), not through the Vite proxy — the proxy buffers and the whole run arrives in one lump (`demo-spec.md` §10). CORS for `:5173` is already open when `ROIA_DEV` is set.
- [x] Input form: grant URL (+ PDF drop zone **PLUS**), profile URL
- [x] **Two-step submit:** *Analyse* → `POST /api/probe` → render any questions as a radio group with the default pre-selected → *Start run* → `POST /api/runs` with the answers. Skipping the questions is always allowed and uses the defaults **(AC14)**
- [x] ⚠️ **Carried over from WI-1.4b:** two option values mean *do not start the run* — `thin_profile` → `use_different_url` and `no_eligibility_found` → `upload_document` send the user back to the form. Every other value, including every skipped question, starts the run. Each option's `evidence_ids` resolve in the store, so an option can show which page it was found on.
- ✅ **Done:** refresh mid-run restores state **(AC8b)**

### WI-2.4b — Live timeline `[AC7]` **CORE** ⏱1h30
> **STATUS: ✅ DONE** — `frontend/src/useRunStream.ts`, `Timeline.tsx`, `timelineRows.ts`;
> **7 tests** in `backend/tests/e2e/test_timeline.py`.
>
> **The Done line, watched in a browser during a real 122 s run:**
> ```
> t+  2s   63 events  Sources (56)  rows= 5  live=1
> t+ 15s   91 events  Sources (59)  rows=19  live=1
> t+ 29s  154 events  Sources (85)  rows=38  live=1
> t+122s  161 events  Sources (85)  rows=41  live=0
> 15 distinct timeline states · 1 stream connection · still 1 after a 5 s wait
> 41 rows still on screen after completion · zero console errors
> ```
> The 29 s → 122 s gap is the LLM #4 assessment call — the same 100 s silence WI-2.3 clips when
> replaying. **15 distinct states** is the evidence it streams rather than arriving in one lump.
>
> 🚫 **`@mui/lab` is NOT installed, deliberately** — it publishes only `9.0.0-beta.x` against MUI 9, and
> this is a rail, a dot and a list. `demo-spec.md` §5 already made exactly this call once, rejecting the
> Pro-licensed `@mui/x-charts` Heatmap for a hand-rolled grid on the same reasoning. A beta dependency
> pulled fresh by `npm ci` on the morning of the demo is not worth a vertical line. **No new dependencies
> at all in this item.**
>
> **The stream is the ONLY source of timeline events; the snapshot is not seeded from.** It replays from
> seq 0 on every connection (AC8a), so seeding would just be a second path to keep correct. AC8b still
> holds — a refresh reconnects and the server re-sends everything. `RunPage` falls back to
> `snapshot.events` only while the stream has said nothing at all.
>
> 📉 **50 raw events become 25 rows.** `stage.started`/`stage.finished` and `tool.started`/`tool.finished`
> collapse into one row each, which starts as "running" and gains its duration when the matching
> `finished` arrives. `evidence.added` produces **no row** — 85 of 162 events are evidence and listing
> them would bury the activity; they feed the "Sources (N)" chip and each tool's `+N` badge. The full
> recorded run renders **42 rows**, comfortably over AC7's 15.
>
> ⚠️ **`run-status` is the WRONG thing to wait on under `?fixture=`.** The snapshot answers `finished`
> immediately — the recorded run genuinely is — while the stream is still replaying at `&speed=`. Two of
> my own tests failed on exactly this before I noticed. Wait for `event-count` to reach the total, or for
> `stream-live` to disappear. `wait_for_replay()` in `test_timeline.py` does it.
>
> 🐛 **`Timeline.tsx` and `timeline.ts` differ only in casing**, which `tsc` rejects outright and which a
> case-sensitive filesystem would resolve as two files. The reduction lives in **`timelineRows.ts`**;
> merging it into the component instead trips oxlint's fast-refresh rule, so the split is the answer.
>
> ✅ **Both critical carry-overs were mutation-tested.** Removing `es.close()` failed
> `test_the_stream_closes_on_run_finished_and_does_not_reconnect`; removing the seq dedupe failed
> `test_repeated_sequence_numbers_are_rendered_once`. The reconnect test waits **5 s**, longer than
> `EventSource`'s ~3 s retry — a shorter wait would prove nothing.
>
> ⚠️ **Warnings now come off the stream, not the snapshot**, so they appear on the run's own schedule
> rather than all at once. One WI-2.4a test was updated to wait for the replay; nothing was weakened.
- [x] `useRunStream(runId)` — `EventSource`, dedupe on `seq`, **`es.close()` on `run.finished`**
- [x] 🔑 **Carried over from WI-2.4a:** the plumbing is already there. **`eventsUrl(runId, replay)`** in `frontend/src/api.ts` builds the URL off `VITE_API_BASE` and threads `?fixture=`/`&speed=` — point `EventSource` at it and nothing else. `RunPage.tsx` reads those two params from `useSearchParams` already, and **deliberately does not poll**, so the stream is the only thing to add. `RunEvent` in `types.ts` is `{seq, ts, type, …}` with a top-level index signature, matching §6.3.
- [x] ⚠️ **Carried over from WI-2.4a:** **MUI 9 removed the system shorthand props from `Stack`** (`alignItems`, `justifyContent`, …) — they go through `sx`. `tsc` catches it, but it will look like a mystery the first time. MUI's `Timeline` lives in `@mui/lab`, which is **not installed**; pin it exactly if you add it.
- [x] 🔴 **Carried over from WI-2.2:** `es.close()` is **not optional**. The server ends the stream itself after `run.finished`, and an `EventSource` treats a server-closed connection as a dropped one and **reconnects after ~3 s** — which replays all 165 events again, forever. Closing it client-side is the only thing that stops the loop.
- [x] 🔴 **Carried over from WI-2.2:** events arrive as the **default `message` type** — nothing sets an `event:` name, because a named SSE event never reaches `onmessage`. Use `es.onmessage` and switch on `JSON.parse(e.data).type`; **do not** `addEventListener('run.finished')`, it will never fire.
- [x] ⚠️ **Carried over from WI-2.2:** every connection replays from **seq 0** — `Last-Event-ID` is ignored by design (AC8a). Dedupe on `seq` is what makes a reconnect harmless, so build it first, not last.
- [x] ⚠️ **Carried over from WI-2.2:** sse-starlette sends a `: ping - <timestamp>` **comment line every 15 s**. `EventSource` swallows those; only a hand-rolled line parser needs to skip lines starting with `:`.
- [x] MUI `Timeline` of tool events + a live "Sources (N)" counter
- [x] ⚠️ **Carried over from WI-2.3:** develop against `?fixture=run-001&speed=10` — 162 real events in ~2 s, no API calls. A replayed stream is byte-identical to a live one and ends in `run.finished` the same way, so `es.close()` and dedupe-on-seq are exercised for free. `run-000` (25 events, no report) is the smaller one.
- ✅ **Done:** the timeline streams during a real run

### WI-2.5 — Report view `[AC2, AC3, AC6, AC11]` **CORE** ⏱5h
> **STATUS: ✅ DONE** — `frontend/src/ranking.ts` + `frontend/src/report/` (7 components);
> **13 tests** in `backend/tests/e2e/test_report.py`. **The PLUS score matrix is built.**
>
> **The Done line, measured rather than eyeballed:** a slider keypress to the re-ordered DOM is
> **51.9 ms** against AC6's 100 ms budget, with **zero network requests** — asserted by intercepting
> every request in Playwright, which is the Network tab with a test around it. Mutation-tested: making
> a slider `fetch()` fails that test with the nine calls listed.
>
> 🐛 **The URL cannot be the source of truth for something a drag updates.** The obvious shape —
> derive weights from `?w=` and write back on change — **silently drops rapid updates**: router
> navigation is asynchronous, so nine slider changes in quick succession all read the same committed
> URL and only the last survives. Measured: after moving all nine, the URL held `5,5,5,5,5,5,5,5,0`.
> React state is the truth now and the URL is a mirror; a `useRef` advances synchronously so a burst
> composes. **The AC6 test is what caught it** — on a demo this looks like the slider snapping back,
> with nothing in the console. The functional `setSearchParams` updater does *not* fix it.
>
> ✅ **The browser reproduces the backend's `overall` to the last decimal**, and a test asserts it
> against `run-001.report.json` (6.86 / 5.57 / 4.57). That is the only reason a slider can be honest
> rather than an approximation of a re-run; `computeOverall` mirrors `roia/ranking.py` line for line,
> **renormalising over the scored subset** — deleting that renormalisation fails the test.
>
> **Sliders are integers 0–10, default 5**, and the absolute scale does not matter because the formula
> renormalises: all-fives reproduces the backend's flat `1/9` exactly (5/35 = (1/9)/(7/9) = 1/7). The
> URL form is nine positional integers, `?w=0,10,0,0,0,0,0,0,0` — short enough to paste. A corrupt or
> truncated `w` falls back to defaults rather than producing NaN weights and a blank page; there is a
> test.
>
> **All nine criteria get a slider, including the two that are never scored.** Moving those changes
> nothing, which is the truth, and the label says so rather than leaving someone to wonder.
>
> 🎨 **The score matrix is a hand-rolled CSS grid — 3 × 9 = 27 `<Box>`s**, single hue by lightness,
> `Tooltip` per cell, and the two non-goal columns render `n/a` rather than a misleading 0.0. **Not**
> `@mui/x-charts` (Pro-licensed) and **not** `@mui/lab` (beta-only against MUI 9). A test counts the 27
> cells and asserts those six are `data-assessed="false"`.
>
> 🔒 **`rehype-raw` is absent on purpose**, and tested: model prose containing
> `<img onerror=…>`/`<script>` renders no element and executes nothing, while `**markdown**` still
> becomes `<strong>`. This prose is written by a model that was handed fetched pages and PDFs, so page
> markup reaching the report is a real path rather than a hypothetical.
>
> **`direction.evidence_ids` is rendered as its own "Cited evidence" row.** AC3 ("≥ 2") and AC11
> ("≥ 1 paper and ≥ 1 grant_doc") are claims about *that union*, not about the per-field chips — my
> first AC11 test failed for exactly that reason. Chips carry `data-source-type`, so both criteria are
> answerable by looking at the card. An id that does not resolve renders **as broken, not hidden**.
>
> 📦 **New pinned dependencies:** `react-markdown@10.1.0`, `remark-gfm@4.0.1`, `rehype-sanitize@6.0.0`.
> The bundle is now **722 kB / 225 kB gzipped** and Vite prints a chunk-size warning. Fine for a demo
> on localhost; code-splitting is the fix if it ever matters.
>
> ⚠️ **Two WI-2.4a tests were updated, not weakened**: `direction-count`/`report-placeholder` were the
> placeholder's testids and no longer exist, so AC8b now asserts three real `direction-card`s.
- [x] 3 direction cards: rank, title, problem, evidence-backed gap, strengths, weaknesses, confidence
- [x] ⚠️ **Carried over from WI-2.4b:** `RunPage.tsx` now renders the timeline from `useRunStream`; the report block is the `data-testid="report-placeholder"` Paper below it. **`@mui/lab` is deliberately not installed** — the score matrix is a hand-rolled CSS grid per `demo-spec.md` §5, so do not reach for it. Waiting on `run-status` is unreliable under `?fixture=` (the snapshot says `finished` while the stream still replays) — wait for `event-count`, as `wait_for_replay()` in `tests/e2e/test_timeline.py` does.
- [x] 🔑 **Carried over from WI-2.4a:** **the TypeScript types already exist** — `Report`, `Direction`, `DirectionSection`, `CriterionScore`, `Evidence`, `ReportIdentity`, `ReportInputs` in `frontend/src/types.ts`, mirrored field-for-field from `backend/roia/report.py` and `evidence.py`. `RunPage.tsx` already has the report in hand (`snapshot.report`, non-null only when `status === "finished"`); replace the placeholder `data-testid="report-placeholder"` block. Note `scores` is `Record<string, CriterionScore | null>` — the two non-goal criteria are `null`, which is what "not assessed" renders from.
- [x] **Evidence chips** beneath each field, resolved by ID; click → side panel with title, authors, year, summary, real link
- [x] **9 weight sliders**, re-ranking in-browser with the same formula; "reset to default"; weights in the URL
- [x] "Analysing **X** at **Y** — unverified" banner from `identity.resolved`
- [x] `react-markdown` + `remark-gfm` + `rehype-sanitize`; **no `rehype-raw`**
- [x] **Score matrix — CSS grid of 3 × 9 = 27 `<Box>`s**, single-hue scale + per-cell `Tooltip`, two columns "not assessed" ⚠️ *not* `@mui/x-charts` Heatmap (Pro-licensed) **(PLUS — CORE ships a plain per-criterion list)**
- [x] ⚠️ **Carried over from WI-2.3:** there are now **two** report fixtures and they are not interchangeable. `backend/fixtures/report-sample.json` (WI-1.0, hand-built, **20** evidence rows) is what you build components against. `backend/fixtures/run-001.report.json` (a real run, **85** rows, 3 directions, paired with `run-001.jsonl`) is what `?fixture=run-001` actually serves — check the finished view against that one, since it is what the demo falls back to.
- ✅ **Done:** **AC6 verified in the Network tab — zero requests on slider move**
> Build against `backend/fixtures/report-sample.json` from hour one. Do not wait for a live run.

### WI-2.6 — Warnings + AC walk-through **CORE** ⏱30m
> **STATUS: ✅ DONE** — `frontend/src/Warnings.tsx`, the SPA's snapshot re-fetch, the probe-cache
> refusal in `roia/api.py`; **7 tests** (4 browser + 3 API). **All 16 ACs walked and ticked — see the
> AC walk-through table below the work items.**
>
> 🔴 **The AC9 test found a bug that would have broken the demo.** `RunPage` fetched the snapshot
> **once, on mount** — and `status` and the **report** live only on the snapshot, while the stream
> carries events. So a live run finished with the timeline full, the chip still reading `running`,
> and **no report on the page at all**: AC1's "pressing Run produces a rendered report" quietly false.
> Every earlier test drove `?fixture=`, where the snapshot is `finished` from the first byte, so
> nothing had ever exercised the live path end to end. The fix is one re-fetch when the stream
> reports a terminal event — not polling. Mutation-tested: removing `stream.done` from the effect's
> dependencies fails the AC9 test.
>
> ✅ **Correction: AC14's "< 20 s" is PASS, not RED.** WI-2.4a recorded 27.1 s and I carried it
> forward as a red flag. **It does not reproduce.** Measured again on a quiet machine: `probe()`
> directly **18.1 / 18.2 s**, cold through HTTP **18.56 / 18.62 s**, and the live test **18.8 s**.
> The 27.1 s reading was taken while 81 review subagents were saturating the machine and its network.
> **The throttle was therefore left alone** — measured, `min_interval_s` 1.0 → 0.25 buys only **2.6 s**
> (18.2 → 15.6), so WI-1.4b's "~8 s of that is the throttle" estimate is also too high: the grant's
> artefacts sit on two hosts and the throttle is per-host, so it overlaps more than assumed. Hitting a
> government server four times faster to buy 2.6 s of margin we do not need is not a trade worth making.
>
> 🔴 **The unknown-`probe_id` hole is closed by refusing, not by guessing.** `POST /api/runs` now
> answers **404** when it is given a `probe_id` it no longer holds ("…Analyse again"), and **422** for
> answers with no probe at all. Starting anyway would have dropped the applicant's chosen call period
> — `run_pipeline` only reaches `resolve_answers` when a probe is in hand — and briefed LLM #1 on the
> whole programme instead: a four-minute run against the wrong deadline, silently. The browser catches
> the 404 and returns to the form. A run with **no** probe and **no** answers still starts, unchanged.
>
> **Warnings are dismissible but never deletable.** A warning is the honest half of the report — "the
> profile page yielded 412 characters", "only 3 papers came back" — so a run that could hide them for
> good would claim more than it retrieved. Dismissal is per-view and a "show N dismissed" button brings
> them back. Keyed by **`seq`, not `code`**: the recorded run carries two `thin_literature` warnings
> and keying on the code would dismiss both at once (there is a test).
>
> 🐛 **`tests/e2e/test_report.py` collided with `tests/test_report.py`.** Same basename, no
> `__init__.py`, so pytest imported them as one module `test_report` and full collection failed —
> intermittently, because it depended on `__pycache__` state. That is the shape of a "works on my
> machine" bug. Renamed to **`tests/e2e/test_report_view.py`**; a clean-cache full run is green.
> **Keep test basenames unique across `tests/` and `tests/e2e/`.**
- [x] Warnings render as dismissible MUI `Alert`s
- [x] 🔑 **Carried over from WI-2.5:** the report view is complete and `?fixture=run-001` shows it with no keys and no network — **that is the AC walk-through's harness.** AC2/AC3/AC6/AC11 already have tests in `backend/tests/e2e/test_report.py`, AC7/AC8a in `test_timeline.py`, AC8b/AC14 in `test_shell.py`; **39 browser tests in total**. Walking the ACs is mostly running `pytest tests/e2e -m e2e` and reading, not re-deriving.
- [x] ⚠️ **Carried over from WI-2.3:** `?fixture=run-001` already carries **four real warnings** from the recorded run — `quote_unverified`, `thin_literature` ×2, `compressed_scores` — so the alert UI can be built and checked without provoking a live failure. AC9 still needs its own deliberately broken profile URL.
- [x] A deliberately broken profile URL → run completes with a warning **(AC9)**
- [x] **Walk all 16 ACs and tick them off in this file**
- [x] ✅ **RESOLVED — an unknown `probe_id` used to silently discard the answers.** `POST /api/runs` now answers **404** ("…Analyse again") for a `probe_id` the server no longer holds, and **422** for answers with no probe; the browser catches the 404 and returns to the form. A run with no probe *and* no answers still starts. *The original finding, for context:* `create_run` does `state.probes.get(body.probe_id or "")` and gets `None` without complaint (`backend/roia/api.py`), and `run_pipeline` then does `answers = ""` unless `probe is not None` (`backend/roia/pipeline.py:264-266`) — so `inputs.answers` never reaches LLM #1. **Restart uvicorn with a tab open, press Start, and AC14's "the chosen answer appears in the grant brief" fails with nothing logged.** Decide the fix: reject an unknown `probe_id` (409/404), or re-probe server-side. The frontend cannot detect this — it has no view of the server's probe cache.
- [x] ✅ **RESOLVED — and the finding was wrong.** AC14's "< 20 s" clause **PASSES**: 18.1 / 18.2 s measured directly, 18.56 / 18.62 s cold through HTTP, 18.8 s for the live test. The 27.1 s below did not reproduce — it was read while 81 review subagents were saturating the machine. **The throttle was left alone** (1.0 → 0.25 buys only 2.6 s). *The original finding, for context:* The cold probe on the demo pair measured **27.1 s** end to end (warm 2.7 ms — it is cached by input hash). WI-1.4b measured 17.5 s and warned the margin was ~2.5 s; on a slower network it is gone. **The lever WI-1.4b named is still the right one:** roughly 8 s of it is the 1 req/s politeness throttle, so lowering `min_interval_s` for the probe's ingestion is the first thing to try. Measure before and after; do not just re-run until it passes.
- [x] ⚠️ **Carried over from WI-2.4b:** warnings now come off the **event stream**, so during a live run they appear as they happen rather than only on reload — good for AC9's deliberately broken profile URL. They are also rendered as amber dots in the timeline itself.
- [x] ⚠️ **Carried over from WI-2.4a:** warnings already reach the browser as MUI `Alert`s with `data-testid="run-warning"` (`RunPage.tsx`) and `data-testid="probe-warning"` (`NewRunPage.tsx`) — make them dismissible rather than starting from nothing. `?fixture=run-001` carries four real ones.
- [x] ⚠️ **Carried over from WI-2.4a:** `pytest` no longer runs the `e2e` marker by default. The AC walk-through must run **`cd backend && pytest tests/e2e -m e2e`** explicitly, after **`cd frontend && npm run build`** — and `nvm use` first, because this machine's default node is v18 and Vite 8 refuses it.
- ✅ **Done:** every AC checked

---

## After the plan — changes since the last work item

WI-2.6 closed the last work item. Anything after it belongs to no item, so it is recorded here
rather than being hidden inside one. **If you change something once the plan is closed, add a row.**

| Commit | What | Why |
|---|---|---|
| `5d9e21d` | **`confidence` is derived, not LLM-emitted** | Closes WI-1.6c's deliberately-open box. Details below. |
| `c7bf19d` | Three ticked carry-overs stopped claiming their problem was live | A `- [x]` box reading "currently RED" is a contradiction — a reader scanning the checklist takes the problem as open. Each now states the outcome first and keeps the original finding underneath, labelled as history. |
| `df90e38` | This section was added | Work after the last item belongs to no item, so it needed somewhere to live. |
| *(review)* | **Deep review of the finished build.** 8 dimensions, every finding adversarially verified before it was believed. 60 confirmed; the ones fixed are below, the rest are listed under §Known and not fixed. | The build was complete and every AC ticked. That is exactly when nobody looks again. |

### `5d9e21d` — `confidence` derived from `evidence_strength`

**The problem.** `confidence` was the one field in the report the model asserted **about its own
output**, with nothing behind it. Everything else here is checkable: each score cites evidence, the
overall is arithmetic the browser repeats (AC6). "How sure are you?" is also the question a model is
least able to answer about itself. So the honest reply to *"where does that confidence come from?"*
was **"the model said so"** — the one answer this tool is built never to give.

**The thresholds are the rubric's, not mine.** This was the real risk in changing it: swapping the
model's judgement for arbitrary numbers is not an improvement. `llm.py`'s `RUBRICS` already anchor
`evidence_strength` in words:

| Anchor | The rubric's own wording | Derived |
|---|---|---|
| **8** | "several papers' abstracts were retrieved, and a trend and a citing count both point the same way" | `high` |
| **5** | "several retrieved records support the claim, but none were read beyond their titles" | `medium` |
| **2** | "the claim rests on one retrieved record, or on a query that returned almost nothing" | `low` |

`ranking.confidence_for()` reads those anchors and nothing else.

**`thin_evidence` caps it at `low`.** That flag means the direction fell below the citation floor
*after* unresolvable ids were dropped — a fact about the direction the per-criterion score cannot
see. A model can score `evidence_strength` 8 on citations that later fail to resolve, and calling
that high confidence would be exactly the kind of unbacked claim this change removes.

**It changed nothing the model said.** All six directions across `report-sample.json` and
`run-001.report.json` derive to precisely their recorded label:

```
report-sample.json   rank 1  model 'high'    evidence_strength 8.0  -> high     same
                     rank 2  model 'medium'  evidence_strength 6.0  -> medium   same
                     rank 3  model 'low'     evidence_strength 4.0  -> low      same
run-001.report.json  rank 1  model 'medium'  evidence_strength 7.0  -> medium   same
                     rank 2  model 'low'     evidence_strength 4.0  -> low      same
                     rank 3  model 'low'     evidence_strength 3.0  -> low      same
```

So this bought a **guarantee**, not different answers — and
`test_the_derived_confidence_reproduces_both_recorded_runs` asserts it, so a future rubric change
that moves a threshold fails loudly instead of silently relabelling the demo.

**Both thresholds are mutation-tested.** Lowering `high` to 7.0, or making the boundary exclusive,
fails on a fixture that scores exactly on the line (8.0 and 7.0 both appear in the recorded runs).

⚠️ **No Pro call was needed, contrary to what this box used to say.** `LLMOutput` is
`extra="forbid"`, so the recorded response just has the key removed — **three lines, every other
byte in `backend/fixtures/llm/assessment.json` untouched** — and a model given the new schema would
not emit it. Re-recording would have been worse: it would have changed every score and every
sentence, invalidating `report-sample.json`'s golden values and the tests built on them.

**Guards left behind.** `test_the_model_has_no_confidence_field_to_fill_in` is a tripwire: putting
`confidence` back on `DirectionDraft` would quietly restore the unbacked field and every other test
would still pass. The card's chip reads "medium confidence" with a tooltip naming the score behind
it, so the demo question is answered on screen.

---

## The review pass — what it found and what changed

Everything below was found **after** the plan closed, by reviewing the finished build against
`demo-spec.md` and against a real recorded run. Each was reproduced before it was fixed and has
a test that fails without the fix.

### Fixed

**1. A model-written URL reached the report as a live citation.** `AC5`'s guard rejects a field
*named* `url`; nothing looked at a URL sitting *inside* `problem_statement.text` or a
`rationale`. Those go straight into `report.md`, and in the browser through `react-markdown`,
which renders both `[label](https://…)` and a bare `https://…` as an anchor — a fabricated
citation, clickable, directly above the genuine evidence chips. Not hypothetical: LLM #4's
catalogue is fetched page text, and two of the 85 summaries on `run-004` contain markdown links.
Now `LLMOutput` strips URLs from every string it carries and warns `model_wrote_a_url`, and
`Prose` drops `a` from its sanitiser so only `EvidenceChips` can produce a link. **This was the
one hole in the product's central claim.**

**2. The backend and the browser computed different scores.** `ranking.ts` claimed to mirror
`ranking.py` "line for line". It did not, in two independent ways: Python rounded half-to-even
where `Math.round` is half-up, *and* Python divided each term by the total before summing where
the browser divides once at the end. Together they disagreed on 1.2% of weight vectors on
`run-004` — including the most natural demo gesture, novelty to maximum, where the card read
**5.63** above a `report.json` saying **5.62**. Both are fixed; a sweep test compares the two
across 9,000 weight vectors, and the browser test now checks non-default weights, which is the
only place a slider ever puts you.

**3. Two runs from one probe shared an evidence store.** The probe caches its ingestion so a run
does not re-fetch seven PDFs — and cached the `EvidenceStore` *object*, handing the same one to
every run quoting that `probe_id`. Pressing **Analyse** twice made run 2 open holding run 1's
rows and publish a report listing another run's evidence. Measured: 81 rows against 52. Now
`EvidenceStore.fork()` gives each run its own copy.

**4. `probe_id` was never checked against the run's inputs.** The probe carries the documents the
run analyses. A stale one made the run read grant A while its inputs, its report header and its
archived events all said grant B. Now `422`.

**5. A failed OpenAlex request was minted as a measured zero.** `_get` returns `None` on a 404 or
a timeout, and every summary was computed from `payload or {}` — so a network blip became *"0
works match"*, *"No works matched"*, *"0 works … cite W123"*, minted as evidence and handed to
LLM #4 as citable numbers about the state of the field. The project's own rule is that finding
nothing means **don't know**, never *nobody has done this*. Failed requests now say so, and no
longer fire `thin_literature`.

**6. `Jean-Baptiste Mouret` was looked up as `Jean`.** The title-cleaning regex treated any
hyphen as a separator, so every hyphenated name was truncated at it and step 2b resolved a
stranger — whose publication record then drove the applicant-fit scores. The demo pair has no
hyphen in it, which is why nothing noticed. A hyphen now has to be spaced to count.

**7. The score matrix did not re-rank with the sliders.** It was handed `report.directions` and
labelled its columns with the backend's stored `rank`, while the cards below used the rank
recomputed in the browser. One slider move and the column headed "#1" sat above a card headed
"#1" that was a different direction — on the one screen whose job is comparing them.

**8. The assessment call ignored the constant that protects AC1.** `ASSESSMENT_THINKING =
"medium"` was added with the measurement that justified it — `high` ran **84 s, 233 s and 411 s**
on the same prompt against AC1's 360 s for the *whole run* — and was then applied only to
`_assess_singly`, the per-direction fallback that runs after the main call has already failed.
The main call passed a literal `"high"`, and a test asserted it. Both now use the constant.

**9. `report.md` claimed the papers were "read in full".** §4 makes paper full text an explicit
non-goal ("the demo reads OpenAlex abstracts only") and §10 lists it among the things the demo
must *say*: "claiming otherwise invites the one question you cannot answer." It is not even the
whole abstract — `Evidence.summary` caps at 400 characters and all twelve paper rows on
`run-004` are truncated there. Corrected in the report, in the rubric anchor the model scores
against, and in the docs.

**10. `report.md` carried none of the run's warnings.** The browser shows them as alerts at the
top; the file a reviewer forwards showed nothing, so the exported copy was quietly the more
confident of the two. `run-004`'s two `quote_unverified` warnings are now in it, and
`run-001`'s `thin_literature` and `compressed_scores` with them.

**11. Eleven warning codes reached the user as raw snake_case**, including `llm_failed`,
`author_unresolved` and `openalex_failed` — the ones that appear on the day something goes wrong
and the box is actually being read. A test now fails if a new code arrives without a sentence.

**12. No timeout on the Gemini client.** `structured()` promises to degrade into
`warning{llm_failed}`, but with no timeout there was nothing to degrade from: the thread waits,
`run.finished` never fires, and the page spins indefinitely. Now 300 s.

**13. Smaller:** `GET /api/runs/{id}/report.md` was specified in §6.2 and implemented only in the
CLI, so the one artefact a reviewer forwards could not be got out of the running app · the
`Analyse` button promised "About 10 seconds" for a probe measured at 17.5 s · the confidence
label's derivation was explained only by a browser tooltip · a nested plain `BaseModel` would
slip past the AC5 guard (no such model exists today; a test now keeps it that way) · the README
repeated a paragraph verbatim.

### Known and not fixed

Found and verified, deliberately left. None of them is on the demo path.

- **AC12's second clause** — "each gap statement cites the evidence ID of that result" — is met
  by the hand-authored fixture and by neither real run; nothing prompts for it or checks it.
  `PipelineResult.trends`/`citings` have no consumer.
- **AC11's 12-paper floor equals the pipeline's ceiling** (4 × 3) and is checked nowhere at
  runtime. One OpenAlex record without an abstract puts a real run under it silently.
- **A cancelled or interrupted run rehydrates as permanently "running"** and its SSE stream never
  closes: `_persist` writes no terminal event.
- **The HTTP `charset` is ignored** — a non-UTF-8 page is mojibake in the store and the report.
- **`_read_zip` has no decompressed-size cap** — a 400 KB response can expand to ~391 MB.
- **A comma in an LLM-authored query or in a researcher's name makes OpenAlex return 400.**
- **XHTML served as `application/xhtml+xml`** is accepted by `_sniff` and never parsed.
- **An uploaded PDF loses its filename** and appears in the report as a hash with a `file://`
  link.
- **Probe answers keyed by anything but the question code are silently discarded** — the recorded
  run on disk did exactly that.
- **`tool.finished.summary`** is in §6.3 and rendered by the frontend, but empty on every event.
- **`Evidence.quote` is never populated**, so `verify_quotes` guards something invisible.
- **Run ids are `len(runs)+1` + an input hash** and can collide after a failed rehydrate.
- **The hermetic suite takes ~4m39s** because `test_pipeline.py`'s `completed` fixture is
  function-scoped and re-runs a whole replayed pipeline per test (`test_assessment.py` already
  solved this with `scope="module"`).

---

## What is left for a human

Everything in the Progress table is done, and the one open decision has been taken:

⏸ ~~`confidence` is LLM-emitted~~ — **done**, see WI-1.6c. It is derived from
`evidence_strength` at that rubric's own anchors, and reproduces every recorded label.

One operational habit remains. It is not a decision:

1. ⚠️ **Score spread varies between runs.** One run had six of seven criteria re-ranking the cards,
   another had one. A `compressed_scores` warning fires when it happens — **look at the report before
   demoing and re-run if you see it**, because the weight sliders are the third thing the demo claims.

---

## AC walk-through (WI-2.6)

Every criterion, its verdict, and the **one command** that proves it. All 16 rows were run on
the day WI-2.6 was closed. Commands are from `backend/`; browser rows need
`cd frontend && nvm use && npm run build` first.

| AC | | Proof |
|---|---|---|
| **AC1** ≤ 6 min | ✅ | **No test — a wall-clock criterion, so it is measured.** Three real runs: **112 s** (WI-2.2), **122 s** (WI-2.4b, watched in a browser), **137–158 s** (CLI). Budget is 360 s. |
| **AC2** exactly 3 directions | ✅ | `pytest tests/e2e/test_report_view.py::test_ac2_exactly_three_directions_each_with_a_problem_and_a_gap -m e2e` |
| **AC3** ≥ 2 resolvable ids | ✅ | `…::test_ac3_every_direction_cites_at_least_two_resolvable_ids -m e2e` — 8/8/12 ids, none unresolvable |
| **AC4** provenance by type | ✅ | `pytest tests/test_evidence.py::test_ac4_provenance_is_enforced_per_source_type tests/test_evidence.py::test_ac4_a_paper_must_derive_from_a_two_hundred_api_query` |
| **AC5** no `url` in LLM schemas | ✅ | `pytest tests/test_llm_schemas.py::test_ac5_no_llm_output_model_declares_a_source_field tests/test_llm_schemas.py::test_ac5_declaring_a_source_field_is_a_definition_time_error` — the second makes it a **class-definition-time `TypeError`**, not a lint |
| **AC6** sliders < 100 ms, no network | ✅ | `pytest tests/e2e/test_report_view.py::test_ac6_moving_a_slider_reorders_with_zero_network_requests -m e2e` — **measured 51.9 ms**, zero requests |
| **AC7** ≥ 15 events, stays visible | ✅ | `pytest tests/e2e/test_timeline.py -k ac7 -m e2e` — 42 rows from 162 events; 15 distinct states seen during a live run |
| **AC8a** server replays from 0 | ✅ | `pytest tests/test_sse.py -k ac8a` — plus two live `curl -N` tabs that joined 25 s in and got all 88 prior events |
| **AC8b** refresh reconnects | ✅ | `pytest tests/e2e/test_shell.py::test_ac8b_a_deep_linked_run_survives_a_browser_refresh -m e2e` |
| **AC9** broken profile → warning | ✅ | `pytest tests/e2e/test_warnings.py::test_ac9_a_broken_profile_url_completes_with_a_visible_warning -m e2e` (browser, whole stack) and `tests/test_pipeline.py::test_ac9_an_unreachable_profile_still_produces_a_finished_run` (no-probe path) |
| **AC10a** unknown id dropped + warned | ✅ | `pytest tests/test_llm.py::test_structured_drops_evidence_ids_that_do_not_resolve` |
| **AC10b** retry once, then flag | ✅ | `pytest tests/test_llm_schemas.py::test_ac10b_below_floor_retries_once_then_flags_thin_evidence` |
| **AC11** paper + grant_doc per direction | ✅ | `pytest tests/e2e/test_report_view.py::test_ac11_every_direction_cites_a_paper_and_a_grant_document -m e2e` — 12 distinct papers in the store |
| **AC12** trend + citing cited | ✅ | `pytest tests/test_pipeline.py::test_ac12_every_direction_gets_a_trend_and_a_citing_count_with_a_row_behind_it` |
| **AC13** every `report.md` link is stored | ✅ | `pytest tests/test_report.py -k ac13` — both halves: every link resolves, **and** no URL in the file could have come from a model |
| **AC14** probe < 20 s, answer reaches the brief | ✅ | `pytest tests/test_probe.py::test_ac14_live_probe_completes_inside_twenty_seconds -m live` — **18.8 s**; and `tests/e2e/test_shell.py -k ac14 -m e2e` for the two-step submit |

**Run them all:** `pytest` (**285** hermetic) · `pytest tests/e2e -m e2e` (**43** browser) · `pytest -m live` (**8** network). 336 in total — the counts are `--collect-only` output, not from memory.

---

## Traceability

| AC | Work item(s) |
|---|---|
| AC1 ≤6 min | WI-1.6d (orchestration), timed in WI-2.6 |
| AC2 3 directions | WI-1.6b, WI-1.6c, WI-1.7, WI-2.5 |
| AC3 ≥2 evidence IDs | WI-1.2, WI-1.6c, WI-2.5 |
| AC4 provenance by type | WI-1.2, WI-1.4, WI-1.5 |
| AC5 no `url` in LLM schemas | WI-1.2 |
| AC6 sliders <100 ms | WI-2.5 |
| AC7 ≥15 events | WI-1.3, WI-1.6d, WI-2.4b |
| AC8a server replay | WI-2.2 |
| AC8b refresh reconnect | WI-2.4a |
| AC9 graceful degradation | WI-1.4, WI-1.5, WI-1.6d, WI-2.6 |
| AC10a / AC10b | WI-1.2 |
| AC11 ≥12 paper rows | WI-1.5 (`fetch_top_works`), WI-1.6c |
| AC12 trend + citing cited | WI-1.5, WI-1.6d |
| AC13 report.md links | WI-1.7 |
| AC14 pre-flight clarification | WI-1.4b, WI-2.1, WI-2.4a |

Every AC has an owner whose **Done** line actually tests it. Enabling-only items (no AC of their own): WI-0.0, WI-0.1 and WI-1.1

---

## Critical path

```
0.0 → 0.1 → 0.2 → 1.1 → 1.2 → 1.4 → 1.4b → 1.5 → 1.6a → 1.6b → 1.6c → 1.6d → 1.7 → 2.1 → 2.4a → 2.5
```

Side branches (block nothing on the path): **1.0** (do it early anyway — it unblocks 2.5 if Day 1 slips), **1.3 → 2.2 → 2.4b**, **2.3**.

> For one developer, critical path ≡ total effort. The graph only tells you **ordering** — and the one thing it says loudly is: **WI-1.0 and WI-1.3 are cheap insurance against the most likely failure**, which is Day 1 running long and Day 2 having nothing to render.

**Riskiest item: WI-1.6c** — one call producing gaps + 27 scores + narrative for 3 directions, with an open-ended "make the scores spread" tuning loop at ~45 s per Pro round-trip. The per-direction fallback is written down so you don't have to invent it at 9 pm.

## Cut order if behind

1. Score matrix → plain per-criterion list *(WI-2.5)*
2. PDF upload → URL-only grant input *(WI-2.1)*
3. `report.md` export *(WI-1.7)*
4. `ingest_profile` extra links → seed page only *(WI-1.4)*
5. Timeline richness → a flat event list *(WI-2.4b)*

**Never cut:** WI-1.2 (evidence store), the AC5 test, the weight sliders, WI-1.0 (report fixture), WI-2.3 (fixture replayer).

## Definition of done

- [ ] All 16 ACs ticked in the traceability table
- [ ] `pytest` green, `pytest -m live` green, `ruff` clean
- [ ] One real cold run recorded as a fixture, with its wall-clock time written down
- [ ] A deliberate-failure run recorded (AC9)
- [ ] `README` names what is stubbed: **unverified identity, 2-signal gap check, abstracts not full text, no competitor analysis**
