"""Configuration loading, validation, and persistence."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

_APP_DIR = Path.home() / ".jobhunter"
_CONFIG_PATH = _APP_DIR / "config.json"
_DEFAULT_CONFIG = Path(__file__).parent / "default_config.json"


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base*, returning a new dict.

    - New keys in *override* are added.
    - Existing scalar values in *base* are kept (user settings win).
    - Nested dicts are merged recursively.
    """
    merged = dict(base)
    for key, value in override.items():
        if key not in merged:
            merged[key] = value
        elif isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        # else: keep existing user value
    return merged


class Config:
    """Thin wrapper around a JSON config file with dot-path access."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else _CONFIG_PATH
        self._data: dict[str, Any] = {}
        self._ensure_exists()
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, dotpath: str, default: Any = None) -> Any:
        """Retrieve a value using ``section.key`` notation.

        >>> cfg.get("llm.endpoint", "http://localhost:8080")
        """
        keys = dotpath.split(".")
        node: Any = self._data
        for k in keys:
            if isinstance(node, dict) and k in node:
                node = node[k]
            else:
                return default
        return node

    def set(self, dotpath: str, value: Any) -> None:
        """Set a value using ``section.key`` notation and persist."""
        keys = dotpath.split(".")
        node = self._data
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = value

    def save(self) -> None:
        """Write current config back to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=4), encoding="utf-8")

    @property
    def data(self) -> dict[str, Any]:
        return self._data

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _ensure_exists(self) -> None:
        """Copy default config if user config is missing, or merge new keys."""
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(_DEFAULT_CONFIG, self.path)
            return

        # Merge any new keys from defaults into existing config
        with open(_DEFAULT_CONFIG, encoding="utf-8") as f:
            defaults = json.load(f)
        with open(self.path, encoding="utf-8") as f:
            user = json.load(f)

        merged = _deep_merge(user, defaults)
        if merged != user:
            self.path.write_text(json.dumps(merged, indent=4), encoding="utf-8")

    def _load(self) -> None:
        with open(self.path, encoding="utf-8") as f:
            self._data = json.load(f)

    def _resolve_path(self, raw: str) -> Path:
        """Resolve a path relative to the app directory."""
        p = Path(raw)
        if p.is_absolute():
            return p
        return _APP_DIR / p
