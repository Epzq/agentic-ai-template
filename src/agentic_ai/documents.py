from __future__ import annotations

from pathlib import Path

_TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".rst"}


def load_document(path: str | Path) -> str:
    """Extract plain text from a local ``.pdf``, ``.docx``, ``.txt``, or ``.md`` file.

    Raises ``FileNotFoundError`` / ``ValueError`` for bad input, and ``RuntimeError``
    if the optional parser for that format isn't installed (``.[docs]`` extra).
    """
    p = Path(path).expanduser()
    if not p.is_file():
        raise FileNotFoundError(p)

    suffix = p.suffix.lower()
    if suffix in _TEXT_SUFFIXES:
        return p.read_text(encoding="utf-8", errors="replace").strip()

    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError('PDF support needs:  uv pip install -e ".[docs]"') from exc
        pages = (page.extract_text() or "" for page in PdfReader(str(p)).pages)
        return "\n\n".join(pages).strip()

    if suffix == ".docx":
        try:
            import docx  # python-docx
        except ImportError as exc:
            raise RuntimeError('DOCX support needs:  uv pip install -e ".[docs]"') from exc
        return "\n".join(para.text for para in docx.Document(str(p)).paragraphs).strip()

    raise ValueError(f"unsupported document type: {suffix or '(no extension)'}")
