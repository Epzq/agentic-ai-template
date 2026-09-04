"""agentic-ai-starter: a minimal, readable agent loop built on LangChain + LangGraph."""

from dotenv import load_dotenv

# Make .env available as real environment variables (for ANTHROPIC_API_KEY,
# GOOGLE_API_KEY, etc. - Settings reads .env itself, but SDKs read os.environ).
load_dotenv()

from .agent import build_agent  # noqa: E402
from .config import Settings  # noqa: E402

__all__ = ["Settings", "build_agent"]
__version__ = "0.1.0"
