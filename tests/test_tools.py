from __future__ import annotations

import datetime as dt

import pytest

from agentic_ai.tools import _safe_path, add, default_tools, multiply, now


def test_add_and_multiply():
    assert add.invoke({"a": 2, "b": 3}) == 5
    assert multiply.invoke({"a": 4, "b": 2.5}) == 10.0


def test_now_is_iso_utc():
    parsed = dt.datetime.fromisoformat(now.invoke({}))
    assert parsed.tzinfo is not None


def test_safe_path_allows_inside(tmp_path):
    target = _safe_path(str(tmp_path), "notes/todo.txt")
    assert str(target).startswith(str(tmp_path.resolve()))


def test_safe_path_blocks_escape(tmp_path):
    with pytest.raises(ValueError):
        _safe_path(str(tmp_path), "../../etc/passwd")


def test_read_text_file_tool(settings, tmp_path):
    (tmp_path / "hello.txt").write_text("hi there", encoding="utf-8")
    tools = {t.name: t for t in default_tools(settings)}
    assert tools["read_text_file"].invoke({"path": "hello.txt"}) == "hi there"


@pytest.mark.network
def test_search_wikipedia_live():
    from agentic_ai.tools import search_wikipedia

    assert "Python" in search_wikipedia.invoke({"query": "Python programming language"})