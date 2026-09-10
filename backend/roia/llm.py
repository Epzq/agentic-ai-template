"""Gemini plumbing — one structured call, used four times.

There is no tool-calling loop. Control flow is plain Python and each call is a single
request with a JSON schema attached, which removes ``thought_signature`` round-tripping,
``TOO_MANY_TOOL_CALLS`` and request-limit tuning — the three things most likely to eat a day.

**The model never authors a source.** It receives a numbered catalogue of evidence Python
already minted and returns IDs; ``llm_schemas.LLMOutput`` makes a schema with a ``url``
field impossible to define (AC5), and validation drops any ID that does not resolve (AC10a).

``serialize_catalogue`` is called **per direction**, never once for the whole run: a single
undifferentiated 200-row catalogue degrades ID-citation accuracy and lets direction 1 cite
direction 3's papers.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

from google import genai
from google.genai import types
from pydantic import ValidationError

from roia.config import Settings, get_settings
from roia.evidence import THIN_EVIDENCE, CitationContext, EvidenceStore, WarnFn
from roia.ingest import Artefact, DocumentSet
from roia.llm_schemas import (
    SCORED_CRITERIA,
    Assessment,
    CandidateDirection,
    Candidates,
    Capabilities,
    CitesEvidence,
    DirectionDraft,
    GrantBrief,
    LLMOutput,
    below_floor,
)
from roia.openalex import WorkRef

#: Generous: a truncated JSON object fails validation, and a retry costs more than the
#: tokens would have. WI-1.6c sets its own, higher.
MAX_OUTPUT_TOKENS = 8192
#: Extraction, not judgement — the same answer every time is what we want.
TEMPERATURE = 0.0

#: warning codes
LLM_FAILED = "llm_failed"
LLM_INVALID_OUTPUT = "llm_invalid_output"
QUOTE_UNVERIFIED = "quote_unverified"

_PAGE_MARKER = re.compile(r"\[p\.\d+\]\s*")


def _thinking_level(name: str) -> types.ThinkingLevel:
    """``"low"`` / ``"high"`` to the SDK enum, falling back rather than raising on a typo."""
    try:
        return types.ThinkingLevel(name.upper())
    except ValueError:
        return types.ThinkingLevel.LOW


#: A hung model call has no natural end. `structured()` promises never to raise and to
#: degrade into `warning{llm_failed}`, but with no timeout there was nothing to degrade
#: *from*: the worker thread waits, `run.finished` is never emitted, the SSE stream stays
#: open, and the page shows a spinner for as long as anyone is willing to look at it.
#:
#: 300 s against AC1's 360 s for the whole run. The assessment is the longest call and has
#: been measured at 84–411 s at `thinking="high"`; at `ASSESSMENT_THINKING` it is ~94 s, so
#: this is roughly triple the expected worst case — late enough not to cut off a slow but
#: healthy call, early enough that the run still ends and says why.
LLM_TIMEOUT_S = 300


@lru_cache(maxsize=4)
def _client_for(api_key: str) -> genai.Client:
    """One client per key. Cached rather than module-level so importing is side-effect free."""
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=LLM_TIMEOUT_S * 1000),  # the SDK takes ms
    )


def structured[T: LLMOutput](
    prompt: str,
    schema: type[T],
    *,
    model: str,
    thinking: str = "low",
    max_output_tokens: int = MAX_OUTPUT_TOKENS,
    context: CitationContext | None = None,
    warn: WarnFn | None = None,
    client: genai.Client | None = None,
    settings: Settings | None = None,
) -> T | None:
    """One structured call. Returns a validated ``schema`` instance, or ``None``.

    Never raises: a refusal, a timeout, a truncated response or a schema violation all
    become ``warning{llm_failed | llm_invalid_output}`` and a ``None`` the caller can
    degrade around (AC9). ``context`` carries the evidence store, so unresolvable IDs are
    dropped during validation rather than reaching the report.
    """
    active = settings or get_settings()
    api = client or _client_for(active.gemini_api_key)

    try:
        response = api.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=schema.model_json_schema(),
                thinking_config=types.ThinkingConfig(thinking_level=_thinking_level(thinking)),
                max_output_tokens=max_output_tokens,
                temperature=TEMPERATURE,
            ),
        )
    except Exception as exc:  # noqa: BLE001 - the SDK raises a wide family; none may escape
        if warn is not None:
            warn(LLM_FAILED, f"{schema.__name__} via {model}: {type(exc).__name__}: {exc}")
        return None

    text = (response.text or "").strip()
    if not text:
        if warn is not None:
            warn(LLM_FAILED, f"{schema.__name__} via {model}: empty response")
        return None

    try:
        return schema.model_validate_json(text, context=context)
    except ValidationError as exc:
        if warn is not None:
            warn(
                LLM_INVALID_OUTPUT,
                f"{schema.__name__} via {model} returned {exc.error_count()} schema "
                f"violation(s): {exc.errors()[0].get('msg', '')}",
            )
        return None


def serialize_catalogue(ids: list[str], store: EvidenceStore) -> str:
    """The numbered evidence catalogue a model may cite from.

    Called **per direction** with that direction's own query results, the grant rows and its
    trend/citing rows — not once for the whole run.
    """
    lines: list[str] = []
    for evidence_id in ids:
        row = store.get(evidence_id)
        if row is None:
            continue
        head = f"[{row.id}] {row.source_type}"
        if row.year:
            head += f" ({row.year})"
        head += f" — {row.title}"
        if row.authors:
            head += f". {', '.join(row.authors[:4])}"
        lines.append(f"{head}\n    {row.summary}" if row.summary else head)
    return "\n".join(lines)


def serialize_documents(documents: DocumentSet, store: EvidenceStore) -> str:
    """Document text with each page labelled by the evidence ID that carries it.

    The catalogue alone will not do for LLM #1 and #2: an evidence row's ``summary`` is
    capped at 400 chars, so a model given only the catalogue would be extracting
    requirements from the first paragraph of each page. This hands over the full text while
    keeping every passage attributable to a row the reader can open.
    """
    blocks: list[str] = []
    for artefact in documents.artefacts:
        blocks.extend(_artefact_blocks(artefact, store))
    return "\n\n".join(blocks)


def _artefact_blocks(artefact: Artefact, store: EvidenceStore) -> list[str]:
    if not artefact.text.strip():
        return []
    if artefact.kind != "pdf" or not artefact.evidence_ids:
        head = artefact.evidence_ids[0] if artefact.evidence_ids else "unstored"
        return [f"[{head}] {artefact.name}\n{artefact.text}"]

    # _read_pdf writes "[p.N] body" per page, joined by a blank line, and evidence_ids are
    # minted in the same order — so the split lines the two up.
    pages = [p for p in _PAGE_MARKER.split(artefact.text) if p.strip()]
    blocks: list[str] = []
    for evidence_id, page_text in zip(artefact.evidence_ids, pages, strict=False):
        row = store.get(evidence_id)
        title = row.title if row is not None else artefact.name
        blocks.append(f"[{evidence_id}] {title}\n{page_text.strip()}")
    return blocks


def verify_quotes(
    quotes: list[tuple[str, str]], source: str, *, warn: WarnFn | None = None
) -> list[str]:
    """Check each quote is an exact substring of what we retrieved.

    ``demo-spec.md`` §4: exact substring only, **log failures, never drop**. A quote that
    cannot be found is reported and kept — removing it would hide the problem, and the
    surrounding claim is still the model's to answer for.

    Takes ``(label, quote)`` pairs and returns the labels that failed.
    """
    haystack = _squash(source)
    failed: list[str] = []
    for label, quote in quotes:
        needle = _squash(quote)
        if not needle or needle in haystack:
            continue
        failed.append(label)
        if warn is not None:
            warn(QUOTE_UNVERIFIED, f'{label}: "{quote[:120]}" is not verbatim in the source')
    return failed


#: Markup ``pymupdf4llm`` adds, which was never in the document. Comparing a quote against
#: our own asterisks would fail 7 of 16 real quotes on the demo call for no good reason.
_OUR_MARKUP = re.compile(r"<sup>.*?</sup>|<br\s*/?>|[*_`]")


def _squash(text: str) -> str:
    """Normalise for an exact-content comparison.

    Whitespace-insensitive because PDF extraction breaks lines mid-sentence, and
    markup-insensitive because the markdown emphasis is ours, not the source's. Everything
    else must match: a stitched-together quote still fails, which is the point.
    """
    return re.sub(r"\s+", " ", _OUR_MARKUP.sub("", text)).strip().lower()


# --- LLM #1: the grant brief -----------------------------------------------------------

GRANT_BRIEF_PROMPT = """\
You are reading the documents of a research funding call. Extract what the call asks for.

Rules:
- Extract only what the documents say. If something is not stated, leave it empty.
- Every requirement and criterion must carry a `quote` that is **word-for-word** from the
  text below, and `evidence_ids` naming the bracketed IDs the quote came from.
- Do not summarise a quote. Copy it.
{answers}
CALL DOCUMENTS
==============
{documents}
"""


def grant_brief(
    documents: DocumentSet,
    store: EvidenceStore,
    *,
    answers: str = "",
    warn: WarnFn | None = None,
    client: genai.Client | None = None,
    settings: Settings | None = None,
) -> GrantBrief | None:
    """LLM #1 — the call's requirements and criteria, each with a verbatim quote.

    ``answers`` is ``answers_brief(resolve_answers(...))`` from the pre-flight probe. It is
    the only path by which the applicant's chosen call reaches the brief: on the demo pair
    the page carries two calls with two different deadlines, and without this the brief
    describes both (AC14).
    """
    active = settings or get_settings()
    source = serialize_documents(documents, store)
    if not source.strip():
        if warn is not None:
            warn(LLM_FAILED, "no grant document text was recovered; skipping the grant brief")
        return None

    prompt = GRANT_BRIEF_PROMPT.format(
        answers=f"\n{answers}\n" if answers else "",
        documents=source,
    )
    brief = structured(
        prompt,
        GrantBrief,
        model=active.model_fast,
        context=CitationContext(store=store, warn=warn),
        warn=warn,
        client=client,
        settings=active,
    )
    if brief is not None:
        verify_quotes(
            [(f"requirement {r.text[:40]!r}", r.quote) for r in brief.requirements]
            + [(f"criterion {c.name!r}", c.quote) for c in brief.criteria],
            source,
            warn=warn,
        )
    return brief


# --- LLM #2: the applicant's capabilities ----------------------------------------------

CAPABILITIES_PROMPT = """\
You are reading a researcher's public page and the titles of their indexed publications.
Summarise what they can demonstrably do.

Rules:
- Ground every claim in the material below. Each entry in `expertise` must carry at least
  one ID in `evidence_ids`, copied from a bracketed marker such as `[e23]` in the PROFILE
  section — write it as `e23`, without the brackets.
- The publication list is **titles and years only** — you have not read those papers, so do
  not describe their findings. It carries no IDs, so cite the profile for what it supports.
- Prefer specific methods and domains over adjectives.

PROFILE
=======
{documents}

INDEXED PUBLICATIONS ({count} most cited)
=========================================
{works}
"""


def capabilities(
    documents: DocumentSet,
    works: list[WorkRef],
    store: EvidenceStore,
    *,
    warn: WarnFn | None = None,
    client: genai.Client | None = None,
    settings: Settings | None = None,
) -> Capabilities | None:
    """LLM #2 — expertise, methods and domains, from the profile page and work titles."""
    active = settings or get_settings()
    source = serialize_documents(documents, store)
    if not source.strip():
        if warn is not None:
            warn(LLM_FAILED, "no profile text was recovered; skipping the capabilities call")
        return None

    listing = "\n".join(
        f"- {w.title} ({w.year or 'n.d.'}, {w.cited_by_count} citations)" for w in works
    )
    prompt = CAPABILITIES_PROMPT.format(
        documents=source, works=listing or "(none retrieved)", count=len(works)
    )
    return structured(
        prompt,
        Capabilities,
        model=active.model_fast,
        context=CitationContext(store=store, warn=warn),
        warn=warn,
        client=client,
        settings=active,
    )



# --- LLM #3: candidate directions ------------------------------------------------------

#: OpenAlex `title_and_abstract.search` is conjunctive: every extra word narrows the result
#: set hard. Verified while building WI-1.5 — "embodied AI assistant human action
#: anticipation robot" returns **zero** works, while "intent prediction human robot
#: collaboration" returns 66. A model left to its own devices writes the first kind.
CANDIDATES_PROMPT = """\
You are advising a researcher on what to propose under a specific funding call.

Below is what the call asks for, and what this researcher can demonstrably do. Propose
exactly 3 research directions they should consider, and 3 search queries for each.

Rules:
- Each direction must be a plausible bridge between something the call wants and something
  this researcher can actually do. Say which, in the rationale.
- **Do not claim anything about the state of the literature.** You have not been shown any
  papers. Do not write that something is under-explored, that a gap exists, that nobody has
  done it, or that a field is emerging. You have no basis for any of that yet, and those
  claims are written later by a step that reads the evidence.
- Queries are for a keyword search over titles and abstracts. Keep each to 3-6 plain words.
  No boolean operators, no quotes, no author names, no year filters. Every extra word
  shrinks the result set, and a query that returns nothing is a wasted direction.
- Make the 3 directions genuinely different from each other, not three phrasings of one.

THE CALL
========
{brief}

THE RESEARCHER
==============
{capabilities}
"""


def candidate_directions(
    brief: GrantBrief,
    caps: Capabilities,
    *,
    warn: WarnFn | None = None,
    client: genai.Client | None = None,
    settings: Settings | None = None,
) -> Candidates | None:
    """LLM #3 — three directions and nine queries. **No literature in context.**

    This call is given the grant brief and the applicant's capabilities, and nothing else.
    It cannot be handed papers: there is no parameter to pass them through, and the output
    schema has nowhere to put a claim about the field. Python then runs the queries, and
    LLM #4 writes the gaps with what came back.
    """
    active = settings or get_settings()
    prompt = CANDIDATES_PROMPT.format(
        brief=brief.model_dump_json(indent=2),
        capabilities=caps.model_dump_json(indent=2),
    )
    return structured(
        prompt,
        Candidates,
        model=active.model_fast,
        warn=warn,
        client=client,
        settings=active,
    )


# --- LLM #4: the assessment ------------------------------------------------------------
#
# This is the call that has read the literature. LLM #3 proposed directions with no papers
# in context; the queries have since been run, the most-cited works fetched and their
# abstracts stored. Only now can a gap be asserted, and only against rows in the catalogue.

#: 27 anchored sentences — 9 criteria x what a 2, a 5 and an 8 look like.
#:
#: Anchors exist because a model scoring several items on several criteria in one shot
#: shows **score compression**: everything lands 6-8, and weights stop mattering. That kills
#: the weight slider, which is the demo's third claim. Two of the nine are defined here for
#: completeness but are **not sent** — the demo scores them `None` (non-goal §4), and
#: offering a rubric for a criterion we will not score invites the model to score it.
RUBRICS: dict[str, dict[int, str]] = {
    "grant_alignment": {
        2: "Fits the funder's general remit but misses the call's stated objectives; you "
           "would have to argue the connection.",
        5: "Addresses some stated objectives and satisfies eligibility, but not the "
           "criteria the call says it weighs first.",
        8: "Speaks directly to the call's leading evaluation criterion in the call's own "
           "words, and eligibility is satisfied without argument.",
    },
    "scientific_novelty": {
        2: "A competent application of established methods to a new dataset; the dataset "
           "is the contribution.",
        5: "A meaningful extension of a known method — nobody would be surprised by the "
           "result, but it has not been done.",
        8: "Reformulates the problem so that a question nobody could previously ask "
           "becomes answerable.",
    },
    "importance": {
        2: "Solving it improves a benchmark number that few outside the subfield track.",
        5: "Solving it removes a real obstacle for one research community.",
        8: "Solving it changes what a whole class of downstream systems can be trusted "
           "to do.",
    },
    "applicant_fit": {
        2: "The applicant would be learning the core method from scratch; the profile "
           "shows no adjacent work.",
        5: "The applicant has one of the two halves — the domain or the method — and would "
           "need a collaborator for the other.",
        8: "The direction sits on work the applicant is already funded to do, and the "
           "profile shows outputs in it.",
    },
    "feasibility": {
        2: "Needs infrastructure, data or approvals the evidence does not show the "
           "applicant has, inside the call's duration.",
        5: "Achievable with effort, but one substantial dependency — a platform, a cohort, "
           "an approval — is unresolved.",
        8: "Every ingredient is evidenced as already in place; the risk is scientific, "
           "not logistical.",
    },
    "competitive_differentiation": {  # not scored in the demo (non-goal §4)
        2: "Indistinguishable from what several visible groups are already doing.",
        5: "A recognisable variation on an active line of work.",
        8: "Approaches the problem from a direction the active groups have not taken.",
    },
    "collaboration_potential": {  # not scored in the demo (non-goal §4)
        2: "A single-investigator project with no natural partner.",
        5: "Would benefit from one collaborator who is plausibly available.",
        8: "Requires, and would attract, the multidisciplinary team the call asks for.",
    },
    "impact_potential": {
        2: "The realistic endpoint is a paper and a benchmark entry.",
        5: "The realistic endpoint is a tool or dataset another group would adopt.",
        8: "The realistic endpoint is a capability a named user community can act on, "
           "with a measurable benchmark.",
    },
    "evidence_strength": {
        2: "The claim rests on one retrieved record, or on a query that returned almost "
           "nothing.",
        5: "Several retrieved records support the claim, but none were read beyond their "
           "titles.",
        # Not "read in full": the run retrieves abstracts, capped at 400 characters. An
        # anchor describing evidence the system cannot gather invites the model to award it.
        8: "Several papers' abstracts were retrieved, and a trend and a citing count both "
           "point the same way.",
    },
}

#: The assessment is the longest output in the run: 3 directions x (gap + 7 rationales +
#: strengths + weaknesses). A truncated JSON object fails validation and costs the stage.
#:
#: ⚠️ **Thinking tokens count against this budget.** A run at 24,000 produced 8,175 thought
#: + 15,811 output = 23,986 and truncated mid-JSON, which failed validation, fell back to
#: three per-direction calls and took 323 s. The model's ceiling is 65,536, so this leaves
#: room for the thinking as well as the answer. Raising the cap alone is not the fix: at
#: 48,000 the model simply wrote more, and one call ran past 400 s — longer than AC1 allows
#: for the entire run. The prompt caps the prose instead, and this caps the accident.
ASSESSMENT_MAX_OUTPUT_TOKENS = 32_000
#: `high` measured 84 s, 233 s and 411 s on the same prompt — too variable against
#: AC1's 360 s for the *whole* run. `medium` is the same model, deliberating less.
ASSESSMENT_THINKING = "medium"

#: Claim C3: the sliders have to move something. Below this the report is nine numbers
#: that all say the same thing.
SPREAD_MIN = 1.5
CRITERION_RANGE_MIN = 3.0
CRITERIA_NEEDING_RANGE = 4
#: At least this many criteria must re-rank the cards, or the sliders are decoration.
MIN_RERANKING_CRITERIA = 2
COMPRESSED_SCORES = "compressed_scores"


@dataclass
class DirectionEvidence:
    """One candidate direction and the evidence rows it is allowed to cite.

    Kept per direction on purpose: a single undifferentiated catalogue degrades ID-citation
    accuracy and lets direction 1 cite direction 3's papers.
    """

    candidate: CandidateDirection
    evidence_ids: list[str]


def rubric_text(criteria: Sequence[str] = SCORED_CRITERIA) -> str:
    """The anchored rubric block, for the criteria actually being scored."""
    blocks = []
    for name in criteria:
        anchors = RUBRICS[name]
        blocks.append(
            f"{name}\n"
            f"  2 = {anchors[2]}\n"
            f"  5 = {anchors[5]}\n"
            f"  8 = {anchors[8]}"
        )
    return "\n".join(blocks)


ASSESSMENT_PROMPT = """\
You are assessing research directions for a specific funding call, with the evidence that
was actually retrieved for each one in front of you.

For every direction, write an evidence-backed gap and score it on {n} criteria.

Rules on evidence:
- `evidence_ids` may only contain IDs from **that direction's own catalogue** below. An ID
  from another direction's catalogue is wrong even if it is a real ID.
- The gap must rest on what the catalogue shows. Say what the retrieved records do and do
  not contain. **Finding nothing means "we did not find it", never "nobody has done it".**
- Every number you state must come from a catalogue entry, and you must cite that entry.
  Do not estimate counts.
- Each direction needs at least 2 evidence IDs overall, and each criterion at least 1.
- `grant_alignment` **must cite at least one `grant_doc` entry** — a page of the call's own
  documents. Alignment argued without pointing at the call is an assertion, and the call's
  landing page is not the same thing as the document that states the criteria.
- Each direction must cite at least one `paper` entry: a work whose abstract you were given.
  A search result you were not shown the abstract of is not something you have read.

Rules on scoring:
- For each criterion, first decide **the order of the three directions** on that criterion,
  then assign values consistent with that order. Do not score each direction in isolation.
- Use the anchors. A criterion where all three directions land within a point of each other
  means you have not committed to an ordering.

Length — these are cards a reader scans, not an essay:
- `problem_statement` and `evidence_backed_gap`: at most 120 words each.
- Each `rationale`: **one or two sentences**, naming the evidence it rests on.
- `key_strengths` and `key_weaknesses`: at most 3 items each, one sentence per item.

ANCHORED RUBRIC
===============
{rubric}

{directions}
"""

_DIRECTION_BLOCK = """\
DIRECTION {n}: {title}
{rule}
Why it was proposed: {rationale}

Evidence catalogue for DIRECTION {n} — cite only these IDs:
{catalogue}
"""


def _assessment_prompt(items: Sequence[DirectionEvidence], store: EvidenceStore) -> str:
    blocks = [
        _DIRECTION_BLOCK.format(
            n=index,
            title=item.candidate.title,
            rule="=" * (len(item.candidate.title) + 12),
            rationale=item.candidate.rationale,
            catalogue=serialize_catalogue(item.evidence_ids, store),
        )
        for index, item in enumerate(items, start=1)
    ]
    return ASSESSMENT_PROMPT.format(
        n=len(SCORED_CRITERIA), rubric=rubric_text(), directions="\n\n".join(blocks)
    )


def check_spread(directions: Sequence[DirectionDraft]) -> tuple[float, list[str]]:
    """``(overall spread, criteria whose range clears the bar)``.

    Pure arithmetic over the model's values — this measures compression, it does not fix it.
    """
    if len(directions) < 2:
        return 0.0, []
    means = [
        sum(getattr(d.scores, c).value for c in SCORED_CRITERIA) / len(SCORED_CRITERIA)
        for d in directions
    ]
    wide = [
        c for c in SCORED_CRITERIA
        if max(getattr(d.scores, c).value for d in directions)
        - min(getattr(d.scores, c).value for d in directions) >= CRITERION_RANGE_MIN
    ]
    return round(max(means) - min(means), 2), wide


def reranking_criteria(directions: Sequence[DirectionDraft]) -> list[str]:
    """Which criteria, weighted alone, change the order of the cards.

    This is claim C3 itself, rather than a proxy for it. A live run showed why the
    distinction matters: it scored a spread of **0.71**, well under the compression floor,
    while **six of seven** criteria re-ranked the cards and three different directions could
    each be made the winner. The directions were genuinely close on a flat weighting and
    the sliders were doing exactly their job — reporting "the sliders will barely re-rank"
    there would have been simply false.
    """
    if len(directions) < 2:
        return []
    order = [
        d.title for d in sorted(
            directions,
            key=lambda d: -sum(getattr(d.scores, c).value for c in SCORED_CRITERIA),
        )
    ]
    return [
        c for c in SCORED_CRITERIA
        if [d.title for d in sorted(directions, key=lambda d: -getattr(d.scores, c).value)]
        != order
    ]


def assess_directions(
    items: Sequence[DirectionEvidence],
    store: EvidenceStore,
    *,
    warn: WarnFn | None = None,
    client: genai.Client | None = None,
    settings: Settings | None = None,
) -> list[DirectionDraft]:
    """LLM #4 — gaps, seven scores and narrative, **with the evidence catalogue in context**.

    One call for all three directions, so the model can order them against each other on
    each criterion. If that call fails validation or runs out of tokens, it falls back to
    **one call per direction** — which still produces a report, but loses the cross-direction
    calibration the anchors depend on, so the spread is checked and reported either way.

    Returns however many directions survived; never raises.
    """
    active = settings or get_settings()
    context = CitationContext(store=store, warn=warn)

    def combined() -> Assessment | None:
        return structured(
            _assessment_prompt(items, store),
            Assessment,
            model=active.model_smart,
            # `ASSESSMENT_THINKING`, not a literal "high". The constant exists precisely to
            # keep this call away from `high`, whose own comment records 84 s / 233 s / 411 s
            # on the same prompt against AC1's 360 s for the *whole run* — and it was being
            # applied only to `_assess_singly`, the fallback that runs after this one has
            # already failed. The measurement that set it also found `medium` gives a better
            # score spread (4.71 vs 3.0), which is what the weight sliders need.
            thinking=ASSESSMENT_THINKING,
            max_output_tokens=ASSESSMENT_MAX_OUTPUT_TOKENS,
            context=context,
            warn=warn,
            client=client,
            settings=active,
        )

    assessment = combined()
    # AC10b: unresolvable IDs were dropped during validation. If that left a direction
    # under its floor, the call gets exactly one more attempt, and the better result wins —
    # a retry can never make the report worse.
    if assessment is not None and _under_floor(assessment.directions):
        retried = combined()
        if retried is not None and len(_under_floor(retried.directions)) < len(
            _under_floor(assessment.directions)
        ):
            assessment = retried

    directions = list(assessment.directions) if assessment is not None else _assess_singly(
        items, store, context, warn=warn, client=client, settings=active
    )
    for node in _under_floor(directions):
        _note(
            warn, THIN_EVIDENCE,
            f"{type(node).__name__} cites {len(node.evidence_ids)} resolvable evidence id(s) "
            f"after one retry; {type(node).evidence_floor} required",
        )

    if directions:
        spread, wide = check_spread(directions)
        flips = reranking_criteria(directions)
        # A small overall spread is not itself a problem — it means the directions are close
        # on a flat weighting, which can be the honest answer. The sliders are useless only
        # when too few criteria separate the directions, or when none of them re-ranks.
        if len(wide) < CRITERIA_NEEDING_RANGE or len(flips) < MIN_RERANKING_CRITERIA:
            _note(
                warn, COMPRESSED_SCORES,
                f"{len(wide)}/{len(SCORED_CRITERIA)} criteria separate the directions and "
                f"{len(flips)} re-rank them (overall spread {spread}) — the weight sliders "
                f"will barely move the cards",
            )
    return directions


def _assess_singly(
    items: Sequence[DirectionEvidence],
    store: EvidenceStore,
    context: CitationContext,
    *,
    warn: WarnFn | None,
    client: genai.Client | None,
    settings: Settings,
) -> list[DirectionDraft]:
    """The fallback: one call per direction, decided in advance rather than at 9 pm.

    Each call sees only its own direction, so the model cannot order the three against each
    other and the scores will compress. That is the price of getting a report at all.
    """
    _note(warn, LLM_INVALID_OUTPUT,
          "the combined assessment failed; retrying one direction at a time, which loses "
          "cross-direction calibration")
    drafts: list[DirectionDraft] = []
    for item in items:
        draft = structured(
            _assessment_prompt([item], store),
            DirectionDraft,
            model=settings.model_smart,
            thinking=ASSESSMENT_THINKING,
            max_output_tokens=ASSESSMENT_MAX_OUTPUT_TOKENS // 3,
            context=context,
            warn=warn,
            client=client,
            settings=settings,
        )
        if draft is not None:
            drafts.append(draft)
    return drafts


def _under_floor(directions: Sequence[DirectionDraft]) -> list[CitesEvidence]:
    """Every citing node still short of its own floor — directions need 2, scores need 1."""
    return [node for direction in directions for node in below_floor(direction)]


def _note(warn: WarnFn | None, code: str, message: str) -> None:
    if warn is not None:
        warn(code, message)
