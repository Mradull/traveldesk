"""
Second decision 409; PUT/PATCH/DELETE 405; DB triggers refuse UPDATE of decided tickets, lines, approvals.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0 > Testing strategy
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.schemas import today


@pytest.fixture
def decided_ticket(api_client, team, make_trip, make_evidence, auth_header) -> dict:
    """An APPROVED ticket (manager decision) of Rohan."""
    rohan = team["employee"]
    trip_id = make_trip(rohan["employee_id"])
    ticket = api_client.post(
        f"/api/v1/trips/{trip_id}/tickets", headers=auth_header(rohan),
        json={"expenses": [{"expense_type": "AIRFARE", "amount": "24500", "expense_date": today().isoformat(),
                            "description": "Return flight", "evidence_id": make_evidence(rohan["employee_id"])}]},
    ).json()
    decided = api_client.post(
        f"/api/v1/tickets/{ticket['ticket_id']}/decision", headers=auth_header(team["manager"]),
        json={"decision": "APPROVED", "review_comment": "Fare checked against the booking."},
    )
    assert decided.status_code == 200
    return decided.json()


def test_second_decision_is_409(api_client, team, auth_header, decided_ticket) -> None:
    response = api_client.post(
        f"/api/v1/tickets/{decided_ticket['ticket_id']}/decision", headers=auth_header(team["manager"]),
        json={"decision": "REJECTED", "rejection_reason": "OTHER", "review_comment": "Changed my mind later."},
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "ALREADY_DECIDED"


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
def test_no_edit_or_delete_endpoints(api_client, team, auth_header, decided_ticket, method) -> None:
    urls = [
        f"/api/v1/tickets/{decided_ticket['ticket_id']}",
        f"/api/v1/expenses/{decided_ticket['expenses'][0]['expense_id']}",
        f"/api/v1/tickets/{decided_ticket['ticket_id']}/decision",
        f"/api/v1/evidence/{decided_ticket['expenses'][0]['evidence_id']}",
    ]
    for url in urls:
        response = api_client.request(method, url, headers=auth_header(team["employee"]), json={})
        assert response.status_code == 405, url
        assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


@pytest.mark.parametrize(
    "sql,expected",
    [
        ("UPDATE expense_tickets SET total_amount = 1 WHERE ticket_id = :ticket_id", "TICKET_READ_ONLY"),
        ("DELETE FROM expense_tickets WHERE ticket_id = :ticket_id", "TICKET_READ_ONLY"),
        ("UPDATE expenses SET amount = 1 WHERE ticket_id = :ticket_id", "TICKET_READ_ONLY"),
        ("UPDATE expense_evidence SET original_filename = 'x.jpg' WHERE evidence_id = "
         "(SELECT evidence_id FROM expenses WHERE ticket_id = :ticket_id)", "TICKET_READ_ONLY"),
        ("UPDATE ticket_approvals SET review_comment = 'rewritten comment' WHERE ticket_id = :ticket_id",
         "ALREADY_DECIDED"),
        ("DELETE FROM ticket_approvals WHERE ticket_id = :ticket_id", "ALREADY_DECIDED"),
    ],
)
def test_database_triggers_refuse_changes(test_engine, decided_ticket, sql: str, expected: str) -> None:
    """Even a direct SQL edit (e.g. in pgAdmin) cannot rewrite a decision (migration 006)."""
    with pytest.raises(DBAPIError) as error:
        with test_engine.begin() as db:
            db.execute(text(sql), {"ticket_id": decided_ticket["ticket_id"]})
    assert error.value.orig.diag.message_primary == expected


def test_trip_approval_rows_are_permanent(api_client, team, make_trip, auth_header, test_engine) -> None:
    trip_id = make_trip(team["employee"]["employee_id"], state="IN_PROGRESS")
    api_client.post(f"/api/v1/trips/{trip_id}/decision", headers=auth_header(team["manager"]),
                    json={"decision": "APPROVED"})
    with pytest.raises(DBAPIError) as error:
        with test_engine.begin() as db:
            db.execute(text("UPDATE trip_approvals SET decision = 'REJECTED' WHERE trip_id = :t"), {"t": trip_id})
    assert error.value.orig.diag.message_primary == "ALREADY_DECIDED"
