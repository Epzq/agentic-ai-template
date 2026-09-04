from __future__ import annotations

import pytest

from agentic_ai.config import Settings


@pytest.fixture
def settings(tmp_path):
    """Settings pointed at an isolated temp workdir so filesystem tools are sandboxed."""
    return Settings(workdir=str(tmp_path), model="claude-sonnet-5")
