"""BGE embedding wrapper using fastembed (ONNX Runtime).

Replaces sentence-transformers + PyTorch with a lightweight ONNX-based
embedding library. Same BGE model, same vectors, ~30MB instead of ~800MB.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

log = logging.getLogger(__name__)

_MODEL_NAME = "BAAI/bge-base-en-v1.5"
_DIMENSION = 768

# Lazy-loaded global model instance
_model = None


def _get_model():
    """Lazy-load the fastembed model (downloads ONNX weights on first use)."""
    global _model
    if _model is None:
        log.info("Loading embedding model: %s", _MODEL_NAME)
        from fastembed import TextEmbedding
        _model = TextEmbedding(model_name=_MODEL_NAME)
        log.info("Embedding model loaded (dim=%d)", _DIMENSION)
    return _model


def embed_text(text: str) -> NDArray[np.float32]:
    """Embed a single string, returning a normalized 768-dim vector."""
    model = _get_model()
    # fastembed returns a generator, consume it
    vecs = list(model.embed([text]))
    vec = np.asarray(vecs[0], dtype=np.float32)
    # Normalize
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec


def embed_texts(texts: list[str], *, batch_size: int = 32) -> NDArray[np.float32]:
    """Embed multiple strings, returning an (N, 768) normalized matrix."""
    if not texts:
        return np.empty((0, _DIMENSION), dtype=np.float32)
    model = _get_model()
    vecs = list(model.embed(texts, batch_size=batch_size))
    result = np.asarray(vecs, dtype=np.float32)
    # Normalize each row
    norms = np.linalg.norm(result, axis=1, keepdims=True)
    norms = np.where(norms > 0, norms, 1.0)
    result = result / norms
    return result


def cosine_similarity(a: NDArray[np.float32], b: NDArray[np.float32]) -> float:
    """Cosine similarity between two normalized vectors (fast dot product)."""
    return float(np.dot(a, b))


def cosine_similarity_matrix(
    query: NDArray[np.float32], corpus: NDArray[np.float32]
) -> NDArray[np.float32]:
    """Cosine similarities between one query vector and a corpus matrix.

    Parameters
    ----------
    query : (768,) normalized vector
    corpus : (N, 768) normalized matrix

    Returns
    -------
    (N,) array of similarities in [-1, 1]
    """
    if corpus.shape[0] == 0:
        return np.empty(0, dtype=np.float32)
    return corpus @ query


def vec_to_bytes(vec: NDArray[np.float32]) -> bytes:
    """Serialize a numpy vector to bytes for SQLite BLOB storage."""
    return vec.astype(np.float32).tobytes()


def bytes_to_vec(blob: bytes) -> NDArray[np.float32]:
    """Deserialize bytes from SQLite BLOB back to a numpy vector."""
    return np.frombuffer(blob, dtype=np.float32).copy()


# Module-level constants
DIMENSION = _DIMENSION
MODEL_NAME = _MODEL_NAME
