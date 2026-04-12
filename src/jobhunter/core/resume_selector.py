"""Index-based resume bullet selection via LLM.

The selector NEVER generates content -- it only picks indices from the
existing bullet library.  This is the fabrication-proof design.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jobhunter.core.llm_client import LLMClient, LLMError
from jobhunter.core.resume_db import ResumeDB

log = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "bullet_select.txt"

# Fallback cap when a section has no user-configured cap
DEFAULT_CAP_PER_SECTION = 4


@dataclass
class Selection:
    """Result of the bullet selection process."""

    picks: dict[str, list[int]]  # section -> [bullet_id, ...]
    rationale: str = ""
    raw: str = ""


class ResumeSelector:
    """Select the best resume bullets for a job description."""

    def __init__(
        self,
        llm_client: LLMClient,
        resume_db: ResumeDB,
    ) -> None:
        self.llm = llm_client
        self.db = resume_db
        self._prompt_template = ""
        if _PROMPT_PATH.exists():
            self._prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")

    @property
    def caps(self) -> dict[str, int]:
        """Pull caps dynamically from the resume DB (user-configured per section)."""
        return self.db.get_all_caps(default=DEFAULT_CAP_PER_SECTION)

    def select(self, jd_text: str, *, company: str = "", position: str = "") -> Selection:
        """Pick the best bullets for a job description.

        Returns a Selection with picks keyed by section name,
        each containing a list of bullet_ids.
        """
        # Build the library payload
        library = self._build_library_payload()
        if not library["sections"]:
            log.warning("Resume library is empty; cannot select bullets")
            return Selection(picks={})

        # Build prompt
        prompt = self._prompt_template
        prompt = prompt.replace("{{LIBRARY}}", json.dumps(library, indent=2))
        prompt = prompt.replace("{{JOB_DESCRIPTION}}", jd_text[:3000])
        prompt = prompt.replace("{{COMPANY}}", company)
        prompt = prompt.replace("{{POSITION}}", position)
        prompt = prompt.replace("{{CAPS}}", json.dumps(self.caps))

        schema = {
            "type": "object",
            "properties": {
                "picks": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                },
                "rationale": {"type": "string"},
            },
            "required": ["picks", "rationale"],
        }

        system_prompt = (
            "You are tailoring a resume by SELECTING pre-written bullets from a library. "
            "You do not write, rewrite, or paraphrase. You only pick which bullet IDs "
            "best fit the target job description. Return ONLY valid JSON."
        )

        try:
            result = self.llm.generate_json(prompt, schema, system_prompt=system_prompt)
        except LLMError:
            log.exception("Bullet selection failed")
            return Selection(picks={})

        raw_picks = result.get("picks", {}) if isinstance(result, dict) else {}
        rationale = result.get("rationale", "") if isinstance(result, dict) else ""

        # Validate picks: ensure IDs exist and respect caps
        validated = self._validate_picks(raw_picks)

        return Selection(
            picks=validated,
            rationale=rationale,
            raw=json.dumps(result),
        )

    def render_preview(self, selection: Selection) -> str:
        """Render selected bullets as a markdown preview."""
        lines: list[str] = []
        for section, bullet_ids in selection.picks.items():
            bullets = [self.db.get_bullet(bid) for bid in bullet_ids]
            bullets = [b for b in bullets if b]
            if not bullets:
                continue

            lines.append(f"## {section}")
            role = bullets[0].get("role", "")
            if role:
                lines.append(f"*{role}*")
            lines.append("")
            for b in bullets:
                lines.append(f"- {b['text']}")
            lines.append("")

        return "\n".join(lines)

    def render_selection_notes(
        self, selection: Selection, *, company: str = "", position: str = ""
    ) -> str:
        """Render a sidecar document explaining the selections."""
        lines = [
            f"# Selection Notes",
            f"**Target:** {company} - {position}",
            f"**Rationale:** {selection.rationale}",
            "",
        ]

        for section, bullet_ids in selection.picks.items():
            cap = self.caps.get(section, "?")
            lines.append(f"## {section} ({len(bullet_ids)}/{cap})")
            for bid in bullet_ids:
                b = self.db.get_bullet(bid)
                if b:
                    lines.append(f"- [#{bid}] {b['text'][:100]}...")
            lines.append("")

        return "\n".join(lines)

    def mark_selected(self, selection: Selection) -> None:
        """Increment usage counters for all selected bullets."""
        for bullet_ids in selection.picks.values():
            for bid in bullet_ids:
                self.db.increment_selected(bid)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_library_payload(self) -> dict[str, Any]:
        """Build a JSON-serializable library for the LLM prompt."""
        sections_data: list[dict[str, Any]] = []
        for section in self.db.get_sections():
            bullets = self.db.list_bullets(section=section)
            bullet_entries = [
                {"id": b["bullet_id"], "text": b["text"]}
                for b in bullets
            ]
            if bullet_entries:
                sections_data.append({
                    "section": section,
                    "cap": self.caps.get(section, 4),
                    "bullets": bullet_entries,
                })
        return {"sections": sections_data}

    def _validate_picks(self, raw_picks: dict[str, list[int]]) -> dict[str, list[int]]:
        """Ensure all picked IDs exist and respect section caps."""
        validated: dict[str, list[int]] = {}
        for section, ids in raw_picks.items():
            cap = self.caps.get(section, 4)
            valid_ids: list[int] = []
            seen: set[int] = set()

            for bid in ids:
                if bid in seen:
                    continue
                b = self.db.get_bullet(bid)
                if b and b["section"] == section:
                    valid_ids.append(bid)
                    seen.add(bid)
                    if len(valid_ids) >= cap:
                        break

            if valid_ids:
                validated[section] = valid_ids

        return validated
