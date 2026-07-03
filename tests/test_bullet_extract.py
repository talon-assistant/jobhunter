"""Tests for the shared bullet extraction module."""

from unittest.mock import MagicMock

from jobhunter.core.bullet_extract import (
    smart_extract_bullets,
    extract_bullets_llm,
    extract_bullets,
)

SAMPLE = (
    "JOHN SMITH\n"
    "john@example.com | 555-123-4567\n"
    "EXPERIENCE\n"
    "Led team of 12 engineers across 3 SOC locations\n"
    "Reduced security incidents by 45% through zero trust implementation\n"
    "Python\n"  # too short / not a bullet
)


def test_smart_extract_finds_action_verb_bullets():
    bullets = smart_extract_bullets(SAMPLE, "resume.pdf")
    texts = [b["text"] for b in bullets]
    assert any("Led team" in t for t in texts)
    assert any("Reduced security" in t for t in texts)
    assert not any("JOHN SMITH" in t for t in texts)
    assert not any("john@example" in t for t in texts)


def test_extract_bullets_uses_llm_when_it_works():
    llm = MagicMock()
    llm.generate_json.return_value = {
        "roles": [
            {"section": "experience", "role": "VP at Corp",
             "bullets": ["Did a great thing that mattered a lot"]}
        ]
    }
    bullets, method = extract_bullets(llm, SAMPLE, "resume.pdf")
    assert method == "llm"
    assert len(bullets) == 1
    assert bullets[0]["role"] == "VP at Corp"


def test_extract_bullets_falls_back_when_llm_raises():
    llm = MagicMock()
    llm.generate_json.side_effect = Exception("401 Invalid authentication credentials")
    bullets, method = extract_bullets(llm, SAMPLE, "resume.pdf")
    # Fell back to text extraction and surfaced the reason
    assert method.startswith("text (llm failed:")
    assert "401" in method
    # Still got bullets from the heuristic path
    assert any("Led team" in b["text"] for b in bullets)


def test_extract_bullets_falls_back_when_llm_returns_nothing():
    llm = MagicMock()
    llm.generate_json.return_value = {"roles": []}
    bullets, method = extract_bullets(llm, SAMPLE, "resume.pdf")
    assert "llm found nothing" in method
    assert len(bullets) >= 1  # heuristic still found some


def test_extract_bullets_no_llm_uses_text():
    bullets, method = extract_bullets(None, SAMPLE, "resume.pdf")
    assert method == "text"
    assert len(bullets) >= 1


def test_extract_bullets_llm_raises_on_failure():
    """extract_bullets_llm itself must not swallow — callers decide fallback."""
    llm = MagicMock()
    llm.generate_json.side_effect = RuntimeError("boom")
    try:
        extract_bullets_llm(llm, SAMPLE, "resume.pdf")
        assert False, "expected the exception to propagate"
    except RuntimeError:
        pass
