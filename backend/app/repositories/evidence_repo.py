"""
SQL for expense_evidence and evidence_files.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0
"""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection


def insert(
    db: Connection,
    employee_id: int,
    original_filename: str,
    mime_type: str,
    content: bytes,
    sha256: str,
) -> dict:
    """Store one upload: metadata row (EVD code from the sequence) + the bytes, same transaction."""
    row = db.execute(
        text(
            """
            INSERT INTO expense_evidence (employee_id, original_filename, mime_type, size_bytes, sha256)
            VALUES (:employee_id, :original_filename, :mime_type, :size_bytes, :sha256)
            RETURNING evidence_id, evidence_code, original_filename, mime_type, size_bytes,
                      sha256, uploaded_at
            """
        ),
        {
            "employee_id": employee_id,
            "original_filename": original_filename,
            "mime_type": mime_type,
            "size_bytes": len(content),
            "sha256": sha256,
        },
    ).mappings().one()
    db.execute(
        text("INSERT INTO evidence_files (evidence_id, content) VALUES (:evidence_id, :content)"),
        {"evidence_id": row["evidence_id"], "content": content},
    )
    return dict(row)


def get_file(db: Connection, evidence_id: UUID) -> dict | None:
    """Photo bytes + who may see them (uploader and the uploader's line manager)."""
    row = db.execute(
        text(
            """
            SELECT v.evidence_id, v.employee_id, e.manager_id AS owner_manager_id,
                   v.mime_type, v.original_filename, f.content
            FROM expense_evidence AS v
            JOIN evidence_files AS f ON f.evidence_id = v.evidence_id
            JOIN employees AS e ON e.employee_id = v.employee_id
            WHERE v.evidence_id = :evidence_id
            """
        ),
        {"evidence_id": evidence_id},
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


def lock_for_ticket(db: Connection, evidence_ids: list[UUID]) -> dict[UUID, dict]:
    """Lock the evidence rows a new ticket wants to use; report owner, hash and whether attached."""
    rows = db.execute(
        text(
            """
            SELECT v.evidence_id, v.employee_id, v.sha256,
                   EXISTS (SELECT 1 FROM expenses AS x WHERE x.evidence_id = v.evidence_id) AS is_attached
            FROM expense_evidence AS v
            WHERE v.evidence_id = ANY(:evidence_ids)
            FOR UPDATE OF v
            """
        ),
        {"evidence_ids": evidence_ids},
    ).mappings().all()
    return {row["evidence_id"]: dict(row) for row in rows}


def delete_unattached_older_than(db: Connection, hours: int) -> int:
    """Scheduler clean-up: uploads never attached to an expense line after `hours` hours.
    evidence_files rows are removed by ON DELETE CASCADE."""
    result = db.execute(
        text(
            """
            DELETE FROM expense_evidence AS v
            WHERE v.uploaded_at < now() - make_interval(hours => CAST(:hours AS INT))
              AND NOT EXISTS (SELECT 1 FROM expenses AS x WHERE x.evidence_id = v.evidence_id)
            """
        ),
        {"hours": hours},
    )
    return result.rowcount
