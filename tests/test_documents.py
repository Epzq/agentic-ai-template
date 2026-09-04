from __future__ import annotations

import pytest

from agentic_ai.documents import load_document


def test_reads_markdown(tmp_path):
    f = tmp_path / "context.md"
    f.write_text("# Project\n\nWe study perovskite solar cells.", encoding="utf-8")
    assert "perovskite" in load_document(f)


def test_reads_plain_text(tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("  hello  ", encoding="utf-8")
    assert load_document(f) == "hello"


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_document(tmp_path / "nope.pdf")


def test_unknown_extension_raises(tmp_path):
    f = tmp_path / "data.bin"
    f.write_bytes(b"\x00\x01")
    with pytest.raises(ValueError):
        load_document(f)
