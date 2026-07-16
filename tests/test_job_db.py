"""Tests for job_db.py."""

import pytest
from jobhunter.core.job_db import JobDB


def test_add_and_get_application(tmp_job_db: JobDB):
    app_id = tmp_job_db.add_application("Acme", "Engineer", location="NYC", source="dice")
    assert app_id > 0

    app = tmp_job_db.get_application(app_id)
    assert app is not None
    assert app["company"] == "Acme"
    assert app["position"] == "Engineer"
    assert app["location"] == "NYC"
    assert app["status"] == "new"


def test_update_application(tmp_job_db: JobDB):
    app_id = tmp_job_db.add_application("Acme", "Engineer")
    tmp_job_db.update_application(app_id, status="applied")

    app = tmp_job_db.get_application(app_id)
    assert app["status"] == "applied"
    assert app["date_applied"] is not None  # auto-set


def test_status_transition_validation(tmp_job_db: JobDB):
    app_id = tmp_job_db.add_application("Acme", "Engineer")
    # new -> applied is valid
    tmp_job_db.update_application(app_id, status="applied")
    # applied -> new is invalid
    with pytest.raises(ValueError, match="Cannot transition"):
        tmp_job_db.update_application(app_id, status="new")


def test_list_applications_filters(tmp_job_db: JobDB):
    tmp_job_db.add_application("A", "Eng", source="dice", fit_score=80)
    tmp_job_db.add_application("B", "Mgr", source="linkedin", fit_score=30)
    tmp_job_db.add_application("C", "Dir", source="dice", fit_score=60)

    # Filter by source
    results = tmp_job_db.list_applications(source="dice")
    assert len(results) == 2

    # Filter by min_score
    results = tmp_job_db.list_applications(min_score=50)
    assert len(results) == 2

    # Search
    results = tmp_job_db.list_applications(search="Mgr")
    assert len(results) == 1
    assert results[0]["company"] == "B"


def test_delete_application(tmp_job_db: JobDB):
    app_id = tmp_job_db.add_application("Acme", "Engineer")
    assert tmp_job_db.delete_application(app_id) is True
    assert tmp_job_db.get_application(app_id) is None


def test_url_exists(tmp_job_db: JobDB):
    tmp_job_db.add_application("A", "Eng", url="https://dice.com/jobs/123?ref=abc")
    assert tmp_job_db.url_exists("https://dice.com/jobs/123?ref=xyz") is not None
    assert tmp_job_db.url_exists("https://dice.com/jobs/999") is None


def test_events(tmp_job_db: JobDB):
    app_id = tmp_job_db.add_application("Acme", "Engineer")
    # 'found' event auto-created
    events = tmp_job_db.get_events(app_id)
    assert len(events) == 1
    assert events[0]["event_type"] == "found"

    # Add status change
    tmp_job_db.update_application(app_id, status="applied")
    events = tmp_job_db.get_events(app_id)
    assert len(events) == 2
    assert events[1]["event_type"] == "status_change"


def test_search_urls(tmp_job_db: JobDB):
    uid = tmp_job_db.add_search_url("dice", "https://dice.com/jobs?q=security")
    urls = tmp_job_db.list_search_urls()
    assert len(urls) == 1
    assert urls[0]["board"] == "dice"

    tmp_job_db.toggle_search_url(uid, False)
    enabled = tmp_job_db.list_search_urls(enabled_only=True)
    assert len(enabled) == 0

    tmp_job_db.delete_search_url(uid)
    assert len(tmp_job_db.list_search_urls()) == 0


def test_stats(tmp_job_db: JobDB):
    tmp_job_db.add_application("A", "Eng")
    tmp_job_db.add_application("B", "Mgr")
    app3 = tmp_job_db.add_application("C", "Dir")
    tmp_job_db.update_application(app3, status="applied")

    stats = tmp_job_db.get_stats()
    assert stats.get("new") == 2
    assert stats.get("applied") == 1


def test_focus_counts(tmp_job_db: JobDB):
    # Empty DB: everything zero
    counts = tmp_job_db.get_focus_counts()
    assert counts["total"] == 0
    assert counts["overdue_followups"] == 0

    # Seed: one high-fit new, one low-fit new, one applied with overdue follow-up
    tmp_job_db.add_application("A", "CISO", fit_score=85, jd_text="jd")
    tmp_job_db.add_application("B", "Analyst", fit_score=20, jd_text="jd")
    app3 = tmp_job_db.add_application("C", "Director", fit_score=70, jd_text="jd")
    tmp_job_db.update_application(app3, status="applied", follow_up_date="2020-01-01")
    app4 = tmp_job_db.add_application("D", "VP", fit_score=90, jd_text="jd")
    tmp_job_db.update_application(app4, status="applied")
    tmp_job_db.update_application(app4, status="offer")

    counts = tmp_job_db.get_focus_counts(high_fit_threshold=60)
    assert counts["total"] == 4
    assert counts["high_fit_new"] == 1       # A (B is below threshold, C/D not 'new')
    assert counts["overdue_followups"] == 1  # C
    assert counts["in_flight"] == 1          # C (D moved on to offer)
    assert counts["offers"] == 1             # D
    assert counts["added_this_week"] == 4
