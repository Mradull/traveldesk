"""
scripts/ingest_policy.py - build Vera's policy index (owner: Piyush, M2).

Run from backend/ after init_db.py, and again whenever data/expense_policy.txt changes:
    python scripts/ingest_policy.py

Steps: read the document -> chunk_policy() -> embed every chunk with all-MiniLM-L6-v2 ->
insert chunks whose content_hash is new -> delete chunks of this file that no longer exist.
Safe to run any number of times (idempotent). The running API notices the change on its
next search (the retriever compares the table fingerprint).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # so "import app" works from backend/

from app.core.config import get_settings                 # noqa: E402
from app.core.database import transaction                # noqa: E402
from app.rag.chunker import chunk_policy                 # noqa: E402
from app.rag.embeddings import embed_texts               # noqa: E402
from app.repositories import policy_chunk_repo           # noqa: E402


def main() -> None:
    settings = get_settings()
    path = Path(settings.policy_document_path)
    if not path.is_absolute():                     # relative paths are relative to backend/
        path = Path(__file__).resolve().parents[1] / path
    chunks = chunk_policy(path.read_text(encoding="utf-8"))
    print(f"Read {path}: {len(chunks)} chunks from {len({c.ref_id for c in chunks})} rule ids")

    vectors = embed_texts([c.content for c in chunks])    # first run downloads the model (~90 MB)
    if len(vectors[0]) != settings.embedding_dimensions:
        raise SystemExit(f"Model returned {len(vectors[0])} dims, expected {settings.embedding_dimensions}")

    # One transaction: the index is never half-updated.
    with transaction() as conn:
        added = sum(policy_chunk_repo.insert_if_new(
            conn, ref_id=c.ref_id, section_title=c.section_title, chunk_index=c.chunk_index,
            content=c.content, embedding=v, source_file=path.name, content_hash=c.content_hash)
            for c, v in zip(chunks, vectors))
        removed = policy_chunk_repo.delete_stale(conn, path.name, [c.content_hash for c in chunks])
        total, _ = policy_chunk_repo.fingerprint(conn)
    print(f"policy_chunks: {added} added, {removed} removed, {total} in total")


if __name__ == "__main__":
    main()
