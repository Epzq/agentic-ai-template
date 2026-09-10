"""WI-1.2 — minting, ID resolution, and AC4's provenance rules."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from roia.evidence import SUMMARY_MAX_CHARS, Evidence, EvidenceStore


def test_mint_returns_short_sequential_ids() -> None:
    """e1, e2, ... — models copy short tokens far more reliably than hashes."""
    store = EvidenceStore()

    first = store.mint(
        source_type="webpage", url="https://example.org/", title="A", http_status=200
    )
    second = store.mint(
        source_type="webpage", url="https://example.org/b", title="B", http_status=200
    )

    assert (first, second) == ("e1", "e2")
    assert len(store) == 2
    assert store.get("e1") is not None and store.get("e1").title == "A"
    assert store.get("e404") is None
    assert isinstance(store.get("e1").retrieved_at, datetime)


def test_mint_refuses_a_caller_supplied_id() -> None:
    with pytest.raises(ValueError, match="mint\\(\\) assigns the id"):
        EvidenceStore().mint(
            id="e99", source_type="api_query", title="x", url="https://a", http_status=200
        )


def test_resolve_ids_splits_and_dedupes_preserving_order() -> None:
    store = EvidenceStore()
    store.mint(source_type="api_query", url="https://api/1", title="q", http_status=200)
    store.mint(source_type="api_query", url="https://api/2", title="q", http_status=200)

    kept, dropped = store.resolve_ids(["e2", "e999", "e1", "e2", "e999"])

    assert kept == ["e2", "e1"]
    assert dropped == ["e999"]


@pytest.mark.parametrize(
    ("kind", "fields", "missing"),
    [
        ("grant_doc", {"sha256": "a" * 64}, "page"),
        ("grant_doc", {"page": 3}, "sha256"),
        ("webpage", {"url": "https://example.org/", "http_status": 404}, "http_status==200"),
        ("webpage", {"http_status": 200}, "url"),
        ("api_query", {"url": "https://api.openalex.org/works"}, "http_status"),
        ("paper", {"url": "https://openalex.org/W1"}, "derived_from"),
    ],
)
def test_ac4_provenance_is_enforced_per_source_type(
    kind: str, fields: dict[str, object], missing: str
) -> None:
    """A row whose provenance cannot be checked must never reach the report."""
    with pytest.raises(ValidationError, match=missing):
        Evidence(id="e1", source_type=kind, title="t", retrieved_at=datetime.now(UTC), **fields)


def test_ac4_a_paper_must_derive_from_a_two_hundred_api_query() -> None:
    store = EvidenceStore()
    search = store.mint(
        source_type="api_query", url="https://api/works?q=x", title="search", http_status=200
    )
    failed = store.mint(
        source_type="api_query", url="https://api/works?q=y", title="search", http_status=429
    )
    page = store.mint(source_type="grant_doc", page=1, sha256="b" * 64, title="call sheet")

    paper = store.mint(
        source_type="paper", url="https://openalex.org/W1", title="Real paper", derived_from=search
    )
    assert store.get(paper).derived_from == search

    with pytest.raises(ValueError, match="requires an api_query with a logged 200"):
        store.mint(
            source_type="paper", url="https://openalex.org/W2", title="p", derived_from=failed
        )
    with pytest.raises(ValueError, match="requires an api_query with a logged 200"):
        store.mint(source_type="paper", url="https://openalex.org/W3", title="p", derived_from=page)
    with pytest.raises(ValueError, match="not in the store"):
        store.mint(
            source_type="paper", url="https://openalex.org/W4", title="p", derived_from="e999"
        )


def test_summary_is_truncated_rather_than_rejected() -> None:
    """An OpenAlex abstract is routinely 1,200+ chars; a run must not die over one."""
    store = EvidenceStore()
    long_abstract = "word " * 500

    row = store.get(
        store.mint(
            source_type="api_query",
            url="https://api/works",
            title="q",
            http_status=200,
            summary=long_abstract,
        )
    )

    assert len(row.summary) <= SUMMARY_MAX_CHARS
    assert row.summary.endswith("…")
    assert row.summary.startswith("word word")
