"""
Tickets only on Active trips; expense date before creation 422 on the right field; evidence 404/409; rollback; routing.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0 > Testing strategy
"""

from datetime import timedelta

import pytest
from sqlalchemy import text

from app.schemas import today


def line(evidence_id: str, **overrides) -> dict:
    """One expense line body; default: MEALS 800 (below the 1,500 threshold) dated today."""
    return {
        "expense_type": "MEALS",
        "amount": "800.00",
        "expense_date": today().isoformat(),
        "description": "Team lunch with client",
        "evidence_id": evidence_id,
        **overrides,
    }


def count(test_engine, table: str) -> int:
    with test_engine.connect() as db:
        return db.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()


def test_clean_ticket_is_auto_approved_by_system(api_client, team, make_trip, make_evidence, auth_header) -> None:
    rohan = team["employee"]
    trip_id = make_trip(rohan["employee_id"])
    photos = [make_evidence(rohan["employee_id"]) for _ in range(2)]

    response = api_client.post(
        f"/api/v1/trips/{trip_id}/tickets",
        headers=auth_header(rohan),
        json={"expenses": [line(photos[0]), line(photos[1], expense_type="LODGING", amount="5000")]},
    )
    assert response.status_code == 201
    ticket = response.json()
    assert ticket["ticket_code"].startswith("TKT-") and ticket["trip_id"] == trip_id
    assert (ticket["status"], ticket["routing"], ticket["flag_count"]) == ("AUTO_APPROVED", "AUTO", 0)
    assert ticket["total_amount"] == 5800 and ticket["is_read_only"] is True
    assert [e["expense_code"][:4] for e in ticket["expenses"]] == ["EXP-", "EXP-"]
    assert all(e["status"] == "AUTO_APPROVED" for e in ticket["expenses"])
    assert [(h["reviewer_type"], h["reviewer_name"], h["decision"]) for h in ticket["history"]] == [
        ("SYSTEM", "SYSTEM", "AUTO_APPROVED")
    ]


def test_flagged_ticket_waits_for_manager(api_client, team, make_trip, make_evidence, auth_header) -> None:
    rohan = team["employee"]
    trip_id = make_trip(rohan["employee_id"])
    response = api_client.post(
        f"/api/v1/trips/{trip_id}/tickets",
        headers=auth_header(rohan),
        json={"expenses": [line(make_evidence(rohan["employee_id"]), amount="1800")]},     # MEALS > 1,500
    )
    assert response.status_code == 201
    ticket = response.json()
    assert (ticket["status"], ticket["routing"], ticket["flag_count"], ticket["history"]) == (
        "PENDING", "MANAGER", 1, []
    )
    flag = ticket["expenses"][0]["flags"][0]
    assert flag["rule_code"] == "OVER_THRESHOLD" and flag["policy_ref"] == "[POL-6.2]"
    assert flag["message"] == "MEALS amount 1,800.00 is above the 1,500.00 review threshold"

    queue = api_client.get("/api/v1/tickets/pending", headers=auth_header(team["manager"])).json()
    assert [(t["ticket_id"], t["flag_codes"]) for t in queue] == [(ticket["ticket_id"], ["OVER_THRESHOLD"])]


def test_multiple_tickets_per_trip_and_trip_totals(api_client, team, make_trip, make_evidence, auth_header) -> None:
    rohan = team["employee"]
    trip_id = make_trip(rohan["employee_id"])
    for amount in ("800", "1800"):
        response = api_client.post(
            f"/api/v1/trips/{trip_id}/tickets", headers=auth_header(rohan),
            json={"expenses": [line(make_evidence(rohan["employee_id"]), amount=amount)]},
        )
        assert response.status_code == 201

    card = api_client.get("/api/v1/trips", headers=auth_header(rohan)).json()[0]
    assert (card["ticket_count"], card["pending_ticket_count"], card["total_claimed"]) == (2, 1, 2600)
    pending_only = api_client.get("/api/v1/tickets?status=PENDING", headers=auth_header(rohan)).json()
    assert [t["status"] for t in pending_only] == ["PENDING"]
    assert len(api_client.get(f"/api/v1/trips/{trip_id}/tickets", headers=auth_header(rohan)).json()) == 2
    assert len(api_client.get(f"/api/v1/trips/{trip_id}/expenses", headers=auth_header(rohan)).json()) == 2


@pytest.mark.parametrize("state", ["IN_PROGRESS", "REJECTED", "COMPLETED"])
def test_ticket_only_on_active_trip(api_client, team, make_trip, make_evidence, auth_header, test_engine, state) -> None:
    rohan = team["employee"]
    trip_id = make_trip(rohan["employee_id"], state=state)
    response = api_client.post(
        f"/api/v1/trips/{trip_id}/tickets", headers=auth_header(rohan),
        json={"expenses": [line(make_evidence(rohan["employee_id"]))]},
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "TRIP_NOT_ACTIVE"
    assert count(test_engine, "expense_tickets") == 0


def test_ticket_time_auto_complete_check(api_client, team, make_trip, make_evidence, auth_header, test_engine) -> None:
    """The scheduler has not run yet, but start + 90 days is reached: the ticket is refused and the
    trip is completed (AUTO) on the spot."""
    rohan = team["employee"]
    trip_id = make_trip(rohan["employee_id"], start_offset=-90, end_offset=-88, created_offset=-95)
    response = api_client.post(
        f"/api/v1/trips/{trip_id}/tickets", headers=auth_header(rohan),
        json={"expenses": [line(make_evidence(rohan["employee_id"]))]},
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "TRIP_NOT_ACTIVE"
    with test_engine.connect() as db:
        state = db.execute(
            text("SELECT trip_state, completion_type FROM travel_requests WHERE trip_id = :t"), {"t": trip_id}
        ).one()
    assert tuple(state) == ("COMPLETED", "AUTO")


def test_expense_date_before_trip_created_is_422_on_that_line(
    api_client, team, make_trip, make_evidence, auth_header, test_engine
) -> None:
    rohan = team["employee"]
    trip_id = make_trip(rohan["employee_id"], created_offset=-5)
    too_early = (today() - timedelta(days=6)).isoformat()
    response = api_client.post(
        f"/api/v1/trips/{trip_id}/tickets", headers=auth_header(rohan),
        json={"expenses": [line(make_evidence(rohan["employee_id"])),
                           line(make_evidence(rohan["employee_id"]), expense_date=too_early)]},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "EXPENSE_DATE_BEFORE_TRIP_CREATED"
    assert error["details"] == [
        {"field": "expenses.1.expense_date", "msg": f"Must be on or after {(today() - timedelta(days=5)).isoformat()}"}
    ]
    assert count(test_engine, "expense_tickets") == 0 and count(test_engine, "expenses") == 0   # nothing saved


def test_line_without_photo_is_refused(api_client, team, make_trip, auth_header) -> None:
    """The brief's 'missing receipt' scenario: refused with 422 (stricter than a flag)."""
    rohan = team["employee"]
    trip_id = make_trip(rohan["employee_id"])
    body = line("x")
    del body["evidence_id"]
    response = api_client.post(f"/api/v1/trips/{trip_id}/tickets", headers=auth_header(rohan), json={"expenses": [body]})
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "expenses.0.evidence_id"


def test_someone_elses_photo_is_404_and_reused_photo_is_409(
    api_client, team, make_trip, make_evidence, auth_header, test_engine
) -> None:
    rohan, sara = team["employee"], team["colleague"]
    trip_id = make_trip(rohan["employee_id"])
    url = f"/api/v1/trips/{trip_id}/tickets"

    saras_photo = make_evidence(sara["employee_id"])
    not_mine = api_client.post(url, headers=auth_header(rohan), json={"expenses": [line(saras_photo)]})
    assert not_mine.status_code == 404 and not_mine.json()["error"]["code"] == "EVIDENCE_NOT_FOUND"
    assert not_mine.json()["error"]["details"][0]["field"] == "expenses.0.evidence_id"

    photo = make_evidence(rohan["employee_id"])
    assert api_client.post(url, headers=auth_header(rohan), json={"expenses": [line(photo)]}).status_code == 201
    # Rollback: the first line is valid, the second reuses an attached photo -> nothing is saved.
    reused = api_client.post(
        url, headers=auth_header(rohan),
        json={"expenses": [line(make_evidence(rohan["employee_id"])), line(photo)]},
    )
    assert reused.status_code == 409 and reused.json()["error"]["code"] == "EVIDENCE_ALREADY_USED"
    assert count(test_engine, "expense_tickets") == 1 and count(test_engine, "expenses") == 1


def test_tickets_permissions(api_client, team, make_trip, make_evidence, auth_header) -> None:
    rohan = team["employee"]
    trip_id = make_trip(rohan["employee_id"])
    body = {"expenses": [line(make_evidence(rohan["employee_id"]))]}
    assert api_client.post(f"/api/v1/trips/{trip_id}/tickets", headers=auth_header(team["manager"]), json=body).status_code == 403
    assert api_client.post(f"/api/v1/trips/{trip_id}/tickets", headers=auth_header(team["colleague"]), json=body).status_code == 404

    ticket = api_client.post(f"/api/v1/trips/{trip_id}/tickets", headers=auth_header(rohan), json=body).json()
    url = f"/api/v1/tickets/{ticket['ticket_id']}"
    assert api_client.get(url, headers=auth_header(rohan)).status_code == 200
    assert api_client.get(url, headers=auth_header(team["manager"])).status_code == 200      # approving manager
    for stranger in ("colleague", "other_manager"):
        assert api_client.get(url, headers=auth_header(team[stranger])).status_code == 404
    expense_url = f"/api/v1/expenses/{ticket['expenses'][0]['expense_id']}"
    assert api_client.get(expense_url, headers=auth_header(team["colleague"])).status_code == 404
    assert api_client.get(expense_url, headers=auth_header(rohan)).json()["evidence_code"].startswith("EVD-")


def test_policy_check_rerun_is_read_only(api_client, team, make_trip, make_evidence, auth_header) -> None:
    rohan = team["employee"]
    trip_id = make_trip(rohan["employee_id"])
    ticket = api_client.post(
        f"/api/v1/trips/{trip_id}/tickets", headers=auth_header(rohan),
        json={"expenses": [line(make_evidence(rohan["employee_id"]), expense_type="AIRFARE", amount="24500")]},
    ).json()
    expense_id = ticket["expenses"][0]["expense_id"]
    check = api_client.get(f"/api/v1/expenses/{expense_id}/policy-check", headers=auth_header(team["manager"]))
    assert check.status_code == 200
    body = check.json()
    assert [f["rule_code"] for f in body["flags"]] == ["OVER_THRESHOLD"]
    assert body["requires_manager_review"] is True and body["rules_version"] == "VGS-FIN-TE-001 v2.0"
    again = api_client.get(f"/api/v1/tickets/{ticket['ticket_id']}", headers=auth_header(rohan)).json()
    assert again["status"] == "PENDING"                                          # nothing changed


def test_policy_rules_endpoint(api_client, team, auth_header) -> None:
    rules = api_client.get("/api/v1/policy/rules", headers=auth_header(team["employee"])).json()
    assert rules["review_thresholds_inr"] == {
        "AIRFARE": 20000, "LODGING": 7500, "MEALS": 1500, "GROUND_TRANSPORT": 3000, "INCIDENTALS": 1000
    }
    assert rules["hard_cap_per_line_inr"] == 200000 and rules["evidence_max_bytes"] == 5242880
    assert api_client.get("/api/v1/policy/rules").status_code == 401
