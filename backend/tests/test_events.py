"""WI-1.3 — the event log the UI is driven by (AC7, AC9)."""

from __future__ import annotations

import json
import pathlib
from datetime import datetime

import httpx
import pytest

from roia.events import (
    EVENT_TYPES,
    IDENTITY_RESOLVED,
    RUN_FINISHED,
    RUN_STARTED,
    STAGE_FINISHED,
    STAGE_STARTED,
    TOOL_FINISHED,
    TOOL_STARTED,
    WARNING,
    Event,
    Run,
    read_jsonl,
)
from roia.evidence import EvidenceStore
from roia.ingest import ingest_profile


def test_emit_numbers_events_from_zero_and_stamps_them(tmp_path) -> None:
    run = Run("run-test", jsonl_path=tmp_path / "events.jsonl")

    first = run.emit(STAGE_STARTED, stage="ingest")
    second = run.emit(STAGE_FINISHED, stage="ingest", ms=1200)

    assert [first.seq, second.seq] == [0, 1]
    assert isinstance(first.ts, datetime) and first.ts <= second.ts
    assert len(run.events) == 2


def test_payload_fields_sit_at_the_top_level(tmp_path) -> None:
    """§6.3 specifies {seq, ts, type, …}, not a nested payload key."""
    run = Run("run-test", jsonl_path=tmp_path / "events.jsonl")

    event = run.emit(TOOL_FINISHED, tool="search_literature", ms=340, summary="15 hits")

    dumped = event.model_dump()
    assert dumped["tool"] == "search_literature" and dumped["ms"] == 340
    assert "payload" not in dumped


def test_emit_accepts_either_a_payload_dict_or_keywords(tmp_path) -> None:
    """OpenAlexClient's emit slot passes (type, payload); pipeline code reads better with
    keywords. One method has to take both or every call site needs an adapter."""
    run = Run("run-test", jsonl_path=tmp_path / "events.jsonl")

    from_dict = run.emit(IDENTITY_RESOLVED, {"author_id": "A1", "display_name": "Someone"})
    from_kwargs = run.emit(IDENTITY_RESOLVED, author_id="A1", display_name="Someone")

    assert from_dict.model_dump(exclude={"seq", "ts"}) == from_kwargs.model_dump(
        exclude={"seq", "ts"}
    )


def test_every_event_is_written_to_the_jsonl_file_as_it_happens(tmp_path) -> None:
    """Written per event, not at the end: a run that dies mid-way still leaves its trail."""
    path = tmp_path / "run.jsonl"
    run = Run("run-test", jsonl_path=path)

    run.started(grant_url="https://example.org/call", profile_url="https://example.org/me")
    run.warning("thin_literature", "only 3 works matched")

    lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["type"] == RUN_STARTED and first["inputs"]["grant_url"].endswith("/call")
    assert json.loads(lines[1])["code"] == "thin_literature"


def test_a_run_owns_its_file_and_does_not_append_to_a_stale_one(tmp_path) -> None:
    path = tmp_path / "run.jsonl"
    path.write_text('{"seq": 99, "ts": "2020-01-01T00:00:00Z", "type": "run.finished"}\n')

    run = Run("run-test", jsonl_path=path)
    run.emit(RUN_FINISHED)

    assert [e.seq for e in read_jsonl(path)] == [0]


def test_a_run_without_a_path_keeps_events_in_memory_only(tmp_path) -> None:
    run = Run("run-test")

    run.emit(RUN_STARTED)

    assert len(run.events) == 1
    assert list(tmp_path.iterdir()) == []


def test_read_jsonl_round_trips_a_recorded_run(tmp_path) -> None:
    """WI-2.3 replays these files, so what was written has to load back identically."""
    path = tmp_path / "run.jsonl"
    run = Run("run-test", jsonl_path=path)
    run.started(grant_url="https://example.org/call")
    run.identity_resolved("A5090467618", "Basura Fernando", "A*STAR", margin=0.0)
    run.finished()

    replayed = read_jsonl(path)

    assert [e.model_dump() for e in replayed] == [e.model_dump() for e in run.events]
    assert replayed[1].model_dump()["confidence"] == "unverified"


# --- the vocabulary ---------------------------------------------------------------------

def test_the_typed_constructors_cover_the_whole_vocabulary(tmp_path) -> None:
    """§6.3 lists ten event types. A constructor missing here is an event nobody emits."""
    store = EvidenceStore()
    evidence = store.get(store.mint(source_type="webpage", url="https://example.org/",
                                    title="A page", http_status=200))
    run = Run("run-test", jsonl_path=tmp_path / "run.jsonl")

    run.started(grant_url="https://example.org/call")
    run.stage_started("ingest")
    run.tool_started("ingest_grant", "https://example.org/call")
    run.evidence_added(evidence)
    run.tool_finished("ingest_grant", 1200, "1 page", [evidence.id])
    run.stage_finished("ingest", 1300)
    run.identity_resolved("A1", "Someone", "Somewhere", margin=12.5)
    run.warning("profile_unreachable", "HTTP 404")
    run.failed("boom", "for the test")
    run.finished()

    assert {e.type for e in run.events} == EVENT_TYPES
    assert len(run.events) == 10


def test_evidence_added_carries_the_four_fields_the_chip_needs(tmp_path) -> None:
    store = EvidenceStore()
    evidence = store.get(store.mint(source_type="paper", url="https://openalex.org/W1",
                                    title="A real paper", derived_from=store.mint(
                                        source_type="api_query", url="https://api/x",
                                        title="q", http_status=200)))
    run = Run("run-test")

    event = run.evidence_added(evidence)

    assert event.model_dump(exclude={"seq", "ts", "type"}) == {
        "id": evidence.id, "source_type": "paper",
        "title": "A real paper", "url": "https://openalex.org/W1",
    }


# --- timing helpers ----------------------------------------------------------------------

def test_the_stage_helper_emits_a_matching_pair_with_real_elapsed_ms() -> None:
    run = Run("run-test")

    with run.stage("literature"):
        pass

    assert [e.type for e in run.events] == [STAGE_STARTED, STAGE_FINISHED]
    assert run.events[1].model_dump()["ms"] >= 0
    assert run.events[1].model_dump()["stage"] == "literature"


def test_a_raising_stage_still_closes_its_own_event() -> None:
    """A missing stage.finished leaves the UI spinning on a step that already died."""
    run = Run("run-test")

    with pytest.raises(RuntimeError), run.stage("literature"):
        raise RuntimeError("boom")

    assert [e.type for e in run.events] == [STAGE_STARTED, STAGE_FINISHED]


def test_the_tool_helper_collects_the_evidence_ids_minted_inside_it() -> None:
    run = Run("run-test")

    with run.tool("search_literature", "causal video question answering") as added:
        added.extend(["e4", "e5"])

    assert [e.type for e in run.events] == [TOOL_STARTED, TOOL_FINISHED]
    assert run.events[1].model_dump()["evidence_added"] == ["e4", "e5"]
    assert run.events[0].model_dump()["args_summary"] == "causal video question answering"


# --- wiring into what already exists ------------------------------------------------------

def test_run_warning_drops_straight_into_the_slots_the_other_modules_take(tmp_path) -> None:
    """Every module built before this one takes `warn: WarnFn = Callable[[str, str], None]`.
    If the signatures had drifted, WI-1.6d would be writing adapters instead of wiring."""
    run = Run("run-test", jsonl_path=tmp_path / "run.jsonl")
    store = EvidenceStore()
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404)))

    documents = ingest_profile("https://example.org/gone", store, warn=run.warning,
                               client=client, min_interval_s=0)

    assert documents.artefacts == []
    assert [e.model_dump()["code"] for e in run.warnings()] == ["fetch_failed"]


def test_warnings_are_filtered_out_of_the_full_log() -> None:
    run = Run("run-test")
    run.started()
    run.warning("thin_literature", "only 3 works")
    run.finished()

    assert [e.type for e in run.warnings()] == [WARNING]
    assert len(run.events) == 3


# --- the committed fixture ----------------------------------------------------------------

def test_the_committed_run_000_fixture_is_loadable_and_complete() -> None:
    """WI-2.3's replayer needs something to replay before a real run exists."""
    events = read_jsonl(pathlib.Path("fixtures/run-000.jsonl"))

    assert len(events) >= 10
    assert {e.type for e in events} == EVENT_TYPES - {"run.failed"}
    assert [e.seq for e in events] == list(range(len(events)))
    assert events[0].type == RUN_STARTED and events[-1].type == RUN_FINISHED
    assert all(isinstance(e, Event) for e in events)


def test_an_unwritable_log_file_does_not_end_the_run(tmp_path, monkeypatch) -> None:
    """A full disk at event 47 must not kill a four-minute run. The in-memory list is what
    SSE and the snapshot actually read from."""
    run = Run("run-test", jsonl_path=tmp_path / "run.jsonl")
    run.emit(RUN_STARTED)

    def refuse(*args, **kwargs):
        raise OSError("No space left on device")

    monkeypatch.setattr(pathlib.Path, "open", refuse)
    run.warning("thin_literature", "still recorded in memory")
    run.finished()

    assert [e.type for e in run.events] == [RUN_STARTED, WARNING, RUN_FINISHED]
    assert len(run.warnings()) == 1

# --- the frontend's warning vocabulary ----------------------------------------------------

#: Codes defined in `roia/` that are *not* warnings: probe question codes, probe answer
#: values and one model setting. They are named the same way, so the walk below has to
#: exclude them explicitly rather than guess.
NOT_WARNING_CODES = frozenset({
    "all_calls", "all_schemes", "continue", "medium", "multiple_call_periods",
    "multiple_schemes", "no_eligibility_found", "thin_profile", "use_different_url",
    "upload_document",
})


def test_every_backend_warning_code_has_a_human_label() -> None:
    """A warning is only useful if it says something. Six of the fifteen reachable codes
    reached the user as raw snake_case — `llm_failed`, `author_unresolved`,
    `openalex_failed` among them, which are precisely the ones that appear on the day
    something goes wrong and the box is actually being read.

    Asserted here rather than in the frontend because the codes are defined here; a new
    `warn(SOMETHING_NEW, …)` should fail this until someone writes the sentence.
    """
    import re

    roia = pathlib.Path(__file__).resolve().parent.parent / "roia"
    event_types = {
        "run.started", "stage.started", "stage.finished", "tool.started", "tool.finished",
        "evidence.added", "identity.resolved", "warning", "run.finished", "run.failed",
    }
    codes = set()
    for module in roia.glob("*.py"):
        for _, value in re.findall(r'^([A-Z][A-Z0-9_]+) = "([a-z0-9_.]+)"',
                                   module.read_text(), re.M):
            if value not in event_types and value not in NOT_WARNING_CODES:
                codes.add(value)

    warnings_tsx = roia.parent.parent / "frontend" / "src" / "Warnings.tsx"
    if not warnings_tsx.is_file():  # pragma: no cover - the backend can be checked out alone
        pytest.skip("frontend/ is not present")
    labelled = set(re.findall(r"^  ([a-z0-9_]+):", warnings_tsx.read_text(), re.M))

    assert codes, "no codes found — this check would pass vacuously"
    missing = sorted(codes - labelled)
    assert not missing, (
        f"these warning codes would reach the user as raw snake_case: {missing}. "
        f"Add a sentence to HUMAN in frontend/src/Warnings.tsx."
    )
