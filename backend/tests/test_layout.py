"""WI-1.1 — the module layout exists and every module imports.

Cheap, but it catches the two failures that cost the most: a module named in
``execution-plan.md`` that nobody created, and a syntax error committed mid-item that
only shows up when the next work item tries to import it.
"""

from __future__ import annotations

import importlib

import pytest

# Exactly the layout in WI-1.1's checklist.
MODULES = [
    "config", "evidence", "events", "ingest", "openalex",
    "llm", "llm_schemas", "pipeline", "ranking", "report",
]


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name: str) -> None:
    assert importlib.import_module(f"roia.{name}").__doc__, (
        f"roia/{name}.py must say which work item owns it"
    )

