"""
End to end: trip -> approve -> ticket -> reject -> replacement -> complete; persistence; business works with AI/weather down.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0 > Testing strategy  (US-32; brief validation scenarios)
"""

from datetime import timedelta

from fastapi.testclient import TestClient

from app.core import database
from app.core.config import get_settings
from app.core.deps import get_db
from app.main import app
from app.schemas import today

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"


def upload_photo(client, headers: dict, marker: str) -> str:
    response = client.post("/api/v1/evidence", headers=headers,
                           files={"file": (f"{marker}.jpg", JPEG + marker.encode(), "image/jpeg")})
    assert response.status_code == 201, response.text
    return response.json()["evidence_id"]


def line(evidence_id: str, amount: str, expense_type: str = "MEALS") -> dict:
    return {"expense_type": expense_type, "amount": amount, "expense_date": today().isoformat(),
            "description": "Client meeting expense", "evidence_id": evidence_id}


def test_full_business_journey(api_client, team, auth_header) -> None:
    """Employee and manager walk the whole lifecycle through the API, as in the demo script."""
    rohan, vikram = auth_header(team["employee"]), auth_header(team["manager"])

    # 1. Rohan creates a trip that already started (so it can be completed today), then edits it.
    #    A start date in the past is not allowed, so the trip starts today and ends tomorrow.
    trip = api_client.post("/api/v1/trips", headers=rohan, json={
        "destination": "Hyderabad", "start_date": today().isoformat(),
        "end_date": (today() + timedelta(days=1)).isoformat(), "purpose": "Client workshop for FY27 audit planning",
    }).json()
    trip_id = trip["trip_id"]
    assert trip["status_label"] == "In Progress"
    edited = api_client.put(f"/api/v1/trips/{trip_id}", headers=rohan, json={
        "destination": "Hyderabad", "start_date": today().isoformat(),
        "end_date": (today() + timedelta(days=1)).isoformat(), "purpose": "Client workshop and audit planning",
    })
    assert edited.status_code == 200

    # 2. Vikram approves it.
    approved = api_client.post(f"/api/v1/trips/{trip_id}/decision", headers=vikram, json={"decision": "APPROVED"})
    assert approved.json()["status_label"] == "Approved - Active"

    # 3. Rohan raises a clean ticket (auto-approved) and a flagged one (pending).
    clean = api_client.post(f"/api/v1/trips/{trip_id}/tickets", headers=rohan,
                            json={"expenses": [line(upload_photo(api_client, rohan, "taxi"), "450", "GROUND_TRANSPORT")]})
    assert clean.json()["status"] == "AUTO_APPROVED"
    flagged = api_client.post(f"/api/v1/trips/{trip_id}/tickets", headers=rohan,
                              json={"expenses": [line(upload_photo(api_client, rohan, "dinner"), "1800")]}).json()
    assert flagged["status"] == "PENDING"

    # 4. Vikram sees it in his queue and rejects it with reason + comment.
    assert [t["ticket_id"] for t in api_client.get("/api/v1/tickets/pending", headers=vikram).json()] == [flagged["ticket_id"]]
    rejected = api_client.post(f"/api/v1/tickets/{flagged['ticket_id']}/decision", headers=vikram, json={
        "decision": "REJECTED", "rejection_reason": "INSUFFICIENT_EVIDENCE",
        "review_comment": "The bill is cut off; please attach the full itemised bill.",
    }).json()
    assert rejected["status"] == "REJECTED" and rejected["is_read_only"] is True

    # 5. Rohan raises a replacement with a new photo; the new ticket gets new ids.
    replacement = api_client.post(f"/api/v1/trips/{trip_id}/tickets", headers=rohan, json={
        "replacement_of_ticket_id": flagged["ticket_id"],
        "expenses": [line(upload_photo(api_client, rohan, "dinner-full-bill"), "1400")],
    }).json()
    assert replacement["replacement_of_ticket_code"] == flagged["ticket_code"]
    assert replacement["status"] == "AUTO_APPROVED"
    original = api_client.get(f"/api/v1/tickets/{flagged['ticket_id']}", headers=rohan).json()
    assert original["replaced_by_ticket_code"] == replacement["ticket_code"]

    # 6. Today is not yet the end date, so completion waits; tickets are still possible.
    early = api_client.post(f"/api/v1/trips/{trip_id}/complete", headers=vikram)
    assert early.status_code == 409 and early.json()["error"]["code"] == "TRIP_NOT_FINISHED"

    # 7. Spending summary shows the approved money only (450 + 1400) with a trip total row.
    rows = api_client.get("/api/v1/reports/spend-by-trip-category", headers=vikram).json()
    total_row = next(r for r in rows if r["trip_code"] == trip["trip_code"] and r["expense_type"] is None)
    assert total_row["total_amount"] == 1850

    # 8. My Trips card: three tickets, none pending, rejected money not counted.
    card = next(t for t in api_client.get("/api/v1/trips", headers=rohan).json() if t["trip_id"] == trip_id)
    assert (card["ticket_count"], card["pending_ticket_count"], card["total_claimed"]) == (3, 0, 1850)


def test_manager_completion_then_no_more_tickets(api_client, team, make_trip, auth_header) -> None:
    """Demo step 11: the manager completes a finished trip; a new ticket is then refused (409)."""
    rohan, vikram = auth_header(team["employee"]), auth_header(team["manager"])
    trip_id = make_trip(team["employee"]["employee_id"], start_offset=-20, end_offset=-17, created_offset=-30)
    assert api_client.post(f"/api/v1/trips/{trip_id}/complete", headers=vikram).status_code == 200
    refused = api_client.post(f"/api/v1/trips/{trip_id}/tickets", headers=rohan,
                              json={"expenses": [line(upload_photo(api_client, rohan, "late"), "300")]})
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "TRIP_NOT_ACTIVE"


def test_data_survives_a_backend_restart(api_client, team, auth_header) -> None:
    """Persistence: close every pooled connection and start a brand-new app client; the trip is
    still there because it lives in PostgreSQL, not in the backend's memory."""
    rohan = auth_header(team["employee"])
    trip = api_client.post("/api/v1/trips", headers=rohan, json={
        "destination": "Chennai", "start_date": (today() + timedelta(days=5)).isoformat(),
        "end_date": (today() + timedelta(days=7)).isoformat(), "purpose": "Quarterly client review meeting",
    }).json()

    for engine in database._engines.values():            # "restart": drop all open connections
        engine.dispose()
    database._engines.clear()
    get_settings.cache_clear()

    def override_get_db():
        with database.connection(use_test_database=True) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as fresh_client:
            again = fresh_client.get(f"/api/v1/trips/{trip['trip_id']}", headers=rohan)
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert again.status_code == 200 and again.json()["trip_code"] == trip["trip_code"]


def test_health_is_public_and_checks_the_database(api_client) -> None:
    """GET /health needs no token; status 'down' only when the database is unreachable."""
    body = api_client.get("/api/v1/health").json()
    database_check = next(dep for dep in body["dependencies"] if dep["name"] == "database")
    assert database_check["ok"] is True and body["status"] in ("ok", "degraded")


def test_health_reports_down_without_raising(api_client, monkeypatch) -> None:
    from app.routers import health

    def unreachable(*_args, **_kwargs):
        raise ConnectionError("database stopped")

    monkeypatch.setattr(health, "connection", unreachable)
    body = api_client.get("/api/v1/health").json()
    assert body["status"] == "down" and body["dependencies"][0]["detail"] == "ConnectionError"


def test_business_works_with_ai_and_weather_down(api_client, team, make_trip, auth_header, monkeypatch) -> None:
    """Brief: 'External API failures do not block core CRUD'. Point the AI and weather settings at
    nothing; trips, photos, tickets and decisions still work (business code never calls them)."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "invalid-key")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "http://127.0.0.1:9/unreachable")
    monkeypatch.setenv("WEATHER_FORECAST_URL", "http://127.0.0.1:9/unreachable")
    monkeypatch.setenv("WEATHER_GEOCODING_URL", "http://127.0.0.1:9/unreachable")
    get_settings.cache_clear()

    rohan, vikram = auth_header(team["employee"]), auth_header(team["manager"])
    created = api_client.post("/api/v1/trips", headers=rohan, json={
        "destination": "Kochi", "start_date": (today() + timedelta(days=2)).isoformat(),
        "end_date": (today() + timedelta(days=4)).isoformat(), "purpose": "Client onboarding workshop",
    })
    assert created.status_code == 201
    trip_id = make_trip(team["employee"]["employee_id"])
    ticket = api_client.post(f"/api/v1/trips/{trip_id}/tickets", headers=rohan,
                             json={"expenses": [line(upload_photo(api_client, rohan, "offline"), "2500")]})
    assert ticket.status_code == 201
    decided = api_client.post(f"/api/v1/tickets/{ticket.json()['ticket_id']}/decision", headers=vikram,
                              json={"decision": "APPROVED"})
    assert decided.status_code == 200
