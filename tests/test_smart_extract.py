"""Tests for the smart bullet extractor in the wizard."""

from jobhunter.gui.wizard import BulletReviewPage


def test_extracts_action_verb_lines():
    text = (
        "EXPERIENCE\n"
        "Led team of 12 engineers across 3 SOC locations\n"
        "Reduced security incidents by 45% through zero trust implementation\n"
        "Managed $2.4M annual security budget\n"
        "John Doe\n"
        "Columbus, OH\n"
    )
    bullets = BulletReviewPage._smart_extract(text, "test.pdf")
    texts = [b["text"] for b in bullets]
    assert any("Led team" in t for t in texts)
    assert any("Reduced security" in t for t in texts)
    assert any("Managed" in t for t in texts)
    # Should NOT extract the name or location
    assert not any("John Doe" in t for t in texts)
    assert not any("Columbus" in t for t in texts)


def test_extracts_bullet_prefixed_lines():
    text = (
        "• Built incident response program from ground up\n"
        "• Achieved CISSP and CISM certifications in 2020\n"
        "- Deployed Splunk Enterprise Security platform\n"
        "* Automated vulnerability scanning for 200+ endpoints\n"
    )
    bullets = BulletReviewPage._smart_extract(text, "test.pdf")
    assert len(bullets) == 4
    assert bullets[0]["text"].startswith("Built")
    assert bullets[2]["text"].startswith("Deployed")


def test_skips_headers_and_contact():
    text = (
        "JOHN DOE\n"
        "SENIOR SECURITY ENGINEER\n"
        "john@example.com | (555) 123-4567\n"
        "Columbus, OH 43201\n"
        "Led enterprise-wide zero trust implementation across all business units\n"
    )
    bullets = BulletReviewPage._smart_extract(text, "test.pdf")
    texts = [b["text"] for b in bullets]
    assert not any("JOHN DOE" in t for t in texts)
    assert not any("SENIOR SECURITY" in t for t in texts)
    assert not any("john@example" in t for t in texts)
    assert any("Led enterprise" in t for t in texts)


def test_extracts_numbered_lists():
    text = (
        "1. Designed cloud security architecture for AWS migration\n"
        "2. Implemented SIEM platform serving 500+ users\n"
        "3. Created security awareness training program\n"
    )
    bullets = BulletReviewPage._smart_extract(text, "test.pdf")
    assert len(bullets) == 3


def test_skips_short_lines():
    text = (
        "Skills\n"
        "Python\n"
        "AWS\n"
        "Led a complete overhaul of the incident response procedure documentation\n"
    )
    bullets = BulletReviewPage._smart_extract(text, "test.pdf")
    assert len(bullets) == 1
