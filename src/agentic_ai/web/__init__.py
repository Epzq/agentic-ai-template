"""The browser front end: a FastAPI app wrapping the grant-fit analyst.

Needs the optional extra:  pip install -e ".[web]"
"""

from .app import MAX_UPLOAD_BYTES, SUPPORTED_SUFFIXES, create_app

__all__ = ["MAX_UPLOAD_BYTES", "SUPPORTED_SUFFIXES", "create_app"]
