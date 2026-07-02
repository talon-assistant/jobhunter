"""Two-phase job fit scoring: BGE embeddings (fast) + LLM (deep)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jobhunter.core import embeddings
from jobhunter.core.llm_client import LLMClient, LLMError

log = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "fit_analysis.txt"


@dataclass
class ScoredJob:
    """Result of scoring a single job against a resume."""

    company: str
    position: str
    location: str
    url: str
    source: str
    jd_text: str
    jd_embedding: bytes | None = None
    # Fast phase
    fast_score: float = 0.0
    # Deep phase (LLM)
    fit_score: int = 0
    strengths: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    summary: str = ""

    def to_db_fields(self) -> dict[str, Any]:
        return {
            "company": self.company,
            "position": self.position,
            "location": self.location,
            "url": self.url,
            "source": self.source,
            "jd_text": self.jd_text,
            "jd_embedding": self.jd_embedding,
            "fit_score": self.fit_score,
            "fit_analysis": json.dumps({
                "strengths": self.strengths,
                "gaps": self.gaps,
                "summary": self.summary,
                "fast_score": round(self.fast_score, 2),
            }),
        }


class FitScorer:
    """Score jobs against a resume using embeddings and optionally an LLM."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        *,
        deep_threshold: int = 50,
        batch_size: int = 2,
        jd_max_chars: int = 1500,
        auto_archive_below: int = 30,
    ) -> None:
        self.llm = llm_client
        self.deep_threshold = deep_threshold
        self.batch_size = batch_size
        self.jd_max_chars = jd_max_chars
        self.auto_archive_below = auto_archive_below
        self._prompt_template = ""
        if _PROMPT_PATH.exists():
            self._prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")

    def score_fast(
        self,
        resume_text: str,
        jobs: list[dict[str, str]],
    ) -> list[ScoredJob]:
        """Fast scoring using BGE cosine similarity.

        Each job dict must have: company, position, location, url, jd_text, source.
        Returns ScoredJob list with fast_score and fit_score set.
        """
        if not jobs:
            return []

        log.info("Fast-scoring %d jobs via embeddings...", len(jobs))
        resume_vec = embeddings.embed_text(resume_text)

        results: list[ScoredJob] = []
        for job in jobs:
            jd = job.get("jd_text", "")
            if not jd.strip():
                results.append(ScoredJob(
                    company=job.get("company", ""),
                    position=job.get("position", ""),
                    location=job.get("location", ""),
                    url=job.get("url", ""),
                    source=job.get("source", ""),
                    jd_text="",
                    fast_score=0.0,
                    fit_score=0,
                ))
                continue

            jd_vec = embeddings.embed_text(jd)
            sim = embeddings.cosine_similarity(resume_vec, jd_vec)
            # Map cosine similarity [0, 1] to a 0-100 score
            # Typical range for job matching is 0.3-0.8
            fast_score = max(0, min(100, int((sim - 0.3) * 200)))

            scored = ScoredJob(
                company=job.get("company", ""),
                position=job.get("position", ""),
                location=job.get("location", ""),
                url=job.get("url", ""),
                source=job.get("source", ""),
                jd_text=jd,
                jd_embedding=embeddings.vec_to_bytes(jd_vec),
                fast_score=sim,
                fit_score=fast_score,
            )
            results.append(scored)

        results.sort(key=lambda s: s.fit_score, reverse=True)
        log.info(
            "Fast scoring complete. Top: %d, Above threshold: %d",
            results[0].fit_score if results else 0,
            sum(1 for s in results if s.fit_score >= self.deep_threshold),
        )
        return results

    def score_deep(
        self,
        resume_text: str,
        jobs: list[ScoredJob],
    ) -> list[ScoredJob]:
        """Deep scoring using LLM analysis for jobs above threshold.

        Updates fit_score, strengths, gaps, summary on each ScoredJob in place.
        """
        if not self.llm:
            log.warning("No LLM client configured; skipping deep scoring")
            return jobs

        candidates = [j for j in jobs if j.fit_score >= self.deep_threshold]
        if not candidates:
            log.info("No jobs above deep threshold (%d); skipping LLM analysis", self.deep_threshold)
            return jobs

        log.info("Deep-scoring %d jobs via LLM (batch_size=%d)...", len(candidates), self.batch_size)

        for i in range(0, len(candidates), self.batch_size):
            batch = candidates[i : i + self.batch_size]
            self._score_batch(resume_text, batch)

        return jobs

    def score_all(
        self,
        resume_text: str,
        jobs: list[dict[str, str]],
    ) -> list[ScoredJob]:
        """Run both fast and deep scoring phases."""
        scored = self.score_fast(resume_text, jobs)
        return self.score_deep(resume_text, scored)

    def should_auto_archive(self, job: ScoredJob) -> bool:
        """True if a scored job falls below the auto-archive cutoff.

        Only archives jobs that actually have a JD — a job with no
        description scores 0 for lack of data, not lack of fit.
        """
        if self.auto_archive_below <= 0:
            return False
        return bool(job.jd_text.strip()) and job.fit_score < self.auto_archive_below

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _score_batch(self, resume_text: str, batch: list[ScoredJob]) -> None:
        """Score a batch of jobs via LLM and update in place."""
        job_entries = []
        for idx, job in enumerate(batch):
            jd_truncated = job.jd_text[: self.jd_max_chars]
            job_entries.append(
                f"JOB {idx + 1}:\n"
                f"Company: {job.company}\n"
                f"Position: {job.position}\n"
                f"Location: {job.location}\n"
                f"Description:\n{jd_truncated}\n"
            )

        prompt = self._prompt_template.replace("{{RESUME}}", resume_text)
        prompt = prompt.replace("{{JOBS}}", "\n---\n".join(job_entries))
        prompt = prompt.replace("{{COUNT}}", str(len(batch)))

        schema = {
            "type": "object",
            "properties": {
                "scores": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "job_index": {"type": "integer"},
                            "fit_score": {"type": "integer"},
                            "strengths": {"type": "array", "items": {"type": "string"}},
                            "gaps": {"type": "array", "items": {"type": "string"}},
                            "summary": {"type": "string"},
                        },
                        "required": ["job_index", "fit_score", "strengths", "gaps", "summary"],
                    },
                },
            },
            "required": ["scores"],
        }

        try:
            result = self.llm.generate_json(
                prompt, schema, system_prompt="You are a job fit analyst."
            )
            scores = result.get("scores", []) if isinstance(result, dict) else result
            for entry in scores:
                idx = entry.get("job_index", 0) - 1
                if 0 <= idx < len(batch):
                    batch[idx].fit_score = max(0, min(100, entry.get("fit_score", 0)))
                    batch[idx].strengths = entry.get("strengths", [])
                    batch[idx].gaps = entry.get("gaps", [])
                    batch[idx].summary = entry.get("summary", "")
        except LLMError:
            log.exception("LLM scoring failed for batch of %d", len(batch))
