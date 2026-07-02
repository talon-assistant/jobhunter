"""Tests for fit_scorer.py."""

from unittest.mock import MagicMock, patch

import numpy as np

from jobhunter.core.fit_scorer import FitScorer


def test_score_fast_produces_scores(sample_jd, sample_resume):
    with patch("jobhunter.core.fit_scorer.embeddings") as mock_emb:
        # Return normalized vectors with some similarity
        resume_vec = np.random.randn(768).astype(np.float32)
        resume_vec /= np.linalg.norm(resume_vec)
        jd_vec = resume_vec + np.random.randn(768).astype(np.float32) * 0.3
        jd_vec /= np.linalg.norm(jd_vec)

        mock_emb.embed_text.side_effect = [resume_vec, jd_vec]
        mock_emb.cosine_similarity.return_value = float(np.dot(resume_vec, jd_vec))
        mock_emb.vec_to_bytes.return_value = b"\x00" * 3072

        scorer = FitScorer(None, deep_threshold=50)
        jobs = [{
            "company": "Acme", "position": "Engineer",
            "location": "NYC", "url": "https://example.com",
            "jd_text": sample_jd, "source": "dice",
        }]
        results = scorer.score_fast(sample_resume, jobs)
        assert len(results) == 1
        assert 0 <= results[0].fit_score <= 100


def test_score_fast_empty_jd():
    with patch("jobhunter.core.fit_scorer.embeddings") as mock_emb:
        mock_emb.embed_text.return_value = np.zeros(768, dtype=np.float32)

        scorer = FitScorer(None)
        jobs = [{
            "company": "A", "position": "B",
            "location": "", "url": "", "jd_text": "", "source": "",
        }]
        results = scorer.score_fast("resume text", jobs)
        assert len(results) == 1
        assert results[0].fit_score == 0


def test_score_deep_skips_low_scores():
    mock_llm = MagicMock()

    scorer = FitScorer(mock_llm, deep_threshold=50)
    from jobhunter.core.fit_scorer import ScoredJob
    jobs = [
        ScoredJob("A", "Eng", "", "", "", "jd", fit_score=30),
        ScoredJob("B", "Mgr", "", "", "", "jd", fit_score=20),
    ]
    scorer.score_deep("resume", jobs)
    # LLM should not have been called
    mock_llm.generate_json.assert_not_called()


def test_should_auto_archive():
    from jobhunter.core.fit_scorer import ScoredJob

    scorer = FitScorer(None, auto_archive_below=30)
    low = ScoredJob("A", "Eng", "", "", "", "jd text", fit_score=10)
    high = ScoredJob("B", "Mgr", "", "", "", "jd text", fit_score=80)
    no_jd = ScoredJob("C", "Dir", "", "", "", "", fit_score=0)

    assert scorer.should_auto_archive(low) is True
    assert scorer.should_auto_archive(high) is False
    # A job with no JD scored 0 for lack of data, not lack of fit
    assert scorer.should_auto_archive(no_jd) is False

    # Cutoff of 0 disables auto-archive entirely
    disabled = FitScorer(None, auto_archive_below=0)
    assert disabled.should_auto_archive(low) is False
