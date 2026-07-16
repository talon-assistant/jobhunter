"""Tests for the bullet coach: rule checks and LLM-assisted drafting."""

from unittest.mock import MagicMock

from jobhunter.core.bullet_coach import (
    bullet_issues,
    check_bullet,
    draft_bullets,
    improve_bullet,
)


# ---------------------------------------------------------------------------
# Rule-based feedback
# ---------------------------------------------------------------------------

def test_strong_bullet_passes():
    text = "Reduced mean time to respond by 40% by automating SOC triage for a 6-person team"
    issues = bullet_issues(text)
    assert issues == []
    kinds_ok = {c.kind for c in check_bullet(text) if c.ok}
    assert "verb" in kinds_ok
    assert "metric" in kinds_ok


def test_flags_weak_opener():
    issues = bullet_issues("Responsible for managing the security team and 12 vendors")
    assert any(c.kind == "verb" for c in issues)


def test_flags_missing_metric():
    issues = bullet_issues("Led the security team through a major cloud migration")
    assert any(c.kind == "metric" for c in issues)


def test_flags_first_person():
    issues = bullet_issues("Built a tool that saved my team 10 hours per week")
    assert any(c.kind == "pronoun" for c in issues)


def test_flags_buzzwords():
    issues = bullet_issues(
        "Led 3 results-driven initiatives as a team player across the org"
    )
    assert any(c.kind == "buzzword" for c in issues)


def test_flags_unresolved_placeholder():
    issues = bullet_issues("Led a [team size]-person team, cutting costs by [X%]")
    assert any(c.kind == "placeholder" for c in issues)


def test_flags_run_on_length():
    long_bullet = "Led " + " ".join(["word"] * 40) + " with 5 people"
    issues = bullet_issues(long_bullet)
    assert any(c.kind == "length" for c in issues)


def test_empty_text_returns_nothing():
    assert check_bullet("") == []
    assert check_bullet("   ") == []


# ---------------------------------------------------------------------------
# LLM-assisted drafting
# ---------------------------------------------------------------------------

def test_draft_bullets_parses_llm_output():
    llm = MagicMock()
    llm.generate_json.return_value = {
        "bullets": [
            {
                "text": "Led a [team size]-person SOC team, cutting MTTR by [X%]",
                "questions": ["How many analysts?", "How much faster?"],
            },
            {"text": "Automated triage playbooks for phishing response", "questions": []},
        ]
    }

    drafts = draft_bullets(llm, "I ran the SOC and we got faster at incidents", role="SOC Manager")
    assert len(drafts) == 2
    assert drafts[0]["questions"] == ["How many analysts?", "How much faster?"]
    assert drafts[1]["questions"] == []

    # The user's own words must reach the model — that's the source of truth
    prompt = llm.generate_json.call_args[0][0]
    assert "I ran the SOC" in prompt
    assert "SOC Manager" in prompt


def test_draft_bullets_skips_malformed_entries():
    llm = MagicMock()
    llm.generate_json.return_value = {
        "bullets": [
            {"text": "  "},                  # blank
            "not a dict",                     # wrong type
            {"text": "Valid bullet with 3 systems migrated"},
        ]
    }
    drafts = draft_bullets(llm, "description")
    assert len(drafts) == 1
    assert drafts[0]["text"].startswith("Valid bullet")


def test_improve_bullet_returns_variants():
    llm = MagicMock()
    llm.generate_json.return_value = {
        "variants": [
            {"style": "impact", "text": "Cut MTTR 40% by automating SOC triage"},
            {"style": "concise", "text": "Automated SOC triage, cutting MTTR 40%"},
            {"style": "leadership", "text": "Led SOC automation effort that cut MTTR 40%"},
        ],
        "questions": [],
    }
    result = improve_bullet(llm, "Reduced MTTR by 40% via automation")
    assert len(result["variants"]) == 3
    assert {v["style"] for v in result["variants"]} == {"impact", "concise", "leadership"}


def test_improve_bullet_handles_junk():
    llm = MagicMock()
    llm.generate_json.return_value = ["totally", "wrong", "shape"]
    result = improve_bullet(llm, "some bullet")
    assert result == {"variants": [], "questions": []}
