"""Built-in ATS-friendly resume templates.

Each template carries a ``style`` dict that docx_builder.build_resume()
uses to render generated resumes — font, sizes, accent color, margins,
alignment, and rules. The .docx files alongside are static previews of
the same styles.
"""

from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent

TEMPLATES = {
    "classic": {
        "file": "classic.docx",
        "name": "Classic",
        "description": "Clean, conservative Calibri design. Ideal for corporate and traditional roles.",
        "font": "Calibri",
        "style": {
            "font": "Calibri",
            "name_size": 18,
            "heading_size": 11,
            "body_size": 10.5,
            "accent": (0x1A, 0x1A, 0x2E),
            "center_header": True,
            "margins": (0.5, 0.5, 0.75, 0.75),
            "rules": True,
        },
    },
    "modern": {
        "file": "modern.docx",
        "name": "Modern",
        "description": "Bold accent-color headers with Calibri. Good for tech and progressive companies.",
        "font": "Calibri",
        "style": {
            "font": "Calibri",
            "name_size": 20,
            "heading_size": 12,
            "body_size": 10.5,
            "accent": (0x2B, 0x57, 0x9A),
            "center_header": False,
            "margins": (0.6, 0.6, 0.7, 0.7),
            "rules": True,
        },
    },
    "executive": {
        "file": "executive.docx",
        "name": "Executive",
        "description": "Garamond with generous margins. Understated elegance for director+ roles.",
        "font": "Garamond",
        "style": {
            "font": "Garamond",
            "name_size": 22,
            "heading_size": 12,
            "body_size": 11,
            "accent": (0x2C, 0x2C, 0x2C),
            "center_header": True,
            "margins": (0.75, 0.75, 1.0, 1.0),
            "rules": True,
        },
    },
    "compact": {
        "file": "compact.docx",
        "name": "Compact",
        "description": "Arial with tight spacing. Fits more content for technical roles with many bullets.",
        "font": "Arial",
        "style": {
            "font": "Arial",
            "name_size": 16,
            "heading_size": 10,
            "body_size": 9.5,
            "accent": (0x33, 0x33, 0x33),
            "center_header": False,
            "margins": (0.4, 0.4, 0.6, 0.6),
            "rules": True,
        },
    },
    "technical": {
        "file": "technical.docx",
        "name": "Technical",
        "description": "Skills-forward Calibri with a teal accent. Built for engineers and hands-on IC roles.",
        "font": "Calibri",
        "style": {
            "font": "Calibri",
            "name_size": 17,
            "heading_size": 11,
            "body_size": 10,
            "accent": (0x0F, 0x76, 0x6E),
            "center_header": False,
            "margins": (0.5, 0.5, 0.65, 0.65),
            "rules": True,
        },
    },
    "minimal": {
        "file": "minimal.docx",
        "name": "Minimal ATS",
        "description": "Zero decoration, maximum parseability. When you know a strict ATS is the first reader.",
        "font": "Arial",
        "style": {
            "font": "Arial",
            "name_size": 14,
            "heading_size": 11,
            "body_size": 10.5,
            "accent": (0x00, 0x00, 0x00),
            "center_header": False,
            "margins": (0.7, 0.7, 0.8, 0.8),
            "rules": False,
        },
    },
}


def get_template_path(template_key: str) -> Path:
    """Get the full path to a template DOCX file."""
    if template_key not in TEMPLATES:
        raise ValueError(f"Unknown template: {template_key}. Choose from: {list(TEMPLATES.keys())}")
    return TEMPLATE_DIR / TEMPLATES[template_key]["file"]


def get_template_style(template_key: str) -> dict:
    """Get the render style for a template, falling back to classic."""
    entry = TEMPLATES.get(template_key) or TEMPLATES["classic"]
    return entry["style"]


def list_templates() -> list[dict]:
    """Return list of available templates with metadata."""
    return [
        {"key": k, **v, "path": str(TEMPLATE_DIR / v["file"])}
        for k, v in TEMPLATES.items()
    ]
