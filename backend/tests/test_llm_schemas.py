"""WI-1.2 — AC5 (no source fields in LLM schemas), AC10a (drop) and AC10b (retry, flag)."""

from __future__ import annotations

import ast
import pathlib
from typing import ClassVar

import pytest
from pydantic import BaseModel

from roia.evidence import (
    THIN_EVIDENCE,
    UNRESOLVABLE_EVIDENCE_ID,
    CitationContext,
    EvidenceStore,
)
from roia.llm_schemas import (
    FORBIDDEN_FIELDS,
    MODEL_WROTE_A_URL,
    URL_REMOVED,
    CitesEvidence,
    LLMOutput,
    below_floor,
    call_with_evidence_floor,
    citing_nodes,
    llm_output_models,
)


class Cited(CitesEvidence):
    """Stands in for the direction-shaped outputs WI-1.6c will add."""

    title: str = ""


class Scored(CitesEvidence):
    """A criterion score needs one ID, not two (plan.md §7.2) — floors are per model."""

    evidence_floor: ClassVar[int] = 1
    value: float = 0.0


class Wrapper(LLMOutput):
    directions: list[Cited] = []


@pytest.fixture
def store() -> EvidenceStore:
    s = EvidenceStore()
    for n in (1, 2, 3):
        s.mint(source_type="api_query", url=f"https://api/{n}", title=f"q{n}", http_status=200)
    return s


# --- AC5 -----------------------------------------------------------------------------

def test_ac5_no_llm_output_model_declares_a_source_field() -> None:
    models = llm_output_models()

    assert models, "no LLMOutput subclasses imported — this check would pass vacuously"
    for model in models:
        named = FORBIDDEN_FIELDS & set(model.model_fields)
        assert not named, f"{model.__name__} declares {sorted(named)}"


def test_ac5_no_plain_basemodel_hides_under_an_llm_output() -> None:
    """The gap the test above cannot see.

    ``__pydantic_init_subclass__`` only fires for ``LLMOutput`` subclasses, and
    ``llm_output_models()`` only enumerates those. A plain ``BaseModel`` nested inside an
    LLM schema is therefore invisible to both — it may declare ``url`` freely, and the
    model would happily fill it in:

        class Ref(BaseModel):     # not an LLMOutput, so nothing fires
            url: str
        class Brief(LLMOutput):
            ref: Ref              # AC5 is now false and every AC5 test still passes

    Today every model reachable from an LLM schema is an ``LLMOutput``, so AC5 genuinely
    holds across the whole tree. This walks the tree and asserts that, so the day someone
    adds a convenience model without thinking about it, this fails rather than the
    guarantee silently going away.
    """
    from pydantic import BaseModel as PydanticBaseModel

    def nested(annotation: object) -> list[type]:
        """Every pydantic model mentioned anywhere in a field's annotation."""
        found: list[type] = []
        pending = [annotation]
        while pending:
            current = pending.pop()
            if isinstance(current, type) and issubclass(current, PydanticBaseModel):
                found.append(current)
            pending.extend(getattr(current, "__args__", ()) or ())
        return found

    roots = llm_output_models()
    assert roots, "no LLMOutput subclasses imported — this check would pass vacuously"

    seen: set[type] = set()
    offenders: list[str] = []
    descents = 0
    pending = [(model, model.__name__) for model in roots]
    while pending:
        model, path = pending.pop()
        if model in seen:
            continue
        seen.add(model)
        for name, field in model.model_fields.items():
            for child in nested(field.annotation):
                descents += 1
                if not issubclass(child, LLMOutput):
                    offenders.append(f"{path}.{name} -> {child.__name__}")
                pending.append((child, f"{path}.{name}"))

    # Every nested model happens to be a registered LLMOutput too, so comparing counts
    # proves nothing. What proves the walk ran is that it followed at least one field
    # into another model — `GrantBrief.requirements` alone guarantees that.
    assert descents > 0, "the walk never followed a field into a model — it proves nothing"
    assert not offenders, (
        "these models are reachable from an LLM schema but are not LLMOutput subclasses, "
        f"so the forbidden-field guard never runs on them: {offenders}"
    )


def test_ac5_declaring_a_source_field_is_a_definition_time_error() -> None:
    """The teeth. AC5 is not a rule to remember; the class cannot be created."""
    with pytest.raises(TypeError, match="author a source"):

        class Fabricates(LLMOutput):
            url: str

    with pytest.raises(TypeError, match="author a source"):

        class AlsoFabricates(CitesEvidence):
            source_title: str


# --- AC13: the model may not author a URL *inside* a field either ------------------------

def test_a_url_written_into_model_prose_is_removed_and_reported(store: EvidenceStore) -> None:
    """AC13: *"no URL in the file originated from an LLM response."*

    `FORBIDDEN_FIELDS` blocks a field **named** `url`. Nothing blocked a URL living inside
    `problem_statement.text`, and that field goes straight into `report.md` and, in the
    browser, through `react-markdown` — which renders both `[label](https://…)` and a bare
    `https://…` as a live anchor, sitting directly above the genuine evidence chips.

    Not hypothetical: LLM #4's catalogue is fetched page text, and two of the 85 summaries
    on the recorded demo run contain markdown links.
    """
    seen: list[tuple[str, str]] = []
    context = CitationContext(store=store, warn=lambda code, msg: seen.append((code, msg)))

    cited = Cited.model_validate(
        {"title": "See [Chen et al. 2024](https://nature.com/fake) and https://arxiv.org/abs/1",
         "evidence_ids": []},
        context=context,
    )

    assert "https://" not in cited.title
    assert "nature.com" not in cited.title
    assert "Chen et al. 2024" in cited.title, "the sentence survives; only the link goes"
    assert URL_REMOVED in cited.title
    assert MODEL_WROTE_A_URL in [code for code, _ in seen]


def test_urls_are_removed_from_list_fields_too() -> None:
    """`key_strengths` and `key_weaknesses` are `list[str]` and reach `report.md` verbatim."""
    class Bullets(LLMOutput):
        points: list[str] = []

    cleaned = Bullets.model_validate({"points": ["a https://evil.test/x b", "www.evil.test c"]})

    assert not any("evil.test" in point for point in cleaned.points)
    assert all(URL_REMOVED in point for point in cleaned.points)


def test_a_model_with_no_urls_is_left_exactly_as_it_was() -> None:
    """The common case must be untouched — no recorded fixture contains a URL in prose,
    and none of their golden values may move."""
    original = "The field is crowded: 1035 works since 2022 (e68)."

    assert Cited.model_validate({"title": original, "evidence_ids": []}).title == original


def test_the_report_ui_cannot_render_an_anchor_from_model_prose() -> None:
    """The second lock, asserted on the source because there is no JS test runner here.

    `rehype-sanitize`'s default schema allows `a` with `http`/`https` hrefs, and `remark-gfm`
    turns a bare URL into one. `Prose` therefore has to remove `a` from the schema: only
    `EvidenceChips` may produce a link in a report, because only it renders something Python
    actually fetched.
    """
    prose = pathlib.Path("../frontend/src/report/Prose.tsx")
    if not prose.is_file():  # pragma: no cover - the backend can be checked out alone
        pytest.skip("frontend/ is not present")
    source = prose.read_text()

    assert "defaultSchema" in source, "Prose must start from the default schema, not invent one"
    assert "tagNames" in source and "!== 'a'" in source, (
        "Prose must strip `a` from the sanitize schema, or model-authored prose can render "
        "a clickable citation to something nobody retrieved (AC13)"
    )
    assert "rehypeSanitize, NO_ANCHORS" in source, "the stripped schema must actually be passed"


def test_ac5_evidence_is_deliberately_out_of_scope() -> None:
    """Evidence has a url by design — it is minted from something we fetched."""
    from roia.evidence import Evidence

    assert "url" in Evidence.model_fields
    assert not issubclass(Evidence, LLMOutput)


def test_ac5_every_structured_call_in_llm_py_passes_an_llm_output_subclass() -> None:
    """AC5's third clause, now binding.

    This began as a tripwire while ``llm.py`` was empty: it asserted ``structured`` was not
    yet defined, so it would fail the moment WI-1.6a added it. It has done its job — the
    calls exist and are checked here. Both the positional and ``schema=`` forms are walked,
    so a refactor cannot slip an unnamed schema past AC5.
    """
    source = pathlib.Path("roia/llm.py").read_text()
    known = {m.__name__ for m in llm_output_models()}

    calls = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "structured"
    ]
    schemas: list[str] = []
    for call in calls:
        argument = next(
            (kw.value for kw in call.keywords if kw.arg == "schema"),
            call.args[1] if len(call.args) > 1 else None,
        )
        assert isinstance(argument, ast.Name), (
            f"structured() at line {call.lineno} passes a schema this test cannot verify; "
            f"pass a named LLMOutput subclass (AC5)"
        )
        schemas.append(argument.id)

    assert "def structured" in source, "roia/llm.py must define structured() (WI-1.6a)"
    assert schemas, "structured() is defined but never called — AC5 would pass vacuously"
    for name in schemas:
        assert name in known, f"structured() called with {name}, which is not an LLMOutput"


# --- AC10a ---------------------------------------------------------------------------

def test_ac10a_unknown_evidence_id_is_dropped_and_reported(store: EvidenceStore) -> None:
    warnings: list[tuple[str, str]] = []
    context = CitationContext(store=store, warn=lambda c, m: warnings.append((c, m)))

    cited = Cited.model_validate({"evidence_ids": ["e1", "e999", "e2"]}, context=context)

    assert cited.evidence_ids == ["e1", "e2"]
    assert context.dropped == ["e999"]
    assert [c for c, _ in warnings] == [UNRESOLVABLE_EVIDENCE_ID]
    assert "e999" in warnings[0][1]


def test_ac10a_drops_through_nested_models(store: EvidenceStore) -> None:
    context = CitationContext(store=store)

    wrapper = Wrapper.model_validate(
        {"directions": [{"evidence_ids": ["e1", "e42"]}, {"evidence_ids": ["e2", "e3"]}]},
        context=context,
    )

    assert [d.evidence_ids for d in wrapper.directions] == [["e1"], ["e2", "e3"]]
    assert context.dropped == ["e42"]


def test_validation_without_a_store_leaves_ids_untouched() -> None:
    assert Cited(evidence_ids=["e999"]).evidence_ids == ["e999"]


# --- AC10b ---------------------------------------------------------------------------

def _make_call(store: EvidenceStore, *payloads: dict[str, object]):
    """A fake LLM call returning each payload in turn, recording how often it ran."""
    attempts: list[dict[str, object]] = []

    def call() -> Wrapper:
        payload = payloads[min(len(attempts), len(payloads) - 1)]
        attempts.append(payload)
        return Wrapper.model_validate(payload, context=CitationContext(store=store))

    return call, attempts


def test_ac10b_below_floor_retries_once_then_flags_thin_evidence(store: EvidenceStore) -> None:
    thin_payload = {"directions": [{"evidence_ids": ["e1", "e998", "e999"]}]}
    call, attempts = _make_call(store, thin_payload)
    warnings: list[tuple[str, str]] = []

    output, thin = call_with_evidence_floor(call, warn=lambda c, m: warnings.append((c, m)))

    assert len(attempts) == 2, "one retry, not zero and not a loop"
    assert [n.evidence_ids for n in thin] == [["e1"]]
    assert output.directions[0].evidence_ids == ["e1"]
    assert [c for c, _ in warnings] == [THIN_EVIDENCE]


def test_ac10b_a_good_retry_is_kept(store: EvidenceStore) -> None:
    call, attempts = _make_call(
        store,
        {"directions": [{"evidence_ids": ["e999"]}]},
        {"directions": [{"evidence_ids": ["e1", "e2"]}]},
    )
    warnings: list[tuple[str, str]] = []

    output, thin = call_with_evidence_floor(call, warn=lambda c, m: warnings.append((c, m)))

    assert len(attempts) == 2
    assert thin == []
    assert output.directions[0].evidence_ids == ["e1", "e2"]
    assert warnings == []


def test_ac10b_a_worse_retry_is_discarded(store: EvidenceStore) -> None:
    """A retry must never be able to make the result worse than the first attempt."""
    call, attempts = _make_call(
        store,
        {"directions": [{"evidence_ids": ["e1", "e2"]}, {"evidence_ids": ["e999"]}]},
        {"directions": [{"evidence_ids": ["e997"]}, {"evidence_ids": ["e998"]}]},
    )

    output, thin = call_with_evidence_floor(call)

    assert len(attempts) == 2
    assert len(thin) == 1
    assert output.directions[0].evidence_ids == ["e1", "e2"]


def test_no_retry_when_everything_already_clears_its_floor(store: EvidenceStore) -> None:
    call, attempts = _make_call(store, {"directions": [{"evidence_ids": ["e1", "e2"]}]})

    _, thin = call_with_evidence_floor(call)

    assert len(attempts) == 1, "a clean first call must not cost a second round trip"
    assert thin == []


def test_floor_is_per_model_so_a_criterion_score_needs_only_one(store: EvidenceStore) -> None:
    class Direction(CitesEvidence):
        scores: list[Scored] = []

    node = Direction.model_validate(
        {"evidence_ids": ["e1", "e2"], "scores": [{"evidence_ids": ["e3"]}, {"evidence_ids": []}]},
        context=CitationContext(store=store),
    )

    assert len(citing_nodes(node)) == 3
    assert [type(n).__name__ for n in below_floor(node)] == ["Scored"]


def test_citing_nodes_walks_lists_dicts_and_plain_models(store: EvidenceStore) -> None:
    class Bag(BaseModel):
        by_name: dict[str, Cited]
        loose: Cited

    bag = Bag(by_name={"a": Cited(evidence_ids=["e1"])}, loose=Cited(evidence_ids=["e2"]))

    assert sorted(n.evidence_ids[0] for n in citing_nodes(bag)) == ["e1", "e2"]
