"""Tests for resume_db.py."""

from unittest.mock import patch

import numpy as np
import pytest

from jobhunter.core.resume_db import ResumeDB


@pytest.fixture
def db_no_embed(tmp_path):
    """ResumeDB with embedding disabled."""
    db = ResumeDB(tmp_path / "test_resume.db")
    yield db
    db.close()


def test_add_and_get_bullet(db_no_embed: ResumeDB):
    with patch("jobhunter.core.resume_db.embed_text") as mock_embed:
        mock_embed.return_value = np.zeros(768, dtype=np.float32)

        bid = db_no_embed.add_bullet("experience", "Led team of 12 engineers")
        assert bid > 0

        b = db_no_embed.get_bullet(bid)
        assert b is not None
        assert b["text"] == "Led team of 12 engineers"
        assert b["section"] == "experience"
        assert b["priority"] == "normal"


def test_update_bullet(db_no_embed: ResumeDB):
    with patch("jobhunter.core.resume_db.embed_text") as mock_embed:
        mock_embed.return_value = np.zeros(768, dtype=np.float32)

        bid = db_no_embed.add_bullet("experience", "Old text")
        db_no_embed.update_bullet(bid, text="New text")

        b = db_no_embed.get_bullet(bid)
        assert b["text"] == "New text"


def test_delete_bullet(db_no_embed: ResumeDB):
    with patch("jobhunter.core.resume_db.embed_text") as mock_embed:
        mock_embed.return_value = np.zeros(768, dtype=np.float32)

        bid = db_no_embed.add_bullet("experience", "Test bullet")
        assert db_no_embed.delete_bullet(bid) is True
        assert db_no_embed.get_bullet(bid) is None


def test_list_bullets_by_section(db_no_embed: ResumeDB):
    with patch("jobhunter.core.resume_db.embed_text") as mock_embed:
        mock_embed.return_value = np.zeros(768, dtype=np.float32)

        db_no_embed.add_bullet("experience", "Bullet 1")
        db_no_embed.add_bullet("experience", "Bullet 2")
        db_no_embed.add_bullet("skills", "Bullet 3")

        exp = db_no_embed.list_bullets(section="experience")
        assert len(exp) == 2

        skills = db_no_embed.list_bullets(section="skills")
        assert len(skills) == 1


def test_get_sections(db_no_embed: ResumeDB):
    with patch("jobhunter.core.resume_db.embed_text") as mock_embed:
        mock_embed.return_value = np.zeros(768, dtype=np.float32)

        db_no_embed.add_bullet("experience", "A")
        db_no_embed.add_bullet("skills", "B")
        db_no_embed.add_bullet("education", "C")

        sections = db_no_embed.get_sections()
        assert set(sections) == {"experience", "skills", "education"}


def test_increment_selected(db_no_embed: ResumeDB):
    with patch("jobhunter.core.resume_db.embed_text") as mock_embed:
        mock_embed.return_value = np.zeros(768, dtype=np.float32)

        bid = db_no_embed.add_bullet("experience", "Test")
        db_no_embed.increment_selected(bid)
        db_no_embed.increment_selected(bid)

        b = db_no_embed.get_bullet(bid)
        assert b["times_selected"] == 2
        assert b["last_selected"] is not None


def test_export_import_markdown(db_no_embed: ResumeDB, tmp_path):
    with patch("jobhunter.core.resume_db.embed_text") as mock_embed:
        mock_embed.return_value = np.zeros(768, dtype=np.float32)

        db_no_embed.add_bullet("experience", "Led team of 12", role="VP at Acme")
        db_no_embed.add_bullet("experience", "Reduced incidents by 45%", role="VP at Acme")
        db_no_embed.add_bullet("skills", "CISSP certification")

    md_path = tmp_path / "export.md"
    db_no_embed.export_markdown(md_path)

    assert md_path.exists()
    content = md_path.read_text()
    assert "## experience" in content
    assert "Led team of 12" in content

    # Import into a fresh DB (no existing bullets -> no duplicates possible)
    db2 = ResumeDB(tmp_path / "test2.db")
    with patch("jobhunter.core.resume_db.embed_text") as mock2:
        # Each call returns a unique vector so dedup doesn't trigger
        call_count = 0
        def unique_vec(text):
            nonlocal call_count
            v = np.random.randn(768).astype(np.float32)
            v /= np.linalg.norm(v)
            call_count += 1
            return v
        mock2.side_effect = unique_vec
        count = db2.import_from_markdown(md_path)

    assert count == 3
    db2.close()
