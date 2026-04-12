"""Extract text content from PDF, DOCX, and TXT files."""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


def extract_text(file_path: str | Path) -> str:
    """Extract plain text from a document file.

    Supported formats: .pdf, .docx, .doc, .txt, .md
    Returns the extracted text or an empty string on failure.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    try:
        if suffix == ".pdf":
            return _extract_pdf(path)
        elif suffix in (".docx", ".doc"):
            return _extract_docx(path)
        elif suffix in (".txt", ".md", ".text"):
            return path.read_text(encoding="utf-8", errors="replace")
        else:
            log.warning("Unsupported file type: %s", suffix)
            return ""
    except Exception:
        log.exception("Failed to extract text from %s", path)
        return ""


def _extract_pdf(path: Path) -> str:
    """Extract text from a PDF using PyMuPDF."""
    import fitz  # PyMuPDF

    text_parts: list[str] = []
    with fitz.open(str(path)) as doc:
        for page in doc:
            text_parts.append(page.get_text())
    return "\n".join(text_parts).strip()


def _extract_docx(path: Path) -> str:
    """Extract text from a DOCX using python-docx."""
    from docx import Document

    doc = Document(str(path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs).strip()


def supported_extensions() -> list[str]:
    """Return list of supported file extensions."""
    return [".pdf", ".docx", ".doc", ".txt", ".md"]
