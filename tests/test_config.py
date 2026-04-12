"""Tests for config.py."""

import json

from jobhunter.config import Config, _deep_merge


def test_deep_merge_adds_new_keys():
    base = {"a": 1, "b": {"c": 2}}
    override = {"b": {"d": 3}, "e": 4}
    merged = _deep_merge(base, override)
    assert merged == {"a": 1, "b": {"c": 2, "d": 3}, "e": 4}


def test_deep_merge_preserves_existing():
    base = {"a": 1, "b": {"c": 2}}
    override = {"a": 99, "b": {"c": 99}}
    merged = _deep_merge(base, override)
    # Existing values should be preserved
    assert merged["a"] == 1
    assert merged["b"]["c"] == 2


def test_config_get_dotpath(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "llm": {"endpoint": "http://localhost:8080", "temperature": 0.5},
        "resume": {"name": "Test"},
    }))

    cfg = Config(cfg_path)
    assert cfg.get("llm.endpoint") == "http://localhost:8080"
    assert cfg.get("llm.temperature") == 0.5
    assert cfg.get("resume.name") == "Test"
    assert cfg.get("nonexistent.key", "default") == "default"


def test_config_set_and_save(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"llm": {"temperature": 0.5}}))

    cfg = Config(cfg_path)
    cfg.set("llm.temperature", 0.9)
    cfg.set("new.key", "value")
    cfg.save()

    # Reload and verify
    cfg2 = Config(cfg_path)
    assert cfg2.get("llm.temperature") == 0.9
    assert cfg2.get("new.key") == "value"
