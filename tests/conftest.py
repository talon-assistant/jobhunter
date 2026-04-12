"""Shared test fixtures."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from jobhunter.core.job_db import JobDB
from jobhunter.core.resume_db import ResumeDB


@pytest.fixture
def tmp_job_db(tmp_path):
    """A JobDB backed by a temp file."""
    db = JobDB(tmp_path / "test_jobs.db")
    yield db
    db.close()


@pytest.fixture
def tmp_resume_db(tmp_path):
    """A ResumeDB backed by a temp file (with embedding disabled)."""
    db = ResumeDB(tmp_path / "test_resume.db")
    yield db
    db.close()


@pytest.fixture
def mock_llm():
    """A mock LLMClient that returns canned responses."""
    client = MagicMock()
    client.is_healthy.return_value = True

    # Default: return a valid JSON string for generate_json
    client.generate_json.return_value = {"scores": []}
    client.generate_text.return_value = (
        "Dear Hiring Manager,\n\n"
        "I am writing to express my interest in the position. "
        "With over 10 years of experience in security operations, "
        "I have consistently delivered results that align with "
        "organizational goals.\n\n"
        "In my current role, I led a team of 12 engineers and "
        "reduced security incidents by 45%. I would welcome the "
        "opportunity to bring this expertise to your organization.\n\n"
        "Sincerely,\nJohn Doe"
    )
    return client


@pytest.fixture
def sample_jd():
    """A realistic job description string."""
    return (
        "Senior Security Engineer\n"
        "Acme Corporation - New York, NY\n\n"
        "We are looking for a Senior Security Engineer to join our team. "
        "The ideal candidate has 8+ years of experience in cybersecurity, "
        "CISSP certification, and experience with SIEM platforms (Splunk, "
        "Sentinel). You will lead incident response, manage vulnerability "
        "programs, and mentor junior engineers.\n\n"
        "Requirements:\n"
        "- 8+ years in cybersecurity\n"
        "- CISSP or equivalent certification\n"
        "- Experience with cloud security (AWS, Azure)\n"
        "- Strong communication skills\n"
        "- Team leadership experience\n"
    )


@pytest.fixture
def sample_resume():
    """A sample resume text."""
    return (
        "John Doe\nSecurity Leader | CISSP | 12 Years Experience\n\n"
        "VP Security Operations, Acme Holdings (2019-2023)\n"
        "- Led team of 12 security engineers across 3 SOCs\n"
        "- Reduced security incidents by 45% through zero trust implementation\n"
        "- Managed $2.4M annual security budget\n"
        "- Deployed Splunk Enterprise Security across 200+ endpoints\n\n"
        "Security Manager, TechCorp (2015-2019)\n"
        "- Built incident response program from ground up\n"
        "- Achieved CISSP, CISM certifications\n"
        "- Led AWS cloud security migration for 50+ workloads\n"
    )
