"""WI-1.1 — settings load, override and stay independent of the developer's own .env."""

from __future__ import annotations

import pytest

from roia.config import Settings, get_settings


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """No ROIA_/vendor variables set, and the repo's real .env ignored."""
    for name in (
        "ROIA_GEMINI_API_KEY", "GEMINI_API_KEY",
        "ROIA_OPENALEX_API_KEY", "OPENALEX_API_KEY",
        "ROIA_OPENALEX_MAILTO", "OPENALEX_MAILTO",
        "ROIA_MODEL_FAST", "ROIA_MODEL_SMART", "ROIA_DEMO_PROFILE_URL", "ROIA_DEV",
    ):
        monkeypatch.delenv(name, raising=False)


def test_defaults_hold_the_wi_0_1_model_decision(clean_env: None) -> None:
    """Importing without any credentials must work, and must not silently change models."""
    s = Settings(_env_file=None)

    assert s.gemini_api_key == ""
    assert s.openalex_api_key == ""
    assert s.model_fast == "gemini-3.8-flash"      # LLM #1-#3
    assert s.model_smart == "gemini-3.1-pro-preview"  # LLM #4
    assert s.dev is False


def test_roia_prefix_overrides(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROIA_MODEL_SMART", "gemini-3.8-flash")
    monkeypatch.setenv("ROIA_DEMO_PROFILE_URL", "https://example.org/~someone")
    monkeypatch.setenv("ROIA_DEV", "true")

    s = Settings(_env_file=None)

    assert s.model_smart == "gemini-3.8-flash"
    assert s.demo_profile_url == "https://example.org/~someone"
    assert s.dev is True


def test_vendor_keys_are_read_unprefixed(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """.env.example documents GEMINI_API_KEY and OPENALEX_API_KEY without the prefix,
    because that is what the vendors call them and what people paste in."""
    monkeypatch.setenv("GEMINI_API_KEY", "g-unprefixed")
    monkeypatch.setenv("OPENALEX_API_KEY", "oa-unprefixed")
    monkeypatch.setenv("OPENALEX_MAILTO", "someone@example.org")

    s = Settings(_env_file=None)

    assert s.gemini_api_key == "g-unprefixed"
    assert s.openalex_api_key == "oa-unprefixed"
    assert s.openalex_mailto == "someone@example.org"


def test_prefixed_spelling_of_a_vendor_key_also_works(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ROIA_GEMINI_API_KEY", "g-prefixed")

    assert Settings(_env_file=None).gemini_api_key == "g-prefixed"


def test_get_settings_is_cached(clean_env: None) -> None:
    get_settings.cache_clear()
    assert get_settings() is get_settings()
    get_settings.cache_clear()
