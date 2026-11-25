"""
SQL for receipt_checks (what was read from each receipt photo).

Owner: Mradul (M3)  |  Spec: Agile Spec v2.1 > Receipt verification
"""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

_COLUMNS = """evidence_id, status, is_receipt, total_amount, currency, receipt_date, merchant, city,
              from_place, to_place, summary, ai_generated_score, error_code, model_name, analyzed_at"""


def get(db: Connection, evidence_id: UUID) -> dict | None:
    row = db.execute(
        text(f"SELECT {_COLUMNS} FROM receipt_checks WHERE evidence_id = :evidence_id"),
        {"evidence_id": evidence_id},
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


def get_many(db: Connection, evidence_ids: list[UUID]) -> dict[UUID, dict]:
    rows = db.execute(
        text(f"SELECT {_COLUMNS} FROM receipt_checks WHERE evidence_id = ANY(:ids)"),
        {"ids": evidence_ids},
    ).mappings().all()
    return {row["evidence_id"]: dict(row) for row in rows}


def upsert(db: Connection, reading: dict) -> dict:
    """Store (or replace) the reading of one photo. Re-reading happens only for unattached photos."""
    row = db.execute(
        text(
            f"""
            INSERT INTO receipt_checks
                (evidence_id, status, is_receipt, total_amount, currency, receipt_date, merchant, city,
                 from_place, to_place, summary, ai_generated_score, error_code, model_name)
            VALUES
                (:evidence_id, :status, :is_receipt, :total_amount, :currency, :receipt_date, :merchant, :city,
                 :from_place, :to_place, :summary, :ai_generated_score, :error_code, :model_name)
            ON CONFLICT (evidence_id) DO UPDATE SET
                status = EXCLUDED.status, is_receipt = EXCLUDED.is_receipt,
                total_amount = EXCLUDED.total_amount, currency = EXCLUDED.currency,
                receipt_date = EXCLUDED.receipt_date, merchant = EXCLUDED.merchant, city = EXCLUDED.city,
                from_place = EXCLUDED.from_place, to_place = EXCLUDED.to_place, summary = EXCLUDED.summary,
                ai_generated_score = EXCLUDED.ai_generated_score, error_code = EXCLUDED.error_code,
                model_name = EXCLUDED.model_name, analyzed_at = now()
            RETURNING {_COLUMNS}
            """
        ),
        reading,
    ).mappings().one()
    return dict(row)


def is_attached(db: Connection, evidence_id: UUID) -> bool:
    """True once the photo belongs to an expense line (its reading is then frozen)."""
    return bool(db.execute(
        text("SELECT EXISTS (SELECT 1 FROM expenses WHERE evidence_id = :evidence_id)"),
        {"evidence_id": evidence_id},
    ).scalar_one())
