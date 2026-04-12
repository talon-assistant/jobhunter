"""Job description sanitizer: strip prompt injections before LLM exposure.

Two-tier approach:
  Tier 1 -- Regex/heuristic pattern matching for known injection phrases
  Tier 2 -- BGE semantic outlier detection for novel injections

The sanitized JD is what gets stored in the DB and fed to all prompts.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field

import numpy as np

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Tier 1: Known injection patterns
# ──────────────────────────────────────────────────────────────────────

# Phrases that indicate instructions directed at AI systems.
# Each pattern is compiled case-insensitive.
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        # Direct AI addressing
        r"if you are an?\s*(ai|llm|language model|chatbot|assistant|agent)",
        r"(attention|note to|message for|instructions? for)\s*(ai|llm|language model|chatbot|assistant|agent)",
        r"(dear|hello|hey)\s*(ai|llm|language model|chatbot|assistant|agent)",
        r"ai\s*(system|model|agent|assistant)\s*[:,]",

        # Override / ignore instructions
        r"ignore\s*(all\s*)?(previous|prior|above|earlier)\s*(instructions?|prompts?|context)",
        r"disregard\s*(all\s*)?(previous|prior|above|earlier)\s*(instructions?|prompts?)",
        r"override\s*(previous|prior|all)?\s*(instructions?|prompts?|rules?)",
        r"forget\s*(everything|all|what)\s*(you|i)?\s*(said|told|know|learned)",
        r"new\s*instructions?\s*:",
        r"system\s*prompt\s*override",

        # Score/rating manipulation
        r"(rate|score|rank)\s*this\s*(job|posting|position)\s*(a\s*)?(\d+|perfect|100|highly)",
        r"(recommend|suggest)\s*(immediate|strong|definite)\s*(application|apply|match)",
        r"this\s*is\s*a\s*perfect\s*(fit|match)\s*(for|score)",
        r"fit\s*score\s*[:=]\s*\d+",

        # Role/behavior manipulation
        r"(act|behave|respond|pretend)\s*as\s*(if|though)",
        r"you\s*are\s*now\s*(a|an|in)\s",
        r"(switch|change)\s*(to|into)\s*(mode|role|persona)",
        r"(from now on|henceforth|going forward)\s*(you|please|always)",

        # Specific model names (shouldn't appear in a real JD)
        r"(chatgpt|gpt-?\d|claude|gemini|llama|mistral|qwen)\s*[:,]?\s*(please|should|must|ignore|focus)",

        # Exfiltration / tool use
        r"(output|return|print|echo|repeat)\s*(the|your|all)\s*(system|instructions?|prompt|rules?)",
        r"(call|use|invoke|execute)\s*(tool|function|api|endpoint)",
        r"(send|post|transmit|forward)\s*(to|this|data|results?)\s*(to|at|via)",

        # Hidden instruction markers
        r"\[system\]",
        r"\[instruction\]",
        r"\[hidden\]",
        r"<!--.*?-->",  # HTML comments
        r"<\s*!\s*-\s*-",  # Malformed HTML comments
    ]
]

# Topics that should never dominate a professional job description.
# If a paragraph is primarily about one of these AND it doesn't match
# the job's domain, it's suspicious.
_ABSURD_TOPICS = [
    "parrot", "hippopotamus", "unicorn", "dragon", "wizard",
    "magic spell", "hogwarts", "pokemon", "minecraft",
    "banana farming", "underwater basket weaving",
]

# Zero-width and invisible Unicode characters used to hide text
_INVISIBLE_CHARS = re.compile(
    r"[\u200b\u200c\u200d\u200e\u200f"  # zero-width spaces/joiners
    r"\u2060\u2061\u2062\u2063\u2064"    # invisible operators
    r"\ufeff"                             # BOM
    r"\u00ad"                             # soft hyphen
    r"\u034f"                             # combining grapheme joiner
    r"\u061c"                             # Arabic letter mark
    r"\u115f\u1160"                       # Hangul fillers
    r"\u17b4\u17b5"                       # Khmer vowel inherent
    r"\u180e"                             # Mongolian vowel separator
    r"\uffa0"                             # Halfwidth Hangul filler
    r"]+"
)


@dataclass
class SanitizeResult:
    """Result of sanitizing a job description."""

    clean_text: str
    flags: list[str] = field(default_factory=list)
    stripped_count: int = 0
    is_suspicious: bool = False

    @property
    def summary(self) -> str:
        if not self.flags:
            return "Clean"
        return f"Stripped {self.stripped_count} suspicious segment(s): {'; '.join(self.flags)}"


def sanitize(
    text: str,
    *,
    job_context: str = "",
    semantic_threshold: float = 0.20,
    min_paragraph_len: int = 30,
) -> SanitizeResult:
    """Sanitize a job description, stripping injection attempts.

    Parameters
    ----------
    text : raw job description text
    job_context : optional context string (e.g. "Senior Security Engineer")
        used for semantic outlier detection
    semantic_threshold : paragraphs with cosine similarity below this
        (relative to the document average) are flagged as outliers
    min_paragraph_len : paragraphs shorter than this are skipped for
        semantic analysis (headers, short lines are fine)

    Returns
    -------
    SanitizeResult with cleaned text and flags
    """
    if not text or not text.strip():
        return SanitizeResult(clean_text="")

    flags: list[str] = []
    stripped = 0

    # -- Pre-processing: remove invisible characters --
    cleaned = _INVISIBLE_CHARS.sub("", text)
    if len(cleaned) < len(text):
        diff = len(text) - len(cleaned)
        flags.append(f"Removed {diff} invisible Unicode characters")
        stripped += 1

    # -- Tier 1: Regex pattern matching --
    paragraphs = _split_paragraphs(cleaned)
    safe_paragraphs: list[str] = []

    for para in paragraphs:
        injection_found = _check_tier1(para)
        if injection_found:
            flags.append(f"T1: {injection_found}")
            stripped += 1
            log.warning("Injection stripped (Tier 1): %s -- %s", injection_found, para[:80])
            continue
        safe_paragraphs.append(para)

    # -- Tier 2: Semantic outlier detection --
    if len(safe_paragraphs) >= 3:
        analyzable = [p for p in safe_paragraphs if len(p) >= min_paragraph_len]
        if len(analyzable) >= 3:
            outlier_indices = _check_tier2(
                analyzable, job_context=job_context, threshold=semantic_threshold
            )
            if outlier_indices:
                outlier_set = set(outlier_indices)
                filtered = []
                a_idx = 0
                for para in safe_paragraphs:
                    if len(para) >= min_paragraph_len:
                        if a_idx in outlier_set:
                            flags.append(f"T2: Semantic outlier removed")
                            stripped += 1
                            log.warning("Injection stripped (Tier 2): %s", para[:80])
                            a_idx += 1
                            continue
                        a_idx += 1
                    filtered.append(para)
                safe_paragraphs = filtered

    clean_text = "\n\n".join(safe_paragraphs).strip()

    return SanitizeResult(
        clean_text=clean_text,
        flags=flags,
        stripped_count=stripped,
        is_suspicious=stripped > 0,
    )


# ──────────────────────────────────────────────────────────────────────
# Tier 1 internals
# ──────────────────────────────────────────────────────────────────────

def _check_tier1(text: str) -> str | None:
    """Check a paragraph against known injection patterns.

    Returns the matched pattern description or None.
    """
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            return pattern.pattern[:60]

    # Check for absurd topics (only flag if the paragraph is dominated by them)
    lower = text.lower()
    for topic in _ABSURD_TOPICS:
        if topic in lower:
            # Count how much of the paragraph is about this topic
            words = lower.split()
            topic_words = sum(1 for w in words if topic in w)
            if topic_words >= 2 or (len(words) < 20 and topic_words >= 1):
                return f"Absurd topic: {topic}"

    return None


# ──────────────────────────────────────────────────────────────────────
# Tier 2 internals
# ──────────────────────────────────────────────────────────────────────

def _check_tier2(
    paragraphs: list[str],
    *,
    job_context: str = "",
    threshold: float = 0.20,
) -> list[int]:
    """Find semantic outlier paragraphs using BGE embeddings.

    Returns indices of paragraphs that are outliers relative to
    the document's semantic centroid.
    """
    try:
        from jobhunter.core.embeddings import embed_texts, cosine_similarity_matrix
    except ImportError:
        log.warning("Embeddings not available; skipping Tier 2 sanitization")
        return []

    # Embed all paragraphs
    texts = list(paragraphs)
    if job_context:
        texts.append(job_context)

    try:
        vecs = embed_texts(texts)
    except Exception:
        log.exception("Embedding failed during sanitization")
        return []

    if job_context:
        para_vecs = vecs[:-1]
        context_vec = vecs[-1]
    else:
        para_vecs = vecs
        context_vec = None

    # Compute centroid of all paragraph vectors
    centroid = para_vecs.mean(axis=0)
    norm = np.linalg.norm(centroid)
    if norm > 0:
        centroid = centroid / norm

    # Compute similarity of each paragraph to the centroid
    sims = cosine_similarity_matrix(centroid, para_vecs)

    # If we have job context, also check similarity to context
    if context_vec is not None:
        context_sims = cosine_similarity_matrix(context_vec, para_vecs)
        # Use the max of centroid-sim and context-sim (generous)
        sims = np.maximum(sims, context_sims)

    # Find outliers: paragraphs far below the mean similarity
    mean_sim = float(sims.mean())
    std_sim = float(sims.std())
    outliers: list[int] = []

    for i, sim in enumerate(sims):
        sim_val = float(sim)
        # Flag if similarity is below threshold AND more than 1.5 std below mean
        if sim_val < threshold or (std_sim > 0 and sim_val < mean_sim - 1.5 * std_sim):
            outliers.append(i)
            log.debug(
                "Semantic outlier [%d]: sim=%.3f (mean=%.3f, std=%.3f): %s",
                i, sim_val, mean_sim, std_sim, paragraphs[i][:60],
            )

    return outliers


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _split_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs, preserving meaningful structure."""
    # Split on double newlines or single newlines followed by a blank-ish line
    raw = re.split(r"\n\s*\n", text)
    paragraphs: list[str] = []
    for chunk in raw:
        chunk = chunk.strip()
        if chunk:
            paragraphs.append(chunk)
    return paragraphs
