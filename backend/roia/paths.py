"""Where things are on disk, resolved from this file rather than from the CWD.

`FIXTURES_DIR = Path("fixtures")` worked only while the server happened to be started
from the project root. It silently pointed at nothing from anywhere else — an empty
fixture list and a 404 on the demo-day fallback, with no error to explain why. Anchoring
to `__file__` means `uvicorn`, `pytest` and `python -m roia` all agree no matter where
they were launched.
"""

from __future__ import annotations

from pathlib import Path

#: `backend/` — the directory holding `pyproject.toml`, `.env`, `fixtures/` and `runs/`.
BACKEND_DIR = Path(__file__).resolve().parent.parent

FIXTURES_DIR = BACKEND_DIR / "fixtures"
RUNS_DIR = BACKEND_DIR / "runs"
ENV_FILE = BACKEND_DIR / ".env"

#: `frontend/dist/` — the built SPA, a sibling of `backend/`. Absent until someone runs
#: `npm run build`, which is the normal state in development: the API must still boot.
FRONTEND_DIST = BACKEND_DIR.parent / "frontend" / "dist"
