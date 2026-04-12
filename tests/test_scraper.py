"""Tests for scraper.py (URL parsing and board detection only)."""

from jobhunter.core.scraper import clean_search_url, detect_board


def test_detect_board_linkedin():
    assert detect_board("https://www.linkedin.com/jobs/search/?keywords=security") == "linkedin"


def test_detect_board_dice():
    assert detect_board("https://www.dice.com/jobs?q=python") == "dice"


def test_detect_board_builtin():
    assert detect_board("https://builtin.com/jobs?search=engineer") == "builtin"


def test_detect_board_glassdoor():
    assert detect_board("https://www.glassdoor.com/Job/security-engineer-jobs.htm") == "glassdoor"


def test_detect_board_other():
    assert detect_board("https://company.greenhouse.io/jobs/12345") == "other"


def test_clean_search_url():
    url = "https://linkedin.com/jobs/search/?keywords=security&start=25&trk=abc&origin=JOB_SEARCH"
    cleaned = clean_search_url(url)
    assert "start=" not in cleaned
    assert "trk=" not in cleaned
    assert "origin=" not in cleaned
    assert "keywords=security" in cleaned
