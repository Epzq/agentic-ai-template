"""Runtime configuration, read from environment variables or a local ``.env`` file.

Ported from ``reference/config_pattern.py`` (``demo-spec.md`` §5, "Reuse"), with the
prefix changed to ``ROIA_`` and our own fields.

Two naming conventions live here on purpose. Our own settings take the ``ROIA_``
prefix; the three vendor credentials keep the names their vendors use, because that
is what ``.env.example`` documents and what people paste in. Both spellings are
accepted for the vendor keys, so ``ROIA_GEMINI_API_KEY`` works too.

Nothing here is required. Every field defaults to something importable, so a missing
key surfaces where it is used, not at import time — a test suite that cannot even
import the package without credentials is a test suite that stops being run.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from roia.paths import ENV_FILE


class Settings(BaseSettings):
    """Every field is overridable with a ``ROIA_``-prefixed env var, e.g.
    ``ROIA_MODEL_FAST=gemini-3.8-flash``."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_prefix="ROIA_",
        extra="ignore",
    )

    # --- credentials -------------------------------------------------------
    # Paid tier: gemini-3.1-pro-preview has no free tier (WI-0.1).
    gemini_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("ROIA_GEMINI_API_KEY", "GEMINI_API_KEY"),
    )
    # Required, not optional: anonymous OpenAlex is ~100 list calls per DAY,
    # which a single run exhausts (WI-0.1).
    openalex_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("ROIA_OPENALEX_API_KEY", "OPENALEX_API_KEY"),
    )
    openalex_mailto: str = Field(
        default="",
        validation_alias=AliasChoices("ROIA_OPENALEX_MAILTO", "OPENALEX_MAILTO"),
    )

    # --- models (WI-0.1 decision, verified live) ---------------------------
    # Flash for LLM #1-#3 (~2.0 s); Pro for LLM #4 (~10.5 s), which is the one
    # call doing cross-direction scoring and worth the latency.
    model_fast: str = "gemini-3.8-flash"
    model_smart: str = "gemini-3.1-pro-preview"

    # --- the frozen demo pair (WI-0.0) -------------------------------------
    demo_profile_url: str = ""

    # --- dev toggles -------------------------------------------------------
    # Gates CORS for the Vite dev server on :5173 (WI-2.1).
    dev: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide settings, read once.

    Cached rather than module-level so importing ``roia.config`` never touches the
    environment, and so a test can clear the cache to swap the environment out.
    """
    return Settings()
