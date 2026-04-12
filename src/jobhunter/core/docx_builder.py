"""Build resume and cover letter DOCX files using python-docx."""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt

log = logging.getLogger(__name__)


def _split_bold_lead(text: str) -> tuple[str, str]:
    """Split a bullet into (bold_lead, rest) for formatting.

    Tries several split strategies in order of quality:
    1. Colon-space (strongest signal)
    2. Period-space (for sentence-lead bullets)
    3. Strong prepositions (by, through, across, resulting in)
    4. Comma
    5. Weak prepositions (for, with, to)
    6. Fallback: first 5 words
    """
    # Strategy 1: colon-space
    if ": " in text:
        idx = text.index(": ")
        return text[: idx + 1], text[idx + 2 :]

    # Strategy 2: period-space (but not after abbreviations like "Inc." or numbers)
    period_match = re.search(r"(?<![A-Z])\. ", text)
    if period_match and period_match.start() > 10:
        idx = period_match.start()
        return text[: idx + 1], text[idx + 2 :]

    # Strategy 3: strong prepositions
    for prep in (" by ", " through ", " across ", " resulting in "):
        if prep in text:
            idx = text.index(prep)
            if idx > 15:
                return text[: idx + len(prep)].rstrip(), text[idx + len(prep) :]

    # Strategy 4: comma
    if ", " in text:
        idx = text.index(", ")
        if idx > 15:
            return text[: idx + 1], text[idx + 2 :]

    # Strategy 5: weak prepositions
    for prep in (" for ", " with ", " to "):
        if prep in text:
            idx = text.index(prep)
            if idx > 15:
                return text[: idx + len(prep)].rstrip(), text[idx + len(prep) :]

    # Fallback: first 5 words
    words = text.split()
    if len(words) > 5:
        lead = " ".join(words[:5])
        rest = " ".join(words[5:])
        return lead, rest

    return text, ""


def build_resume(
    sections: dict[str, list[str]],
    *,
    name: str = "",
    email: str = "",
    phone: str = "",
    location: str = "",
    output_path: str | Path,
) -> Path:
    """Build a resume DOCX from selected bullets organized by section.

    Parameters
    ----------
    sections : dict mapping section name -> list of bullet strings
    name, email, phone, location : header contact info
    output_path : where to save the DOCX

    Returns the output Path.
    """
    doc = Document()

    # Page margins
    for section in doc.sections:
        section.top_margin = Inches(0.5)
        section.bottom_margin = Inches(0.5)
        section.left_margin = Inches(0.75)
        section.right_margin = Inches(0.75)

    # Header: Name
    if name:
        heading = doc.add_paragraph()
        heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = heading.add_run(name.upper())
        run.bold = True
        run.font.size = Pt(16)
        run.font.name = "Calibri"

    # Header: Contact line
    contact_parts = [p for p in [email, phone, location] if p]
    if contact_parts:
        contact = doc.add_paragraph()
        contact.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = contact.add_run(" | ".join(contact_parts))
        run.font.size = Pt(10)
        run.font.name = "Calibri"

    # Sections with bullets
    for section_name, bullets in sections.items():
        if not bullets:
            continue

        # Section header
        header = doc.add_paragraph()
        run = header.add_run(section_name.upper())
        run.bold = True
        run.font.size = Pt(12)
        run.font.name = "Calibri"

        # Horizontal rule
        header.paragraph_format.space_after = Pt(2)

        # Bullets
        for bullet_text in bullets:
            p = doc.add_paragraph(style="List Bullet")
            bold_lead, rest = _split_bold_lead(bullet_text)

            if rest:
                run_bold = p.add_run(bold_lead + " ")
                run_bold.bold = True
                run_bold.font.size = Pt(11)
                run_bold.font.name = "Calibri"

                run_rest = p.add_run(rest)
                run_rest.font.size = Pt(11)
                run_rest.font.name = "Calibri"
            else:
                run = p.add_run(bold_lead)
                run.font.size = Pt(11)
                run.font.name = "Calibri"

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    log.info("Resume saved to %s", out)
    return out


def build_cover_letter(
    text: str,
    *,
    name: str = "",
    email: str = "",
    phone: str = "",
    location: str = "",
    output_path: str | Path,
) -> Path:
    """Build a cover letter DOCX from plain text.

    Returns the output Path.
    """
    doc = Document()

    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

    # Header: Name
    if name:
        heading = doc.add_paragraph()
        run = heading.add_run(name)
        run.bold = True
        run.font.size = Pt(14)
        run.font.name = "Calibri"

    # Contact line
    contact_parts = [p for p in [email, phone, location] if p]
    if contact_parts:
        contact = doc.add_paragraph()
        run = contact.add_run(" | ".join(contact_parts))
        run.font.size = Pt(10)
        run.font.name = "Calibri"

    # Date
    date_para = doc.add_paragraph()
    run = date_para.add_run(date.today().strftime("%B %d, %Y"))
    run.font.size = Pt(11)
    run.font.name = "Calibri"
    doc.add_paragraph()  # blank line

    # Body paragraphs
    for paragraph in text.split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        p = doc.add_paragraph()
        run = p.add_run(paragraph)
        run.font.size = Pt(11)
        run.font.name = "Calibri"

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    log.info("Cover letter saved to %s", out)
    return out
