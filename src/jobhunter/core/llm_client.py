"""OpenAI-compatible HTTP client for local llama-server."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests

log = logging.getLogger(__name__)


class LLMError(Exception):
    """Raised when the LLM backend returns an error."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class LLMClient:
    """Stateless client that talks to an OpenAI-compatible ``/v1/chat/completions`` endpoint."""

    def __init__(
        self,
        endpoint: str = "http://localhost:8080/v1/chat/completions",
        health_endpoint: str = "http://localhost:8080/health",
        temperature: float = 0.3,
        max_tokens: int = 2048,
        timeout: int = 300,
    ) -> None:
        self.endpoint = endpoint
        self.health_endpoint = health_endpoint
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_healthy(self) -> bool:
        """Return True if the LLM server is responding."""
        try:
            r = requests.get(self.health_endpoint, timeout=5)
            if r.status_code == 200:
                data = r.json()
                return data.get("status") in ("ok", "no slot available")
            return False
        except (requests.ConnectionError, requests.Timeout, ValueError):
            return False

    def generate_text(
        self,
        prompt: str,
        system_prompt: str = "",
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate plain text (cover letters, narratives)."""
        messages = self._build_messages(prompt, system_prompt)
        return self._call(messages, temperature=temperature, max_tokens=max_tokens)

    def generate_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        system_prompt: str = "",
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict | list:
        """Generate structured JSON output with schema enforcement.

        Uses ``response_format`` for constrained generation when supported.
        Falls back to prompt-based JSON extraction if the server ignores it.
        """
        messages = self._build_messages(prompt, system_prompt)

        response_format = {
            "type": "json_object",
            "schema": schema,
        }

        raw = self._call(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )

        return self._parse_json(raw)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_messages(
        self, prompt: str, system_prompt: str
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _call(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "stream": False,
        }
        if response_format:
            payload["response_format"] = response_format

        prompt_preview = messages[-1]["content"][:200]
        log.debug("LLM request (%d msgs, ~%d chars): %s...", len(messages), sum(len(m["content"]) for m in messages), prompt_preview)

        try:
            r = requests.post(
                self.endpoint,
                json=payload,
                timeout=self.timeout,
            )
        except requests.ConnectionError as exc:
            raise LLMError("Cannot connect to LLM server. Is llama-server running?") from exc
        except requests.Timeout as exc:
            raise LLMError(f"LLM request timed out after {self.timeout}s") from exc

        if r.status_code != 200:
            raise LLMError(f"LLM server returned {r.status_code}: {r.text[:500]}", r.status_code)

        try:
            data = r.json()
        except ValueError as exc:
            raise LLMError(f"Invalid JSON in LLM response: {r.text[:500]}") from exc

        text = data["choices"][0]["message"]["content"]
        text = self._truncate_degeneration(text)
        log.debug("LLM response (%d chars): %s...", len(text), text[:200])
        return text

    def _parse_json(self, raw: str) -> dict | list:
        """Extract JSON from raw LLM output, handling markdown fences."""
        text = raw.strip()

        # Strip markdown code fences
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()

        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting first JSON object or array
        for pattern in (r"\{[\s\S]*\}", r"\[[\s\S]*\]"):
            m = re.search(pattern, text)
            if m:
                try:
                    return json.loads(m.group())
                except json.JSONDecodeError:
                    continue

        # Last resort: attempt common repairs
        repaired = self._repair_json(text)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Failed to parse JSON from LLM output:\n{raw[:500]}") from exc

    @staticmethod
    def _repair_json(text: str) -> str:
        """Attempt common JSON repairs (trailing commas, missing brackets)."""
        # Remove trailing commas before } or ]
        text = re.sub(r",\s*([}\]])", r"\1", text)
        # Balance brackets
        opens = text.count("{") - text.count("}")
        if opens > 0:
            text += "}" * opens
        opens = text.count("[") - text.count("]")
        if opens > 0:
            text += "]" * opens
        return text

    @staticmethod
    def _truncate_degeneration(
        text: str,
        *,
        ngram_size: int = 5,
        repeat_threshold: int = 3,
    ) -> str:
        """Detect and truncate degenerate (repetitive) output."""
        words = text.split()
        if len(words) < ngram_size * repeat_threshold:
            return text

        # N-gram repetition detection
        ngrams: dict[str, list[int]] = {}
        for i in range(len(words) - ngram_size + 1):
            gram = " ".join(words[i : i + ngram_size]).lower()
            ngrams.setdefault(gram, []).append(i)

        for gram, positions in ngrams.items():
            if len(positions) >= repeat_threshold:
                cut = positions[1]  # truncate at second occurrence
                truncated = " ".join(words[:cut]).rstrip(".,;:!? ")
                log.warning("Degeneration detected at word %d, truncating", cut)
                return truncated

        # Run-on sentence detection
        sentences = re.split(r"[.!?]+", text)
        for sent in sentences:
            if len(sent.split()) > 60:
                idx = text.index(sent)
                truncated = text[: idx + 60 * 6].rstrip()  # rough char estimate
                log.warning("Run-on sentence detected, truncating")
                return truncated

        return text
