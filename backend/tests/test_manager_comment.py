"""
Reject without comment 422; reject with comment OK; approve with/without comment OK; reject without reason 422.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0 > Testing strategy
"""

import pytest

from app.schemas import today


@pytest.fixture
def pending_ticket(api_client, team, make_trip, make_evidence, auth_header) -> int:
    """A PENDING ticket of Rohan (MEALS 1,800 is over the 1,500 threshold)."""
    rohan = team["employee"]
    trip_id = make_trip(rohan["employee_id"])
    response = api_client.post(
        f"/api/v1/trips/{trip_id}/tickets", headers=auth_header(rohan),
        json={"expenses": [{"expense_type": "MEALS", "amount": "1800", "expense_date": today().isoformat(),
                            "description": "Client dinner", "evidence_id": make_evidence(rohan["employee_id"])}]},
    )
    assert response.json()["status"] == "PENDING"
    return response.json()["ticket_id"]


def decide(api_client, team, auth_header, ticket_id: int, body: dict):
    return api_client.post(f"/api/v1/tickets/{ticket_id}/decision", headers=auth_header(team["manager"]), json=body)


@pytest.mark.parametrize(
    "body,field",
    [
        ({"decision": "REJECTED", "rejection_reason": "OTHER"}, "review_comment"),                    # no comment
        ({"decision": "REJECTED", "rejection_reason": "OTHER", "review_comment": "Too short"}, "review_comment"),
        ({"decision": "REJECTED", "review_comment": "Photo is blurred and unreadable."}, "rejection_reason"),
        ({"decision": "APPROVED", "rejection_reason": "OTHER"}, "rejection_reason"),                  # reason only on reject
    ],
)
def test_invalid_decisions_are_422_under_the_field(api_client, team, auth_header, pending_ticket, body, field) -> None:
    response = decide(api_client, team, auth_header, pending_ticket, body)
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == field
    still = api_client.get(f"/api/v1/tickets/{pending_ticket}", headers=auth_header(team["employee"])).json()
    assert still["status"] == "PENDING"                                        # nothing was saved


def test_reject_with_reason_and_comment(api_client, team, auth_header, pending_ticket) -> None:
    comment = "Photo is blurred and the amount is not readable."
    response = decide(api_client, team, auth_header, pending_ticket,
                      {"decision": "REJECTED", "rejection_reason": "INSUFFICIENT_EVIDENCE", "review_comment": comment})
    assert response.status_code == 200
    ticket = response.json()
    assert ticket["status"] == "REJECTED" and ticket["is_read_only"] is True
    assert all(line["status"] == "REJECTED" for line in ticket["expenses"])         # lines mirror the ticket
    history = ticket["history"][0]
    assert (history["reviewer_type"], history["reviewer_name"], history["rejection_reason"], history["review_comment"]) == (
        "MANAGER", "Vikram Iyer", "INSUFFICIENT_EVIDENCE", comment
    )


@pytest.mark.parametrize("comment", [None, "Client dinner with three attendees; approved as an exception."])
def test_approve_with_or_without_comment(api_client, team, auth_header, pending_ticket, comment) -> None:
    body = {"decision": "APPROVED"} | ({"review_comment": comment} if comment else {})
    response = decide(api_client, team, auth_header, pending_ticket, body)
    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED"
    assert response.json()["history"][0]["review_comment"] == comment


def test_only_the_approving_manager_decides(api_client, team, auth_header, pending_ticket) -> None:
    url = f"/api/v1/tickets/{pending_ticket}/decision"
    body = {"decision": "APPROVED"}
    assert api_client.post(url, headers=auth_header(team["employee"]), json=body).status_code == 403
    assert api_client.post(url, headers=auth_header(team["other_manager"]), json=body).status_code == 404
