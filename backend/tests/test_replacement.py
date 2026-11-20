"""
Same trip_id; new ticket, expense and evidence ids; originals unchanged; second replacement 409; completed trip 409.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0 > Testing strategy
"""

import pytest
from sqlalchemy import text

from app.schemas import today


def _line(evidence_id: str) -> dict:
    return {"expense_type": "AIRFARE", "amount": "4200", "expense_date": today().isoformat(),
            "description": "Extra baggage", "evidence_id": evidence_id}


@pytest.fixture
def rejected(api_client, team, make_trip, make_evidence, auth_header) -> dict:
    """Rohan's ticket, rejected by Vikram (like seed TKT-00004). The duplicate invoice routes it
    to the manager: same invoice on an earlier auto-approved line."""
    rohan = team["employee"]
    trip_id = make_trip(rohan["employee_id"])
    url = f"/api/v1/trips/{trip_id}/tickets"
    api_client.post(url, headers=auth_header(rohan),
                    json={"expenses": [_line(make_evidence(rohan["employee_id"])) | {"invoice_number": "BAG-1"}]})
    ticket = api_client.post(url, headers=auth_header(rohan),
                             json={"expenses": [_line(make_evidence(rohan["employee_id"])) | {"invoice_number": "BAG-1"}]}).json()
    assert ticket["status"] == "PENDING"
    api_client.post(
        f"/api/v1/tickets/{ticket['ticket_id']}/decision", headers=auth_header(team["manager"]),
        json={"decision": "REJECTED", "rejection_reason": "INSUFFICIENT_EVIDENCE",
              "review_comment": "Photo is blurred. Raise a new ticket with a clear photo."},
    )
    return {"trip_id": trip_id, **api_client.get(f"/api/v1/tickets/{ticket['ticket_id']}",
                                                  headers=auth_header(rohan)).json()}


def _snapshot(test_engine, ticket_id: int) -> list:
    with test_engine.connect() as db:
        return db.execute(
            text("""SELECT k.status, k.total_amount, k.decided_at, x.expense_id, x.amount, x.evidence_id
                    FROM expense_tickets k JOIN expenses x ON x.ticket_id = k.ticket_id
                    WHERE k.ticket_id = :t"""),
            {"t": ticket_id},
        ).all()


def test_replacement_gets_new_ids_and_leaves_original_unchanged(
    api_client, team, make_evidence, auth_header, rejected, test_engine
) -> None:
    rohan = team["employee"]
    assert rejected["can_create_replacement"] is True
    before = _snapshot(test_engine, rejected["ticket_id"])

    response = api_client.post(
        f"/api/v1/trips/{rejected['trip_id']}/tickets", headers=auth_header(rohan),
        json={"replacement_of_ticket_id": rejected["ticket_id"], "expenses": [_line(make_evidence(rohan["employee_id"]))]},
    )
    assert response.status_code == 201
    new = response.json()
    assert new["trip_id"] == rejected["trip_id"]
    assert new["ticket_id"] != rejected["ticket_id"]
    assert new["expenses"][0]["expense_id"] != rejected["expenses"][0]["expense_id"]
    assert new["expenses"][0]["evidence_id"] != rejected["expenses"][0]["evidence_id"]
    assert new["replacement_of_ticket_code"] == rejected["ticket_code"]
    assert new["status"] == "AUTO_APPROVED"                     # full validation; inherits nothing

    original = api_client.get(f"/api/v1/tickets/{rejected['ticket_id']}", headers=auth_header(rohan)).json()
    assert original["status"] == "REJECTED" and original["replaced_by_ticket_code"] == new["ticket_code"]
    assert original["can_create_replacement"] is False
    assert _snapshot(test_engine, rejected["ticket_id"]) == before            # old rows unchanged


def test_second_replacement_is_409(api_client, team, make_evidence, auth_header, rejected) -> None:
    rohan = team["employee"]
    url = f"/api/v1/trips/{rejected['trip_id']}/tickets"
    body = lambda: {"replacement_of_ticket_id": rejected["ticket_id"],  # noqa: E731
                    "expenses": [_line(make_evidence(rohan["employee_id"]))]}
    assert api_client.post(url, headers=auth_header(rohan), json=body()).status_code == 201
    second = api_client.post(url, headers=auth_header(rohan), json=body())
    assert second.status_code == 409 and second.json()["error"]["code"] == "REPLACEMENT_NOT_ALLOWED"


def test_only_own_rejected_ticket_on_same_trip(api_client, team, make_trip, make_evidence, auth_header, rejected) -> None:
    rohan, sara = team["employee"], team["colleague"]
    # Another trip of Rohan: same owner, wrong trip.
    other_trip = make_trip(rohan["employee_id"])
    wrong_trip = api_client.post(
        f"/api/v1/trips/{other_trip}/tickets", headers=auth_header(rohan),
        json={"replacement_of_ticket_id": rejected["ticket_id"], "expenses": [_line(make_evidence(rohan["employee_id"]))]},
    )
    assert wrong_trip.status_code == 409 and wrong_trip.json()["error"]["code"] == "REPLACEMENT_NOT_ALLOWED"
    # Sara tries to replace Rohan's ticket on her own trip.
    saras_trip = make_trip(sara["employee_id"])
    not_owner = api_client.post(
        f"/api/v1/trips/{saras_trip}/tickets", headers=auth_header(sara),
        json={"replacement_of_ticket_id": rejected["ticket_id"], "expenses": [_line(make_evidence(sara["employee_id"]))]},
    )
    assert not_owner.status_code == 409


def test_replacement_of_a_non_rejected_ticket_is_409(api_client, team, make_trip, make_evidence, auth_header) -> None:
    rohan = team["employee"]
    trip_id = make_trip(rohan["employee_id"])
    url = f"/api/v1/trips/{trip_id}/tickets"
    approved = api_client.post(url, headers=auth_header(rohan),
                               json={"expenses": [_line(make_evidence(rohan["employee_id"]))]}).json()
    response = api_client.post(url, headers=auth_header(rohan), json={
        "replacement_of_ticket_id": approved["ticket_id"], "expenses": [_line(make_evidence(rohan["employee_id"]))]})
    assert response.status_code == 409 and response.json()["error"]["code"] == "REPLACEMENT_NOT_ALLOWED"


def test_replacement_on_completed_trip_is_409(api_client, team, make_evidence, auth_header, rejected, test_engine) -> None:
    with test_engine.begin() as db:
        db.execute(text("UPDATE travel_requests SET trip_state = 'COMPLETED', completion_type = 'AUTO', "
                        "completed_at = now() WHERE trip_id = :t"), {"t": rejected["trip_id"]})
    rohan = team["employee"]
    detail = api_client.get(f"/api/v1/tickets/{rejected['ticket_id']}", headers=auth_header(rohan)).json()
    assert detail["can_create_replacement"] is False
    response = api_client.post(
        f"/api/v1/trips/{rejected['trip_id']}/tickets", headers=auth_header(rohan),
        json={"replacement_of_ticket_id": rejected["ticket_id"], "expenses": [_line(make_evidence(rohan["employee_id"]))]},
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "TRIP_NOT_ACTIVE"
