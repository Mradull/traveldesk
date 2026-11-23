"""
The three SQL demonstrations return the seed's expected totals.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0 > Testing strategy  (Required SQL demonstrations; Seed data; US-17)
"""

import pytest
from sqlalchemy import text

VIKRAM = {"employee_id": 1, "role": "MANAGER"}            # seed: Vikram Iyer is employee 1
ROHAN = {"employee_id": 3, "role": "EMPLOYEE"}            # seed: Rohan Mehta is employee 3


@pytest.fixture(autouse=True)
def _seed(seeded_test_database) -> None:
    """Every test here starts from the spec's seed data."""


def test_demo1_trip_expense_join(api_client, auth_header) -> None:
    rows = api_client.get("/api/v1/reports/trip-expenses", headers=auth_header(VIKRAM)).json()
    assert [(r["expense_code"], r["trip_code"], r["employee_name"], r["expense_type"], r["amount"], r["status"])
            for r in rows] == [
        ("EXP-00001", "TRP-00001", "Ananya Rao", "AIRFARE", 8500, "AUTO_APPROVED"),
        ("EXP-00002", "TRP-00001", "Ananya Rao", "LODGING", 6200, "AUTO_APPROVED"),
        ("EXP-00003", "TRP-00001", "Ananya Rao", "MEALS", 2400, "APPROVED"),
        ("EXP-00004", "TRP-00001", "Ananya Rao", "INCIDENTALS", 400, "APPROVED"),
        ("EXP-00005", "TRP-00002", "Rohan Mehta", "AIRFARE", 24500, "PENDING"),
        ("EXP-00006", "TRP-00002", "Rohan Mehta", "LODGING", 6000, "PENDING"),
        ("EXP-00007", "TRP-00002", "Rohan Mehta", "AIRFARE", 4200, "REJECTED"),
        ("EXP-00008", "TRP-00003", "Sara Thomas", "AIRFARE", 18000, "AUTO_APPROVED"),
    ]


def test_demo2_spend_by_trip_and_category_approved_only(api_client, auth_header) -> None:
    rows = api_client.get("/api/v1/reports/spend-by-trip-category", headers=auth_header(VIKRAM)).json()
    assert [(r["trip_code"], r["expense_type"], r["line_count"], r["total_amount"]) for r in rows] == [
        ("TRP-00001", "AIRFARE", 1, 8500),
        ("TRP-00001", "INCIDENTALS", 1, 400),
        ("TRP-00001", "LODGING", 1, 6200),
        ("TRP-00001", "MEALS", 1, 2400),
        ("TRP-00001", None, 4, 17500),                      # trip total row (GROUPING SETS)
        ("TRP-00003", "AIRFARE", 1, 18000),
        ("TRP-00003", None, 1, 18000),
    ]


def test_demo3_pending_flagged_lines(api_client, auth_header) -> None:
    rows = api_client.get("/api/v1/expenses/pending", headers=auth_header(VIKRAM)).json()
    assert [(r["expense_code"], r["ticket_code"], r["trip_code"], r["employee_name"], r["flag_codes"]) for r in rows] == [
        ("EXP-00005", "TKT-00003", "TRP-00002", "Rohan Mehta", ["OVER_THRESHOLD"])
    ]
    # ticket_id is the same id the manager's ticket queue uses, so the row can link to the review page.
    queue = api_client.get("/api/v1/tickets/pending", headers=auth_header(VIKRAM)).json()
    assert rows[0]["ticket_id"] == next(t["ticket_id"] for t in queue if t["ticket_code"] == "TKT-00003")


def test_seed_queues_for_the_manager(api_client, auth_header) -> None:
    """Demo preconditions: TKT-00003 pending; TRP-00004 waiting; TRP-00001 can be completed."""
    tickets = api_client.get("/api/v1/tickets/pending", headers=auth_header(VIKRAM)).json()
    assert [t["ticket_code"] for t in tickets] == ["TKT-00003"]
    trips = api_client.get("/api/v1/trips/pending", headers=auth_header(VIKRAM)).json()
    assert [t["trip_code"] for t in trips] == ["TRP-00004"]
    to_complete = api_client.get("/api/v1/trips/to-complete", headers=auth_header(VIKRAM)).json()
    assert [t["trip_code"] for t in to_complete] == ["TRP-00001"]


@pytest.mark.parametrize("url", ["/api/v1/reports/trip-expenses", "/api/v1/reports/spend-by-trip-category",
                                 "/api/v1/expenses/pending"])
def test_reports_are_manager_only(api_client, auth_header, url: str) -> None:
    response = api_client.get(url, headers=auth_header(ROHAN))
    assert response.status_code == 403 and response.json()["error"]["code"] == "FORBIDDEN"


# --- Employee dashboard: GET /dashboard/employee (team addition to Spec v2.0, M3 request) ---
def test_employee_dashboard_from_seed(api_client, auth_header) -> None:
    """Rohan: TRP-00002 Active, TRP-00004 In Progress; TKT-00003 pending 30,500; TKT-00004 rejected (not counted)."""
    body = api_client.get("/api/v1/dashboard/employee", headers=auth_header(ROHAN)).json()
    assert (body["total_trips"], body["open_trips"], body["pending_trip_approval"], body["total_claimed"]) == (
        2, 1, 1, 30500)
    assert [t["trip_code"] for t in body["recent_trips"]] == ["TRP-00004", "TRP-00002"]   # newest request first
    assert body["spend_by_category"] == [
        {"expense_type": "AIRFARE", "total_amount": 24500},
        {"expense_type": "LODGING", "total_amount": 6000},
    ]


def test_employee_dashboard_shows_newest_five_trips(api_client, auth_header, make_trip) -> None:
    for _ in range(4):                                     # TRP-00005..TRP-00008, requested today
        make_trip(ROHAN["employee_id"], state="IN_PROGRESS", created_offset=0)
    body = api_client.get("/api/v1/dashboard/employee", headers=auth_header(ROHAN)).json()
    assert (body["total_trips"], body["pending_trip_approval"]) == (6, 5)
    assert [t["trip_code"] for t in body["recent_trips"]] == [
        "TRP-00008", "TRP-00007", "TRP-00006", "TRP-00005", "TRP-00004"]


def test_employee_dashboard_with_no_trips_is_all_zero(api_client, auth_header, test_engine) -> None:
    with test_engine.begin() as db:                        # a new joiner: no trips, no tickets
        new_id = db.execute(text(
            "INSERT INTO employees (full_name, email, password_hash, department, role, manager_id) "
            "VALUES ('Kiran Das', 'kiran.das@veridian.example', 'not-used', 'Audit', 'EMPLOYEE', 1) "
            "RETURNING employee_id")).scalar_one()
    body = api_client.get("/api/v1/dashboard/employee",
                          headers=auth_header({"employee_id": new_id, "role": "EMPLOYEE"})).json()
    assert body == {"total_trips": 0, "open_trips": 0, "pending_trip_approval": 0, "total_claimed": 0,
                    "recent_trips": [], "spend_by_category": []}


def test_employee_dashboard_is_employee_only(api_client, auth_header) -> None:
    response = api_client.get("/api/v1/dashboard/employee", headers=auth_header(VIKRAM))
    assert response.status_code == 403 and response.json()["error"]["code"] == "FORBIDDEN"
