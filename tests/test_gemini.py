from __future__ import annotations

import agentic_ai.gemini as gem


def test_profile_researcher_wraps_ask_gemini(monkeypatch):
    seen = {}

    def fake_ask(prompt, **kwargs):
        seen["prompt"] = prompt
        return "Prof X: graph ML for battery materials; NRF Fellow 2021; ~40 papers."

    monkeypatch.setattr(gem, "ask_gemini", fake_ask)
    out = gem.profile_researcher.invoke({"url": "https://example.edu/~x"})

    assert "battery materials" in out
    assert "https://example.edu/~x" in seen["prompt"]


def test_ask_gemini_without_key_returns_error_string(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    result = gem.ask_gemini("anything")

    assert result.startswith("gemini error:")


def test_ask_gemini_missing_package_returns_error_string(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setitem(__import__("sys").modules, "google.genai", None)

    result = gem.ask_gemini("anything")

    assert result.startswith("gemini error:")
