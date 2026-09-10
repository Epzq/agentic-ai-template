"""Pydantic output schemas for the four LLM calls.

**No model here may declare a ``url``, ``source_title`` or ``link`` field (AC5).** That is
not a convention to remember — ``LLMOutput.__pydantic_init_subclass__`` raises at class
definition time, so a schema that tries to let the model author a source cannot be
imported, let alone called. The model receives a numbered evidence catalogue and returns
IDs; ``roia.evidence`` owns everything a chip actually links to.

Concrete schemas land with the calls that use them: **WI-1.6a** (``GrantBrief``,
``Capabilities``), **WI-1.6b** (candidate directions + queries), **WI-1.6c** (gaps, the 9
ordinal scores, narrative). This module gives them the base class, the citation validator
and the evidence-floor policy.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator

from roia.evidence import (
    EVIDENCE_FLOOR,
    THIN_EVIDENCE,
    CitationContext,
    WarnFn,
)

#: A model that named one of these would be authoring a source rather than citing one.
FORBIDDEN_FIELDS = frozenset({"url", "source_title", "link"})

#: AC13, the half `FORBIDDEN_FIELDS` cannot reach. That guard blocks a field *name*; this
#: blocks the *value*, because nothing stopped a URL living inside `problem_statement.text`
#: or a `rationale` — fields the schema quite reasonably allows.
MODEL_WROTE_A_URL = "model_wrote_a_url"

#: `[label](https://…)` collapses to `label`, so no renderer downstream can make an anchor.
_MARKDOWN_LINK = re.compile(r"\[([^\]\n]{0,300})\]\(\s*(?:https?://|www\.)[^)\s]*\s*\)", re.I)
#: A bare URL, including one left behind after the wrapper above is removed.
_BARE_URL = re.compile(r"(?:https?://|www\.)[^\s<>\"'\)\]]+", re.I)
#: Left in place of a removed URL. Visible on purpose — a silent deletion would leave a
#: sentence that reads as though it were never making a claim about a source at all.
URL_REMOVED = "(url removed)"


def strip_urls(value: str) -> tuple[str, int]:
    """Remove anything a reader or a markdown renderer would take for a source link.

    Returns the cleaned text and how many links were taken out.
    """
    removed = 0

    def _unwrap(match: re.Match[str]) -> str:
        nonlocal removed
        removed += 1
        return match.group(1)

    text = _MARKDOWN_LINK.sub(_unwrap, value)
    text, bare = _BARE_URL.subn(URL_REMOVED, text)
    return text, removed + bare

class LLMOutput(BaseModel):
    """Base class for every LLM output schema.

    ``extra="forbid"`` because structured output should return exactly the schema — an
    unexpected key means the schema and the prompt have drifted apart, and we would
    rather find out at validation than at render.
    """

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        """AC5, enforced structurally rather than by convention.

        Runs after Pydantic has built ``model_fields``, so it sees inherited fields too.
        """
        named = FORBIDDEN_FIELDS & set(cls.model_fields)
        if named:
            raise TypeError(
                f"{cls.__name__} declares {sorted(named)}, which would let the model author "
                f"a source. LLM outputs cite evidence IDs; only roia.evidence.Evidence "
                f"carries a URL (AC5)."
            )

    @model_validator(mode="after")
    def _no_model_authored_urls(self, info: ValidationInfo) -> LLMOutput:
        """AC13's second half: *"no URL in the file originated from an LLM response."*

        ``__pydantic_init_subclass__`` above forbids a field **named** ``url``. It says
        nothing about a URL sitting **inside** ``problem_statement.text`` or a
        ``rationale`` — and those fields go straight into the markdown template and, in the
        browser, through ``react-markdown``, which turns both ``[label](https://…)`` and a
        bare ``https://…`` into a live anchor. A fabricated citation, clickable, sitting
        directly above the genuine evidence chips.

        This is not hypothetical: the catalogue LLM #4 is told to ground its prose in is
        fetched page text, and on the recorded demo run two of its 85 summaries contain
        markdown links. Copying one through is an ordinary thing for a model to do.

        The URL is removed and the sentence kept. Rejecting the response would throw away a
        99-second scoring call over one bad token, and the claim without a link is ordinary
        unbacked prose — which the chips beside it already distinguish from cited fact.
        """
        removed = 0
        for name in type(self).model_fields:
            value = getattr(self, name, None)
            if isinstance(value, str):
                cleaned, count = strip_urls(value)
                removed += count
                if count:
                    setattr(self, name, cleaned)
            elif isinstance(value, list) and all(isinstance(item, str) for item in value):
                items, count = [], 0
                for item in value:
                    text, found = strip_urls(item)
                    items.append(text)
                    count += found
                removed += count
                if count:
                    setattr(self, name, items)

        if removed:
            warn = getattr(info.context, "warn", None)
            if callable(warn):
                warn(
                    MODEL_WROTE_A_URL,
                    f"{type(self).__name__} wrote {removed} URL(s) into its prose; removed. "
                    f"Only records this tool retrieved carry links (AC13).",
                )
        return self


class CitesEvidence(LLMOutput):
    """Mixin for any LLM output that cites evidence.

    The ``mode="after"`` validator drops IDs that do not resolve against the run's store
    and reports each one (AC10a). Dropping rather than raising is deliberate: one
    hallucinated token four minutes into a run should cost a chip, not the stage.

    Validating without a ``CitationContext`` is a no-op, so these models can be
    constructed freely in tests and fixtures.
    """

    #: How many resolvable IDs this node needs. AC3 says a direction needs 2; a single
    #: criterion score needs 1 (``plan.md`` §7.2), so subclasses override.
    evidence_floor: ClassVar[int] = EVIDENCE_FLOOR

    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _drop_unresolvable_evidence_ids(self, info: ValidationInfo) -> CitesEvidence:
        context = info.context
        if isinstance(context, CitationContext):
            self.evidence_ids = context.resolve(self.evidence_ids, type(self).__name__)
        return self


# --- LLM #1: the grant brief (WI-1.6a) -------------------------------------------------

class GrantRequirement(CitesEvidence):
    """Something the call requires of an applicant, with the sentence that says so."""

    evidence_floor: ClassVar[int] = 1

    text: str
    #: Verbatim from the call documents. Checked as an exact substring after validation —
    #: a quote that is not in the source is reported, never silently kept as if it were.
    quote: str


class GrantCriterion(CitesEvidence):
    """One evaluation criterion the proposal will be judged on."""

    evidence_floor: ClassVar[int] = 1

    name: str
    description: str
    quote: str


class GrantBrief(LLMOutput):
    """What the call asks for. LLM #1's output — extraction, not judgement."""

    call_title: str
    scheme: str = ""
    funder: str = ""
    #: "" when the documents do not state one, rather than a guess.
    call_period: str = ""
    objectives: str
    requirements: list[GrantRequirement] = Field(default_factory=list)
    criteria: list[GrantCriterion] = Field(default_factory=list)


# --- LLM #2: the applicant's capabilities (WI-1.6a) ------------------------------------

class Capability(CitesEvidence):
    """One thing the applicant can demonstrably do."""

    evidence_floor: ClassVar[int] = 1

    area: str
    detail: str


class Capabilities(LLMOutput):
    """What the applicant brings. LLM #2 sees the profile page and their work titles.

    It does **not** see abstracts — ``fetch_author_works`` returns ``WorkRef``s — so this
    is a summary of stated interests and publication titles, not of read papers.
    """

    researcher: str
    summary: str
    expertise: list[Capability] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)


# --- LLM #3: candidate directions (WI-1.6b) --------------------------------------------

class CandidateDirection(LLMOutput):
    """A direction worth investigating — **before** anyone has read the literature.

    There is deliberately no gap field here. At this point the system has seen the call and
    the applicant and nothing else, so any claim about what the field has or has not done
    would be invention. Gaps are written by LLM #4, with the evidence catalogue in front of
    it. Reversing that order is the exact hole revision 1 of the spec had.
    """

    title: str
    #: Why this pairing of call and applicant — grounded in the brief and the capabilities,
    #: never in what the literature supposedly lacks.
    rationale: str
    #: OpenAlex ``title_and_abstract.search`` queries. Three, so one weak phrasing does not
    #: sink the direction.
    queries: list[str] = Field(min_length=3, max_length=3)


class Candidates(LLMOutput):
    """LLM #3's whole output: three directions, nine queries, no claims about the field."""

    directions: list[CandidateDirection] = Field(min_length=3, max_length=3)


# --- LLM #4: the assessment (WI-1.6c) --------------------------------------------------

#: `demo-spec.md` §6.4, in order. The two the demo does not score are still listed, because
#: the report renders them as "not assessed" rather than omitting them.
CRITERIA = (
    "grant_alignment", "scientific_novelty", "importance", "applicant_fit", "feasibility",
    "competitive_differentiation", "collaboration_potential", "impact_potential",
    "evidence_strength",
)
#: Non-goal §4: scored `None`, excluded from the sum, weights renormalised over the seven.
NOT_ASSESSED = ("competitive_differentiation", "collaboration_potential")
SCORED_CRITERIA = tuple(c for c in CRITERIA if c not in NOT_ASSESSED)


class CriterionScore(CitesEvidence):
    """One judged criterion. Never a bare float — a heatmap cell clicks through to chips.

    `evidence_floor` is 1, not the default 2: a direction needs two records behind it
    (AC3), but a single criterion judged against a single quoted requirement is honest.
    """

    evidence_floor: ClassVar[int] = 1

    #: Redeclared **without a default**, so it lands in the JSON schema's `required` list.
    #: Inherited from `CitesEvidence` it is optional, and a model under length pressure
    #: simply omits it — a recorded run came back with every single `evidence_ids` empty and
    #: 30 `thin_evidence` warnings. "A score is never a bare float" has to be enforced by
    #: the schema, not asked for in prose.
    evidence_ids: list[str]

    value: float = Field(ge=0, le=10)
    rationale: str
    #: Always "judged" in the demo — all seven come from LLM #4. `plan.md` §7.1 would make
    #: `evidence_strength` and `feasibility` computed; that is post-demo.
    provenance: Literal["computed", "judged"] = "judged"


class DirectionSection(CitesEvidence):
    """A paragraph with its evidence attached at field level, not as inline tokens.

    Chips render beneath the text. Asking a model to embed `[[ev:e17]]` inside free prose
    fails: constrained decoding cannot enforce token discipline inside a string, and the
    failure mode is a visibly broken report.
    """

    evidence_floor: ClassVar[int] = 1

    #: Required, for the same reason as `CriterionScore.evidence_ids`.
    evidence_ids: list[str]

    text: str


class DirectionScores(LLMOutput):
    """The seven scored criteria, as named fields so the model gets a strict schema."""

    grant_alignment: CriterionScore
    scientific_novelty: CriterionScore
    importance: CriterionScore
    applicant_fit: CriterionScore
    feasibility: CriterionScore
    impact_potential: CriterionScore
    evidence_strength: CriterionScore


class DirectionDraft(CitesEvidence):
    """One assessed direction, as LLM #4 returns it.

    Python owns what is missing here: `rank` and `overall` are arithmetic (rule 2), and
    `thin_evidence` is set from `call_with_evidence_floor`'s verdict, never claimed by the
    model about itself.
    """

    title: str
    problem_statement: DirectionSection
    evidence_backed_gap: DirectionSection
    key_strengths: list[str] = Field(default_factory=list)
    key_weaknesses: list[str] = Field(default_factory=list)
    #: No `confidence` field, deliberately. It was the one thing here the model asserted
    #: about its own output with nothing behind it; `ranking.confidence_for` derives it from
    #: `evidence_strength`, which is rubric-scored and carries citations.
    scores: DirectionScores

    @model_validator(mode="after")
    def _inherit_cited_ids(self) -> DirectionDraft:
        """The direction cites the union of what its own fields cite.

        Asking the model to repeat at direction level what it already cited per field is
        redundant work it forgets — the first recorded run left this empty on all three
        directions while citing 3-6 IDs per section. AC3's "every direction cites >= 2
        evidence IDs" is about what stands behind the direction, and that is the union.

        Runs after ``CitesEvidence``'s validator on every nested model, so only resolvable
        IDs are gathered.
        """
        gathered = [
            *self.evidence_ids,
            *self.problem_statement.evidence_ids,
            *self.evidence_backed_gap.evidence_ids,
            *(eid for name in SCORED_CRITERIA for eid in getattr(self.scores, name).evidence_ids),
        ]
        self.evidence_ids = list(dict.fromkeys(gathered))
        return self


class Assessment(LLMOutput):
    """All three directions in one call, so the model can calibrate across them."""

    directions: list[DirectionDraft] = Field(min_length=3, max_length=3)


def llm_output_models() -> list[type[LLMOutput]]:
    """Every ``LLMOutput`` subclass currently imported, at any depth.

    Recursive on purpose: ``LLMOutput.__subclasses__()`` alone would miss anything
    subclassing ``CitesEvidence``, which is most of what WI-1.6c will add.
    """
    found: list[type[LLMOutput]] = []
    stack: list[type[LLMOutput]] = list(LLMOutput.__subclasses__())
    while stack:
        cls = stack.pop()
        if cls not in found:
            found.append(cls)
            stack.extend(cls.__subclasses__())
    return found


def citing_nodes(model: BaseModel) -> list[CitesEvidence]:
    """Every ``CitesEvidence`` in a validated output, root included, depth first."""
    found: list[CitesEvidence] = []
    seen: set[int] = set()

    def walk(value: Any) -> None:
        if isinstance(value, BaseModel):
            if id(value) in seen:
                return
            seen.add(id(value))
            if isinstance(value, CitesEvidence):
                found.append(value)
            for name in type(value).model_fields:
                walk(getattr(value, name, None))
        elif isinstance(value, (list, tuple, set)):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)

    walk(model)
    return found


def below_floor(model: BaseModel) -> list[CitesEvidence]:
    """Citing nodes left under their own ``evidence_floor`` after unresolvable IDs went."""
    return [n for n in citing_nodes(model) if len(n.evidence_ids) < type(n).evidence_floor]


def call_with_evidence_floor[T: BaseModel](
    call: Callable[[], T],
    *,
    warn: WarnFn | None = None,
) -> tuple[T, list[CitesEvidence]]:
    """Run an LLM call, retry **once** if anything came back under-cited, flag the rest.

    AC10b. The retry is a plain second attempt at the same call — at temperature the
    model often cites properly on the second pass, and one extra call is much cheaper
    than a direction the user cannot check. If the retry is no better it is discarded, so
    a retry can never make the result worse.

    Returns the chosen output and the nodes still below their floor; those are what the
    UI renders as ``thin_evidence``.
    """
    output = call()
    thin = below_floor(output)

    if thin:
        retried = call()
        retried_thin = below_floor(retried)
        if len(retried_thin) < len(thin):
            output, thin = retried, retried_thin

    if warn is not None:
        for node in thin:
            warn(
                THIN_EVIDENCE,
                f"{type(node).__name__} cites {len(node.evidence_ids)} resolvable evidence "
                f"id(s) after one retry; {type(node).evidence_floor} required.",
            )
    return output, thin
