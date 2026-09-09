"""The browser front end: a FastAPI app wrapping the grant-fit analyst.

Needs the optional extra:  pip install -e ".[web]"
"""

from .app import create_app

__all__ = ["create_app"]
