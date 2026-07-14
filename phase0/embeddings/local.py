"""
Local embedding module — sentence-transformers (all-MiniLM-L6-v2).
Replaces OpenAI text-embedding-ada-002 for zero-cost local embeddings.
"""

import os
import json
import numpy as np
from typing import List, Optional

_MODEL = None
_MODEL_NAME = os.environ.get("AGENTOS_EMBED_MODEL", "all-MiniLM-L6-v2")
_DIMENSION = 384  # all-MiniLM-L6-v2 output dimension


def _get_model():
    """Lazy-load sentence-transformers model."""
    global _MODEL
    if _MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer
            _MODEL = SentenceTransformer(_MODEL_NAME)
        except ImportError:
            raise ImportError(
                "sentence-transformers required. Install: pip install sentence-transformers"
            )
    return _MODEL


def embed_text(text: str) -> List[float]:
    """Embed a single text string, return list of floats."""
    model = _get_model()
    vec = model.encode(text, normalize_embeddings=True)
    return vec.tolist()


def embed_texts(texts: List[str], batch_size: int = 32) -> List[List[float]]:
    """Embed multiple texts in batches. Returns list of float lists."""
    model = _get_model()
    vecs = model.encode(texts, batch_size=batch_size, normalize_embeddings=True)
    return vecs.tolist()


def serialize_embedding(vec: List[float]) -> str:
    """Serialize embedding vector to JSON string for SQLite storage."""
    return json.dumps(vec)


def deserialize_embedding(data: str) -> Optional[List[float]]:
    """Deserialize embedding from JSON string. Returns None if invalid."""
    if not data:
        return None
    try:
        vec = json.loads(data)
        if isinstance(vec, list) and len(vec) == _DIMENSION:
            return vec
        return None
    except (json.JSONDecodeError, TypeError):
        return None


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    a_np = np.array(a, dtype=np.float32)
    b_np = np.array(b, dtype=np.float32)
    dot = float(np.dot(a_np, b_np))
    norm_a = float(np.linalg.norm(a_np))
    norm_b = float(np.linalg.norm(b_np))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def vector_search(
    query_vec: List[float],
    candidates: List[dict],
    top_k: int = 5,
    score_threshold: float = 0.3,
) -> List[dict]:
    """
    In-memory vector search over candidates.
    Each candidate must have 'embedding' (str, JSON) and other fields.
    Returns top_k candidates sorted by similarity desc, filtered by threshold.
    """
    results = []
    for row in candidates:
        vec = deserialize_embedding(row.get("embedding", ""))
        if vec is None:
            continue
        score = cosine_similarity(query_vec, vec)
        if score >= score_threshold:
            results.append({**row, "_score": score})
    results.sort(key=lambda x: x["_score"], reverse=True)
    return results[:top_k]
