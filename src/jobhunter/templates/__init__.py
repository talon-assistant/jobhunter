"""Built-in ATS-friendly resume templates."""

from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent

TEMPLATES = {
    "classic": {
        "file": "classic.docx",
        "name": "Classic",
        "description": "Clean, conservative Calibri design. Ideal for corporate and traditional roles.",
        "font": "Calibri",
    },
    "modern": {
        "file": "modern.docx",
        "name": "Modern",
        "description": "Bold accent-color headers with Calibri. Good for tech and progressive companies.",
        "font": "Calibri",
    },
    "executive": {
        "file": "executive.docx",
        "name": "Executive",
        "description": "Garamond with generous margins. Understated elegance for director+ roles.",
        "font": "Garamond",
    },
    "compact": {
        "file": "compact.docx",
        "name": "Compact",
        "description": "Arial with tight spacing. Fits more content for technical roles with many bullets.",
        "font": "Arial",
    },
}


def get_template_path(template_key: str) -> Path:
    """Get the full path to a template DOCX file."""
    if template_key not in TEMPLATES:
        raise ValueError(f"Unknown template: {template_key}. Choose from: {list(TEMPLATES.keys())}")
    return TEMPLATE_DIR / TEMPLATES[template_key]["file"]


def list_templates() -> list[dict]:
    """Return list of available templates with metadata."""
    return [
        {"key": k, **v, "path": str(TEMPLATE_DIR / v["file"])}
        for k, v in TEMPLATES.items()
    ]
