from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables or a local ``.env`` file.

    Every field can be overridden with an ``AGENT_``-prefixed env var, e.g.
    ``AGENT_MODEL=claude-haiku-4-5`` or ``AGENT_TEMPERATURE=0.2``.
    """

    model_config = SettingsConfigDict(env_file=".env", env_prefix="AGENT_", extra="ignore")

    # Any identifier that ``langchain.chat_models.init_chat_model`` understands works here:
    #   claude-opus-5, claude-sonnet-5, claude-haiku-4-5   -> needs ANTHROPIC_API_KEY
    #   openai:gpt-4.1, groq:llama-3.3-70b-versatile, ollama:llama3.1   -> other providers
    model: str = "claude-opus-5"
    # Leave as None to let init_chat_model infer the provider from the model name.
    model_provider: str | None = None

    temperature: float = 0.0
    max_tokens: int = 4096

    # For locally hosted / self-hosted models. Leave unset for hosted APIs.
    #   Ollama on another machine:  AGENT_BASE_URL=http://192.168.1.10:11434
    #   OpenAI-compatible server (llama.cpp, vLLM, LM Studio):
    #     AGENT_MODEL=openai:<name>  AGENT_BASE_URL=http://localhost:8080/v1  AGENT_API_KEY=local
    base_url: str | None = None
    api_key: str | None = None

    system_prompt: str = (
        "You are a careful, resourceful assistant. "
        "Prefer using a tool over guessing. "
        "Explain your reasoning briefly, then give a direct answer."
    )

    # Filesystem tools are confined to this directory.
    workdir: str = "./workspace"

    # Base folder the analyst's save_report tool writes into (one subfolder per run).
    reports_dir: str = "./reports"
