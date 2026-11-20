"""
repositories/policy_chunk_repo.py - SQL for policy_chunks, the RAG store (owner: Piyush, M2).

Written only by scripts/ingest_policy.py; read by rag/retriever.py.
Weather results and chat messages are never written here.
"""
from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping


def insert_if_new(conn: Connection, *, ref_id: str, section_title: str, chunk_index: int,
                  content: str, embedding: list[float], source_file: str, content_hash: str) -> bool:
    """Insert one chunk unless a chunk with the same content_hash exists. True if inserted."""
    result = conn.execute(text("""
        INSERT INTO policy_chunks (ref_id, section_title, chunk_index, content, embedding,
                                   source_file, content_hash)
        VALUES (:ref_id, :section_title, :chunk_index, :content, :embedding, :source_file, :content_hash)
        ON CONFLICT (content_hash) DO NOTHING"""),
        {"ref_id": ref_id, "section_title": section_title, "chunk_index": chunk_index, "content": content,
         "embedding": embedding, "source_file": source_file, "content_hash": content_hash})
    return result.rowcount == 1


def delete_stale(conn: Connection, source_file: str, keep_hashes: list[str]) -> int:
    """Remove chunks of this document whose text no longer exists (the rule changed or was removed)."""
    result = conn.execute(text("""
        DELETE FROM policy_chunks
        WHERE source_file = :source_file AND NOT (content_hash = ANY(:keep))"""),
        {"source_file": source_file, "keep": keep_hashes})
    return result.rowcount


def list_all(conn: Connection) -> list[RowMapping]:
    """Every chunk with its vector (about 85 rows), for the in-memory retrieval cache."""
    return list(conn.execute(text("""
        SELECT chunk_id, ref_id, section_title, content, embedding
        FROM policy_chunks ORDER BY chunk_id""")).mappings())


def fingerprint(conn: Connection) -> tuple[int, int]:
    """(row count, highest chunk_id): changes whenever ingestion adds or removes chunks,
    so the retriever knows when to reload its cache."""
    row = conn.execute(text("SELECT count(*), COALESCE(max(chunk_id), 0) FROM policy_chunks")).one()
    return int(row[0]), int(row[1])
