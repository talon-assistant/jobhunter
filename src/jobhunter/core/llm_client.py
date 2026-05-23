"""Multi-provider LLM client.

Supported providers:
  - claude-cli:  Calls ``claude -p`` subprocess (no API key needed)
  - anthropic:   Anthropic SDK (requires API key)
  - openai:      OpenAI SDK (requires API key)
  - gemini:      Google Generative AI SDK (requires API key)
  - openai-compatible:  Any OpenAI-compatible endpoint (local llama-server, etc.)

All providers expose the same interface: generate_text() and generate_json().
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from typing import Any

log = logging.getLogger(__name__)


class LLMError(Exception):
    """Raised when the LLM backend returns an error."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class LLMClient:
    """Multi-provider LLM client with a unified interface."""

    PROVIDERS = ("claude-cli", "anthropic", "openai", "gemini", "openai-compatible")

    def __init__(
        self,
        provider: str = "claude-cli",
        *,
        api_key: str = "",
        model: str = "",
        endpoint: str = "",
        temperature: float = 0.3,
        max_tokens: int = 4096,
        timeout: int = 300,
    ) -> None:
        if provider not in self.PROVIDERS:
            raise ValueError(f"Unknown provider: {provider}. Choose from: {self.PROVIDERS}")

        self.provider = provider
        self.api_key = api_key
        self.model = model or self._default_model(provider)
        self.endpoint = endpoint
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    @staticmethod
    def _default_model(provider: str) -> str:
        return {
            "claude-cli": "",  # CLI uses its own default
            "anthropic": "claude-sonnet-4-20250514",
            "openai": "gpt-4o",
            "gemini": "gemini-2.5-flash",
            "openai-compatible": "",
        }.get(provider, "")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_healthy(self) -> bool:
        """Return True if the provider is reachable / configured."""
        try:
            if self.provider == "claude-cli":
                return shutil.which("claude") is not None
            elif self.provider == "anthropic":
                return bool(self.api_key)
            elif self.provider == "openai":
                return bool(self.api_key)
            elif self.provider == "gemini":
                return bool(self.api_key)
            elif self.provider == "openai-compatible":
                import requests
                r = requests.get(
                    self.endpoint.replace("/v1/chat/completions", "/health"),
                    timeout=5,
                )
                return r.status_code == 200
        except Exception:
            return False
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
        temp = temperature if temperature is not None else self.temperature
        tokens = max_tokens if max_tokens is not None else self.max_tokens

        if self.provider == "claude-cli":
            return self._call_claude_cli(prompt, system_prompt)
        elif self.provider == "anthropic":
            return self._call_anthropic(prompt, system_prompt, temp, tokens)
        elif self.provider == "openai":
            return self._call_openai(prompt, system_prompt, temp, tokens)
        elif self.provider == "gemini":
            return self._call_gemini(prompt, system_prompt, temp, tokens)
        elif self.provider == "openai-compatible":
            return self._call_openai_compat(prompt, system_prompt, temp, tokens)
        else:
            raise LLMError(f"Unknown provider: {self.provider}")

    def generate_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        system_prompt: str = "",
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict | list:
        """Generate structured JSON output.

        Appends JSON instructions to the prompt and parses the result.
        """
        json_instruction = (
            "\n\nIMPORTANT: Return ONLY valid JSON matching this schema. "
            "No markdown fences, no commentary, no text before or after the JSON.\n"
            f"Schema: {json.dumps(schema)}"
        )
        raw = self.generate_text(
            prompt + json_instruction,
            system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return self._parse_json(raw)

    @property
    def provider_display_name(self) -> str:
        return {
            "claude-cli": "Claude CLI",
            "anthropic": "Anthropic API",
            "openai": "OpenAI API",
            "gemini": "Google Gemini",
            "openai-compatible": "OpenAI-Compatible",
        }.get(self.provider, self.provider)

    # ------------------------------------------------------------------
    # Provider implementations
    # ------------------------------------------------------------------

    def _call_claude_cli(self, prompt: str, system_prompt: str) -> str:
        """Call ``claude -p`` subprocess."""
        claude_bin = shutil.which("claude")
        if not claude_bin:
            raise LLMError(
                "Claude CLI not found. Install Claude Code: "
                "https://docs.anthropic.com/en/docs/claude-code"
            )

        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        try:
            result = subprocess.run(
                [claude_bin, "-p", "--output-format", "text"],
                input=full_prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise LLMError(f"Claude CLI timed out after {self.timeout}s") from exc
        except FileNotFoundError as exc:
            raise LLMError("Claude CLI binary not found") from exc

        if result.returncode != 0:
            stderr = result.stderr[:500] if result.stderr else ""
            raise LLMError(f"Claude CLI failed (exit {result.returncode}): {stderr}")

        text = result.stdout.strip()
        if not text:
            raise LLMError("Claude CLI returned empty output")

        return self._truncate_degeneration(text)

    def _call_anthropic(
        self, prompt: str, system_prompt: str, temp: float, tokens: int
    ) -> str:
        """Call the Anthropic API via the SDK."""
        try:
            import anthropic
        except ImportError:
            raise LLMError("anthropic package not installed. Run: pip install anthropic")

        client = anthropic.Anthropic(api_key=self.api_key)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": tokens,
            "temperature": temp,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        try:
            response = client.messages.create(**kwargs)
        except anthropic.AuthenticationError as exc:
            raise LLMError("Invalid Anthropic API key") from exc
        except anthropic.APIError as exc:
            raise LLMError(f"Anthropic API error: {exc}") from exc

        text = response.content[0].text
        return self._truncate_degeneration(text)

    def _call_openai(
        self, prompt: str, system_prompt: str, temp: float, tokens: int
    ) -> str:
        """Call the OpenAI API via the SDK."""
        try:
            import openai
        except ImportError:
            raise LLMError("openai package not installed. Run: pip install openai")

        client = openai.OpenAI(api_key=self.api_key)
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temp,
                max_tokens=tokens,
            )
        except openai.AuthenticationError as exc:
            raise LLMError("Invalid OpenAI API key") from exc
        except openai.APIError as exc:
            raise LLMError(f"OpenAI API error: {exc}") from exc

        text = response.choices[0].message.content
        return self._truncate_degeneration(text)

    def _call_gemini(
        self, prompt: str, system_prompt: str, temp: float, tokens: int
    ) -> str:
        """Call the Google Gemini API."""
        try:
            import google.generativeai as genai
        except ImportError:
            raise LLMError(
                "google-generativeai package not installed. "
                "Run: pip install google-generativeai"
            )

        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(
            self.model,
            system_instruction=system_prompt if system_prompt else None,
        )

        try:
            response = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=temp,
                    max_output_tokens=tokens,
                ),
            )
        except Exception as exc:
            raise LLMError(f"Gemini API error: {exc}") from exc

        text = response.text
        return self._truncate_degeneration(text)

    def _call_openai_compat(
        self, prompt: str, system_prompt: str, temp: float, tokens: int
    ) -> str:
        """Call any OpenAI-compatible endpoint via HTTP."""
        import requests

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "messages": messages,
            "temperature": temp,
            "max_tokens": tokens,
            "stream": False,
        }
        if self.model:
            payload["model"] = self.model

        try:
            r = requests.post(
                self.endpoint,
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {},
                timeout=self.timeout,
            )
        except requests.ConnectionError as exc:
            raise LLMError(f"Cannot connect to {self.endpoint}") from exc
        except requests.Timeout as exc:
            raise LLMError(f"Request timed out after {self.timeout}s") from exc

        if r.status_code != 200:
            raise LLMError(f"Server returned {r.status_code}: {r.text[:500]}", r.status_code)

        try:
            data = r.json()
        except ValueError as exc:
            raise LLMError(f"Invalid JSON response: {r.text[:500]}") from exc

        text = data["choices"][0]["message"]["content"]
        return self._truncate_degeneration(text)

    # ------------------------------------------------------------------
    # Shared utilities
    # ------------------------------------------------------------------

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
        text = re.sub(r",\s*([}\]])", r"\1", text)
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

        ngrams: dict[str, list[int]] = {}
        for i in range(len(words) - ngram_size + 1):
            gram = " ".join(words[i : i + ngram_size]).lower()
            ngrams.setdefault(gram, []).append(i)

        for gram, positions in ngrams.items():
            if len(positions) >= repeat_threshold:
                cut = positions[1]
                truncated = " ".join(words[:cut]).rstrip(".,;:!? ")
                log.warning("Degeneration detected at word %d, truncating", cut)
                return truncated

        sentences = re.split(r"[.!?]+", text)
        for sent in sentences:
            if len(sent.split()) > 60:
                idx = text.index(sent)
                truncated = text[: idx + 60 * 6].rstrip()
                log.warning("Run-on sentence detected, truncating")
                return truncated

        return text
