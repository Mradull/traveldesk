"""
rag/embeddings.py - text -> 384-number vectors (owner: Piyush, M2).

all-MiniLM-L6-v2 runs locally on the CPU through langchain-huggingface:
no API key, no quota, and the same text always gives the same vector (good for evals).
The model (~90 MB) downloads once on first use and is then cached by sentence-transformers.
Vectors are normalised, so cosine similarity = dot product.
"""
from langchain_core.embeddings import Embeddings

from app.core.config import get_settings

_embedder: Embeddings | None = None     # built on first use; tests replace it with a fake


def get_embedder() -> Embeddings:
    """Load the embedding model once per process."""
    global _embedder
    if _embedder is None:
        if get_settings().embedding_provider != "local":
            raise RuntimeError(f"Unsupported EMBEDDING_PROVIDER {get_settings().embedding_provider!r}")
        from langchain_huggingface import HuggingFaceEmbeddings   # heavy import, only when needed
        _embedder = HuggingFaceEmbeddings(model_name=get_settings().embedding_model,
                                          model_kwargs={"device": "cpu"},
                                          encode_kwargs={"normalize_embeddings": True})
    return _embedder


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Vectors for many texts (used by ingestion)."""
    return get_embedder().embed_documents(texts)


def embed_query(text: str) -> list[float]:
    """Vector for one question (used at retrieval time)."""
    return get_embedder().embed_query(text)
