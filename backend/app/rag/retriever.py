"""
rag/retriever.py - find the policy chunks closest to a question (owner: Piyush, M2).

How it works:
  1. All chunk vectors (~85 rows) are loaded once from policy_chunks into a numpy matrix.
     The cache is reloaded only when the table's fingerprint (count, max id) changes,
     i.e. after scripts/ingest_policy.py was run again.
  2. The question is embedded with the same model; vectors are normalised, so
     cosine similarity = matrix @ query.
  3. The top RAG_TOP_K chunks are returned, keeping only those >= RAG_MIN_SIMILARITY.
Any embedding or database failure raises RetrievalError; the caller turns it into
POLICY_RETRIEVAL_FAILED (Vera then says policy information is temporarily unavailable).
"""
import threading

import numpy as np

from app.core.config import get_settings
from app.core.database import transaction
from app.rag import embeddings
from app.repositories import policy_chunk_repo
from app.schemas import RetrievedChunk


class RetrievalError(Exception):
    """Embedding model or database unavailable."""


_lock = threading.Lock()
_cache: dict = {"fingerprint": None, "rows": [], "matrix": None}


def _load_cache() -> tuple[list, np.ndarray | None]:
    """Return (rows, matrix), reloading from PostgreSQL only if ingestion changed the table."""
    with transaction() as conn:
        fp = policy_chunk_repo.fingerprint(conn)
        if fp == _cache["fingerprint"]:
            return _cache["rows"], _cache["matrix"]
        rows = policy_chunk_repo.list_all(conn)
    with _lock:   # several requests may arrive at once; build the matrix once
        _cache["rows"] = rows
        _cache["matrix"] = np.array([r["embedding"] for r in rows], dtype=np.float32) if rows else None
        _cache["fingerprint"] = fp
    return _cache["rows"], _cache["matrix"]


def _scores(query: str) -> tuple[list, np.ndarray]:
    """Cosine similarity of the query against every chunk."""
    try:
        rows, matrix = _load_cache()
        if matrix is None:
            raise RetrievalError("policy_chunks is empty - run scripts/ingest_policy.py")
        q = np.asarray(embeddings.embed_query(query), dtype=np.float32)
        return rows, matrix @ q
    except RetrievalError:
        raise
    except Exception as exc:   # embedding model or database failure
        raise RetrievalError(f"{type(exc).__name__}: {exc}") from exc


def top_chunks(query: str, top_k: int | None = None) -> list[RetrievedChunk]:
    """The top_k closest chunks, best first, WITHOUT the similarity floor (logged as retrieved)."""
    rows, scores = _scores(query)
    best = np.argsort(-scores)[: top_k or get_settings().rag_top_k]
    return [RetrievedChunk(chunk_id=rows[i]["chunk_id"], ref_id=rows[i]["ref_id"],
                           section_title=rows[i]["section_title"], content=rows[i]["content"],
                           similarity=round(float(scores[i]), 4)) for i in best]


def search(query: str) -> list[RetrievedChunk]:
    """Top chunks that reach RAG_MIN_SIMILARITY - the only ones Vera may answer from."""
    return [c for c in top_chunks(query) if c.similarity >= get_settings().rag_min_similarity]


def best_similarity(query: str) -> float:
    """Highest similarity to any chunk; used by the intent router (>= 0.35 means POLICY)."""
    _, scores = _scores(query)
    return float(scores.max())
