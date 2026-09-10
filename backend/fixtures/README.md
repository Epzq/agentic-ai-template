# Fixtures

The frozen demo inputs and the hand-authored contract sample. Everything here is committed so
the test suite is hermetic — a suite that fails on hotel wifi is a suite people stop running.

## The demo pair (WI-0.0)

**Grant — NRF Frontier Competitive Research Programme (F-CRP)**
`https://www.rgp.gov.sg/nrf-ar/crp`

Everything needed is reachable from that one URL with no browser, via three layers
(see `spikes/probe_grant_url.py`):

| Layer | Yields |
|---|---|
| 1. `trafilatura` | 2,287 chars — objectives, schemes, eligibility |
| 2. Next.js flight data | 3,090 chars — including **the call period, 23 Mar – 18 May 2026**, which trafilatura cannot see |
| 3. linked documents | 7 PDFs, two of them inside ZIPs |

**Profile — Basura Fernando**
`https://basurafernando.github.io/` (also `ROIA_DEMO_PROFILE_URL` in `.env`)

| Check (WI-0.0 gate) | Value | Threshold |
|---|---|---|
| OpenAlex author | [`A5090467618`](https://openalex.org/A5090467618) | resolves from name alone |
| Indexed works | **189** | ≥ 20 ✅ |
| Citations | **9,082** | — |
| Top topic, works since 2022 | **6,614** | ≥ 15 ✅ |

Top topics: multimodal machine learning applications · human pose and action recognition ·
image and video retrieval. Listed interests: visual reasoning, action prediction, action
recognition, transfer learning, embodied AI.

> A Singapore national call against an A\*STAR/NTU researcher, so eligibility genuinely applies
> rather than being trivially satisfied.
>
> ⚠️ F-CRP is **open-topic**, so `grant_alignment` scores against objectives and eligibility
> rather than a named priority list. T-CRP publishes themes if a sharper signal is ever wanted.

## Files

### `grant.pdf`
`F-CRP Call Information Sheet (2026).pdf` — 21 pages, 447,990 bytes, no OCR needed.
sha256 `a04308020652f7321a87533ead49ac208e94a3fb11ce188ab7699f3b5f11667e`.

Cached from inside a ZIP, which is why ingestion has to unzip in memory:
`https://assets.app.optical.gov.sg/rgp/production/published/base/pages/9/ee9b60cc-1ee9-4444-a2ba-327bd9b7fe56.zip?download=`

Load it as `pymupdf4llm.to_markdown(..., page_chunks=True)`. **The metadata key is
`page_number` here**, but it is `page` when `pymupdf-layout` is installed — always read it as
`md.get("page_number") or md.get("page")`.

Content worth knowing: §1 objectives and §2 eligibility on pages 1–2, the four evaluation
criteria (breakthrough potential, impact, implementation, team competency) at §3.3 on page 2,
and Appendix A's proposal-writing pointers on page 12.

### `report-sample.json`
The hand-authored report contract sample (WI-1.0). Three things at once: the shape WI-1.6c's
schemas must produce, the golden input for WI-1.7's ranking test, and what WI-2.5 renders if
Day 1 slips.

**Every value in it was retrieved live, never invented** — the grant quotes are exact substrings
of `grant.pdf`, the six papers are real OpenAlex works, and each `api_query` row's `url` is a
request that returned 200. 3 directions; 20 evidence rows (3 `grant_doc` + 1 `webpage` +
9 `api_query` + 6 `paper`); `e1`–`e5` shared, `e6`–`e10` / `e11`–`e15` / `e16`–`e20` owned by
D1 / D2 / D3 with no cross-citation. See WI-1.0's STATUS line in `execution-plan.md` for the
contract decisions it freezes.

### `crp-page.html` · `profile-page.html`
The two demo-pair pages as fetched on 2026-09-05 (74 KB and 171 KB). Recorded by WI-1.4 so the
ingestion tests are hermetic — they are what proves the three HTML layers still work without
hitting the network.

`crp-page.html` is the one that matters: the F-CRP **call period (23 Mar – 18 May 2026)** and the
seven document links exist *only* in its Next.js flight payload, so it is the regression test for
layer 2. `profile-page.html` is the input to `extract_identity`, which must yield
`("Basura Fernando", "basurafernando.github.io")`.

Both are also checked live by `pytest -m live`, which is what catches the sites changing.

### `run-001.jsonl` *(not yet — WI-1.6d)*
The event stream from the Day-1 CLI run, replayed by WI-2.3 as `?fixture=run-001` so the
frontend can be built without waiting five minutes for a live run. Must hold ≥ 15 events (AC7).
