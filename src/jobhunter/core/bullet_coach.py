"""AI bullet coach: draft, critique, and improve resume bullets.

Design principle: the AI never invents facts. Numbers, scope, and outcomes
come from the user. Drafts mark unknowns with [bracketed placeholders] and
ask the user targeted questions instead of guessing — the same
fabrication-proof stance as the rest of the app.

Two layers:
  - check_bullet(): instant rule-based feedback, no LLM, safe to run on
    every keystroke
  - draft_bullets() / improve_bullet(): LLM-assisted, structured JSON out
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from jobhunter.core.llm_client import LLMClient, LLMError

log = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).parent.parent / "prompts"
_DRAFT_PROMPT_PATH = _PROMPT_DIR / "bullet_draft.txt"
_VARIANTS_PROMPT_PATH = _PROMPT_DIR / "bullet_variants.txt"


# ──────────────────────────────────────────────────────────────────────
# Rule-based feedback (no LLM)
# ──────────────────────────────────────────────────────────────────────

@dataclass
class BulletCheck:
    """One piece of feedback about a bullet."""

    ok: bool
    kind: str      # verb | metric | length | pronoun | buzzword | placeholder
    message: str


# Openers that describe duties instead of achievements
_WEAK_OPENERS = (
    "responsible for", "worked on", "worked with", "helped with", "helped to",
    "assisted with", "assisted in", "participated in", "involved in",
    "tasked with", "duties included", "in charge of", "was part of",
)

# A non-exhaustive set of strong openers; used to praise, never to punish —
# an opener that isn't listed just skips the praise.
_ACTION_VERBS = frozenset({
    "led", "built", "created", "designed", "developed", "launched",
    "delivered", "implemented", "architected", "automated", "reduced",
    "increased", "improved", "cut", "grew", "saved", "drove", "owned",
    "directed", "established", "founded", "transformed", "modernized",
    "migrated", "consolidated", "negotiated", "secured", "streamlined",
    "orchestrated", "spearheaded", "scaled", "shipped", "deployed",
    "mentored", "coached", "trained", "hired", "managed", "supervised",
    "analyzed", "optimized", "resolved", "eliminated", "prevented",
    "detected", "recovered", "audited", "authored", "presented", "won",
})

_BUZZWORDS = (
    "results-driven", "self-starter", "team player", "go-getter",
    "think outside the box", "outside the box", "synergy", "synergies",
    "dynamic individual", "hard worker", "detail-oriented", "guru",
    "ninja", "rockstar", "passionate about", "proven track record",
)

_METRIC_RE = re.compile(r"\d|%|\$")
_PLACEHOLDER_RE = re.compile(r"\[[^\]]{1,60}\]")
_FIRST_PERSON_RE = re.compile(r"\b(i|my|me|we|our|us)\b", re.IGNORECASE)


def check_bullet(text: str) -> list[BulletCheck]:
    """Instant, rule-based feedback on one bullet. Cheap enough for live use."""
    checks: list[BulletCheck] = []
    stripped = text.strip().rstrip(".")
    if not stripped:
        return checks

    lower = stripped.lower()
    words = stripped.split()

    # Opener quality
    weak = next((w for w in _WEAK_OPENERS if lower.startswith(w)), None)
    if weak:
        checks.append(BulletCheck(
            False, "verb",
            f'Starts with "{weak}" — swap in what you actually did '
            f'(Led, Built, Reduced...).',
        ))
    elif words and words[0].lower().rstrip(",") in _ACTION_VERBS:
        checks.append(BulletCheck(True, "verb", "Strong action verb ✓"))

    # Unresolved placeholders from AI drafting
    placeholders = _PLACEHOLDER_RE.findall(stripped)
    if placeholders:
        checks.append(BulletCheck(
            False, "placeholder",
            f"Fill in {', '.join(placeholders[:3])} with your real numbers "
            "before using this bullet.",
        ))
    elif _METRIC_RE.search(stripped):
        checks.append(BulletCheck(True, "metric", "Has a concrete number ✓"))
    else:
        checks.append(BulletCheck(
            False, "metric",
            "No number yet. Team size, %, $, time saved — even a rough "
            "one makes this land harder.",
        ))

    # First person
    if _FIRST_PERSON_RE.search(stripped):
        checks.append(BulletCheck(
            False, "pronoun",
            'Drop first-person words ("I", "we", "my") — resume bullets '
            "are written without them.",
        ))

    # Length
    if len(words) > 32:
        checks.append(BulletCheck(
            False, "length",
            f"{len(words)} words — trim toward one punchy sentence "
            "(under ~28 words).",
        ))
    elif len(words) < 5:
        checks.append(BulletCheck(
            False, "length",
            "Very short — add what changed because of your work.",
        ))

    # Buzzwords
    buzz = [b for b in _BUZZWORDS if b in lower]
    if buzz:
        checks.append(BulletCheck(
            False, "buzzword",
            f'"{buzz[0]}" is recruiter static — replace it with something '
            "specific you did.",
        ))

    return checks


def bullet_issues(text: str) -> list[BulletCheck]:
    """Just the problems from check_bullet()."""
    return [c for c in check_bullet(text) if not c.ok]


# ──────────────────────────────────────────────────────────────────────
# LLM-assisted drafting and improvement
# ──────────────────────────────────────────────────────────────────────

_DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "bullets": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "questions": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["text"],
            },
        },
    },
    "required": ["bullets"],
}

_VARIANTS_SCHEMA = {
    "type": "object",
    "properties": {
        "variants": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "style": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["style", "text"],
            },
        },
        "questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["variants"],
}


def _load_prompt(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    raise LLMError(f"Prompt template missing: {path.name}")


def draft_bullets(
    llm: LLMClient,
    description: str,
    *,
    role: str = "",
    section: str = "experience",
) -> list[dict]:
    """Turn a plain-language description of work into draft bullets.

    Returns a list of {"text": str, "questions": [str]}. Numbers the user
    didn't state appear as [bracketed placeholders], each with a matching
    question, so nothing is fabricated.
    """
    prompt = _load_prompt(_DRAFT_PROMPT_PATH)
    prompt = prompt.replace("{{DESCRIPTION}}", description.strip()[:4000])
    prompt = prompt.replace("{{ROLE}}", role.strip())
    prompt = prompt.replace("{{SECTION}}", section.strip())

    result = llm.generate_json(
        prompt, _DRAFT_SCHEMA,
        system_prompt=(
            "You are a resume coach. You never invent numbers, names, or "
            "outcomes the user did not state — you use [placeholders] and "
            "ask instead."
        ),
    )

    raw = result.get("bullets", []) if isinstance(result, dict) else []
    drafts: list[dict] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("text", "")).strip()
        if not text:
            continue
        questions = [str(q).strip() for q in entry.get("questions", []) if str(q).strip()]
        drafts.append({"text": text, "questions": questions})
    return drafts


def improve_bullet(
    llm: LLMClient,
    bullet: str,
    *,
    role: str = "",
) -> dict:
    """Rewrite one bullet in three styles (impact / concise / leadership).

    Returns {"variants": [{"style", "text"}], "questions": [str]}.
    """
    prompt = _load_prompt(_VARIANTS_PROMPT_PATH)
    prompt = prompt.replace("{{BULLET}}", bullet.strip()[:600])
    prompt = prompt.replace("{{ROLE}}", role.strip())

    result = llm.generate_json(
        prompt, _VARIANTS_SCHEMA,
        system_prompt=(
            "You are a resume coach. You never invent numbers, names, or "
            "outcomes not present in the original bullet — you use "
            "[placeholders] and ask instead."
        ),
    )

    if not isinstance(result, dict):
        return {"variants": [], "questions": []}

    variants = []
    for entry in result.get("variants", []):
        if isinstance(entry, dict) and str(entry.get("text", "")).strip():
            variants.append({
                "style": str(entry.get("style", "variant")).strip() or "variant",
                "text": str(entry["text"]).strip(),
            })
    questions = [str(q).strip() for q in result.get("questions", []) if str(q).strip()]
    return {"variants": variants, "questions": questions}
