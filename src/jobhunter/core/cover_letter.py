"""Cover letter generation via LLM."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from jobhunter.core.llm_client import LLMClient, LLMError

log = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "cover_letter.txt"

# Strings that indicate the LLM failed or leaked tool-call artifacts.
# Keep these narrow: a bare word like "permission" appears in legitimate
# letters (e.g. "permissions management" in security roles).
_BAD_MARKERS = [
    "webfetch",
    "permission denied",
    "requesting permission",
    "needs your permission",
    "tool call",
    "tool_call",
    "[your name]",
    "[your email]",
    "[company name]",
    "i cannot",
    "i can't",
    "as an ai",
]


class CoverLetterGenerator:
    """Generate tailored cover letters from resume + job description."""

    def __init__(
        self,
        llm_client: LLMClient,
        *,
        style_rules: str = "",
    ) -> None:
        self.llm = llm_client
        self.style_rules = style_rules
        self._prompt_template = ""
        if _PROMPT_PATH.exists():
            self._prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")

    def generate(
        self,
        *,
        resume_text: str,
        jd_text: str,
        company: str,
        position: str,
        location: str = "",
        fit_analysis: str = "",
        selected_bullets: str = "",
    ) -> str:
        """Generate a cover letter. Returns plain text.

        Raises LLMError if the LLM fails or produces invalid output.
        """
        prompt = self._prompt_template
        prompt = prompt.replace("{{RESUME}}", resume_text)
        prompt = prompt.replace("{{JD}}", jd_text[:6000])
        prompt = prompt.replace("{{COMPANY}}", company)
        prompt = prompt.replace("{{POSITION}}", position)
        prompt = prompt.replace("{{LOCATION}}", location)
        prompt = prompt.replace("{{FIT_ANALYSIS}}", fit_analysis)
        prompt = prompt.replace("{{SELECTED_BULLETS}}", selected_bullets)
        prompt = prompt.replace("{{STYLE_RULES}}", self.style_rules)

        system_prompt = (
            "You are a professional cover letter writer. Write ONLY the letter text, "
            "starting with 'Dear'. No preamble, no sign-off placeholders, no markdown formatting."
        )

        text = self.llm.generate_text(
            prompt, system_prompt=system_prompt, max_tokens=2048
        )

        # Strip markdown fences if present
        text = re.sub(r"^```(?:text)?\s*\n?", "", text.strip())
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()

        # Validate output
        self._validate(text)

        return text

    def _validate(self, text: str) -> None:
        """Check for hallucination markers or empty output."""
        if not text:
            raise LLMError("Cover letter generation produced empty output")

        lower = text.lower()
        for marker in _BAD_MARKERS:
            if marker in lower:
                raise LLMError(
                    f"Cover letter contains suspicious marker: '{marker}'. "
                    "The model may have failed to generate proper content."
                )

        if len(text) < 200:
            raise LLMError(
                f"Cover letter is suspiciously short ({len(text)} chars). "
                "Expected at least 200 characters for a proper letter."
            )
