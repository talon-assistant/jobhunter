"""Shared bullet extraction from resume text.

Two paths:
  - LLM extraction (structured, high quality) via extract_bullets_llm()
  - Heuristic text extraction (no LLM needed) via smart_extract_bullets()

Both return a list of dicts with keys: section, role, text, source, priority.
The GUI wizard and the Resume Library import both use these so behavior
stays consistent.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_EXTRACT_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "extract_bullets.txt"

_ACTION_VERBS = {
    "led", "managed", "built", "developed", "designed", "implemented",
    "created", "launched", "directed", "established", "delivered",
    "reduced", "increased", "improved", "achieved", "negotiated",
    "orchestrated", "spearheaded", "transformed", "streamlined",
    "automated", "architected", "deployed", "migrated", "consolidated",
    "mentored", "trained", "supervised", "coordinated", "executed",
    "analyzed", "optimized", "secured", "maintained", "administered",
    "oversaw", "pioneered", "introduced", "resolved", "eliminated",
    "drove", "owned", "scaled", "shipped", "authored", "produced",
}

_BULLET_PREFIXES = re.compile(
    r"^(?:"
    r"[-*•◦▪▸►➤→‣⁃]\s+"          # Common bullet chars
    r"|\d+[.)]\s+"                  # Numbered lists: 1. or 1)
    r"|[a-z][.)]\s+"               # Lettered lists: a. or a)
    r")"
)


def smart_extract_bullets(text: str, source: str) -> list[dict[str, str]]:
    """Extract bullet-like lines from resume text without an LLM.

    Handles markdown bullets, unicode bullets, numbered/lettered lists, and
    lines starting with common resume action verbs. Filters out headers,
    contact info, and short fragments.
    """
    bullets: list[dict[str, str]] = []

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or len(stripped) < 15:
            continue

        # Skip likely headers (all caps and short)
        if stripped.isupper() and len(stripped) < 60:
            continue
        # Skip contact info
        if "@" in stripped and len(stripped) < 80:
            continue
        if re.match(r"^\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}", stripped):
            continue
        # Skip short date lines
        if re.match(r"^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", stripped):
            if len(stripped) < 40:
                continue

        is_bullet = False
        clean_text = stripped

        m = _BULLET_PREFIXES.match(stripped)
        if m:
            is_bullet = True
            clean_text = stripped[m.end():].strip()

        if not is_bullet:
            first_word = stripped.split()[0].rstrip(",:;").lower()
            if first_word in _ACTION_VERBS:
                is_bullet = True
                clean_text = stripped

        if is_bullet and 15 <= len(clean_text) <= 500:
            bullets.append({
                "section": "experience",
                "role": "",
                "text": clean_text,
                "source": source,
                "priority": "normal",
            })

    return bullets


def extract_bullets_llm(llm, text: str, source: str) -> list[dict[str, str]]:
    """Extract structured bullets from resume text using an LLM.

    Raises the underlying LLMError (or other exception) on failure so callers
    can decide whether to fall back to smart_extract_bullets(). Never swallows.
    """
    extract_prompt = ""
    if _EXTRACT_PROMPT_PATH.exists():
        extract_prompt = _EXTRACT_PROMPT_PATH.read_text(encoding="utf-8")

    prompt = extract_prompt.replace("{{DOCUMENT}}", text[:8000])
    prompt = prompt.replace("{{FILENAME}}", source)

    result = llm.generate_json(
        prompt,
        {"type": "object", "properties": {"roles": {"type": "array"}}},
        system_prompt="You are a resume parser. Extract bullets exactly as written.",
    )

    roles = result.get("roles", []) if isinstance(result, dict) else []
    bullets: list[dict[str, str]] = []
    for role in roles:
        section = role.get("section", "experience")
        role_name = role.get("role", "")
        for bullet in role.get("bullets", []):
            bullet = (bullet or "").strip()
            if bullet and len(bullet) > 10:
                bullets.append({
                    "section": section,
                    "role": role_name,
                    "text": bullet,
                    "source": source,
                    "priority": "normal",
                })
    return bullets


def extract_bullets(llm, text: str, source: str) -> tuple[list[dict[str, str]], str]:
    """Extract bullets, preferring the LLM and falling back to heuristics.

    Returns (bullets, method) where method is "llm", "text", or "text (llm failed: ...)".
    Never raises — the fallback always produces a result (possibly empty).
    """
    if llm is not None:
        try:
            bullets = extract_bullets_llm(llm, text, source)
            if bullets:
                return bullets, "llm"
            # LLM succeeded but found nothing — try heuristics too
            return smart_extract_bullets(text, source), "text (llm found nothing)"
        except Exception as exc:  # noqa: BLE001 — surface reason to caller
            log.warning("LLM extraction failed for %s: %s", source, exc)
            reason = str(exc).splitlines()[0][:120] if str(exc) else type(exc).__name__
            return smart_extract_bullets(text, source), f"text (llm failed: {reason})"

    return smart_extract_bullets(text, source), "text"
