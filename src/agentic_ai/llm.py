from __future__ import annotations

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from .config import Settings


def build_model(settings: Settings | None = None) -> BaseChatModel:
    """Instantiate the chat model described by ``settings``.

    Uses LangChain's provider-agnostic ``init_chat_model`` so the same code path
    works for Anthropic, OpenAI, Groq, Ollama, and others. Swap providers by
    changing ``AGENT_MODEL`` (and installing that provider's integration package).
    """
    settings = settings or Settings()
    kwargs: dict = {
        "temperature": settings.temperature,
        "max_tokens": settings.max_tokens,
    }
    # Only forwarded when set, so hosted providers keep their own defaults.
    if settings.base_url:
        kwargs["base_url"] = settings.base_url
    if settings.api_key:
        kwargs["api_key"] = settings.api_key
    return init_chat_model(settings.model, model_provider=settings.model_provider, **kwargs)