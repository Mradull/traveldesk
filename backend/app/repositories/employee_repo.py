"""
SQL for employees (never selects password_hash into API models).

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0
"""

from sqlalchemy import text
from sqlalchemy.engine import Connection


def get_for_authentication(db: Connection, email: str) -> dict | None:
    """Fetch the private password hash for login verification only."""
    row = db.execute(
        text(
            """
            SELECT employee_id, full_name, email, password_hash,
                   department, role, manager_id, is_active
            FROM employees
            WHERE email = :email
            """
        ),
        {"email": email},
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


def get_public_by_id(db: Connection, employee_id: int) -> dict | None:
    """Fetch current employee and role without selecting password_hash."""
    row = db.execute(
        text(
            """
            SELECT employee_id, full_name, email, department, role, manager_id
            FROM employees
            WHERE employee_id = :employee_id
              AND is_active = TRUE
            """
        ),
        {"employee_id": employee_id},
    ).mappings().one_or_none()
    return dict(row) if row is not None else None
