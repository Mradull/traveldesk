"""
test_chat_session.py (M2) - session lifecycle through the real HTTP endpoints.
New session replaces the old one; close; idle expiry 410; closed 410; turn numbers; four message
types in order; another employee's session 404; manager 403; new session has no old memory;
history read-only; past chats list.
"""
import pytest

from app.chat import context_builder, memory
from app.schemas import ChatIntent
from tests.conftest import TODAY, rows, tool_call

pytestmark = pytest.mark.usefixtures("vera_db")   # Vera fixtures: test DB, frozen today, fakes

API = "/api/v1/chat"


def open_chat(client, headers) -> str:
    r = client.post(f"{API}/sessions", headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["session_id"]


def send(client, headers, sid, text):
    return client.post(f"{API}/sessions/{sid}/messages", headers=headers, json={"message": text})


def test_open_returns_intro_and_replaces_the_old_session(client, auth, employee):
    h = auth(employee)
    first = open_chat(client, h)
    r = client.post(f"{API}/sessions", headers=h)
    assert r.json()["intro_message"].startswith("Hi, I'm Vera") and r.json()["idle_timeout_minutes"] == 60
    old = rows("SELECT status, close_reason FROM chat_sessions WHERE session_id = :s", s=first)[0]
    assert old == {"status": "CLOSED", "close_reason": "REPLACED"}
    assert len(rows("SELECT 1 FROM chat_sessions WHERE status = 'ACTIVE'")) == 1


def test_close_then_message_gives_410_session_closed(client, auth, employee):
    h = auth(employee)
    sid = open_chat(client, h)
    r = client.post(f"{API}/sessions/{sid}/close", headers=h)
    assert r.status_code == 200 and r.json()["close_reason"] == "USER_CLOSED"
    r = send(client, h, sid, "hello")
    assert r.status_code == 410 and r.json()["error"]["code"] == "SESSION_CLOSED"


def test_idle_session_expires_with_410(client, auth, employee):
    h = auth(employee)
    sid = open_chat(client, h)
    rows("UPDATE chat_sessions SET last_activity_at = now() - interval '61 minutes' "
         "WHERE session_id = :s RETURNING 1", s=sid)
    r = send(client, h, sid, "hello")
    assert r.status_code == 410 and r.json()["error"]["code"] == "SESSION_EXPIRED"
    assert rows("SELECT status, close_reason FROM chat_sessions WHERE session_id = :s", s=sid)[0] == \
        {"status": "EXPIRED", "close_reason": "IDLE_TIMEOUT"}                  # committed before the 410


def test_scheduler_job_expires_idle_sessions(employee):
    from app.chat import session_manager
    from app.services import jobs
    sid = session_manager.open_session(employee).session_id
    rows("UPDATE chat_sessions SET last_activity_at = now() - interval '2 hours' WHERE session_id = :s RETURNING 1", s=sid)
    assert jobs.expire_idle_sessions() == 1


def test_turns_and_the_four_message_types_in_order(client, auth, employee, fake_llm, weather_api):
    h = auth(employee)
    sid = open_chat(client, h)
    fake_llm(tool_call("get_weather_forecast", {"destination": "Bengaluru", "start_date": "2026-11-23",
                                                "end_date": "2026-11-24"}),
             '{"weather_summary": "Rain, 19.4 °C to 27.8 °C, rain chance 70%.", '
             '"travel_checklist": ["Carry an umbrella", "Check the forecast again", "Keep documents handy"], '
             '"limitations": ["Forecasts can change."]}')
    assert send(client, h, sid, "hello").json()["turn_number"] == 1
    reply = send(client, h, sid, "Weather in Bengaluru on 23-24 Nov?").json()
    assert reply["turn_number"] == 2 and reply["weather"]["forecast_basis"]["coverage"] == "FULL"
    events = rows("""SELECT c.turn_number, m.sequence_no, m.message_type, m.tool_call_id FROM chat_messages m
                     JOIN chat_conversations c USING (conversation_id) ORDER BY c.turn_number, m.sequence_no""")
    assert [(e["turn_number"], e["message_type"]) for e in events] == [
        (1, "human_message"), (1, "ai_response"),
        (2, "human_message"), (2, "ai_tool_call"), (2, "tool_response"), (2, "ai_response")]
    assert events[3]["tool_call_id"] == events[4]["tool_call_id"] == "call-1"
    conv = rows("SELECT intent, status, correlation_id FROM chat_conversations ORDER BY turn_number")
    assert [c["intent"] for c in conv] == ["GREETING", "WEATHER"] and conv[1]["status"] == "COMPLETED"


def test_other_employees_session_is_404_and_manager_is_403(client, auth, employee, other_employee, manager):
    sid = open_chat(client, auth(employee))
    for path in (f"/sessions/{sid}/messages", f"/sessions/{sid}/close"):
        r = client.post(API + path, headers=auth(other_employee), json={"message": "hi"})
        assert r.status_code == 404
    assert client.get(f"{API}/sessions/{sid}/messages", headers=auth(other_employee)).status_code == 404
    r = client.post(f"{API}/sessions", headers=auth(manager))
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"
    assert client.post(f"{API}/sessions").status_code == 401


def test_new_session_starts_with_empty_memory(employee, fake_llm):
    from app.chat import chat_service, session_manager
    first = session_manager.open_session(employee).session_id
    fake_llm("Which dates are you travelling to Pune?")
    chat_service.handle_message(employee, first, "Weather in Pune?", "r", "c")
    assert memory.recent_turns(first, 2)                                  # turn 1 is remembered in its session
    second = session_manager.open_session(employee).session_id
    bundle = context_builder.build(memory.recent_turns(second, 1), None, "what should I pack?", [], TODAY)
    assert bundle.history == [] and "Pune" not in bundle.system_prompt


def test_follow_up_in_same_session_sees_earlier_turns(employee, fake_llm):
    from app.chat import chat_service, session_manager
    sid = session_manager.open_session(employee).session_id
    model = fake_llm("Which dates are you travelling to Pune?", "Thanks. Which end date?")
    chat_service.handle_message(employee, sid, "Weather in Pune?", "r", "c")
    reply = chat_service.handle_message(employee, sid, "from the 23rd", "r", "c")
    assert reply.intent == ChatIntent.WEATHER                              # inherited
    second_call_text = " ".join(str(m.content) for m in model.calls[1][0])
    assert "Weather in Pune?" in second_call_text                          # history of THIS session


def test_history_is_read_only_after_close_and_listed_in_past_chats(client, auth, employee):
    h = auth(employee)
    sid = open_chat(client, h)
    send(client, h, sid, "hello")
    assert client.get(f"{API}/sessions/{sid}/messages", headers=h).json()["read_only"] is False
    client.post(f"{API}/sessions/{sid}/close", headers=h)
    history = client.get(f"{API}/sessions/{sid}/messages", headers=h).json()
    assert history["read_only"] is True and [m["message_type"] for m in history["messages"]] == \
        ["human_message", "ai_response"]
    open_chat(client, h)                                                   # empty active chat: not listed
    past = client.get(f"{API}/sessions", headers=h).json()
    assert [p["session_id"] for p in past] == [sid] and past[0]["preview"] == "hello" and past[0]["turn_count"] == 1


def test_rate_limit_429(client, auth, employee, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "chat_rate_limit_per_minute", 2)
    h = auth(employee)
    sid = open_chat(client, h)
    codes = [send(client, h, sid, "hello").status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_message_length_is_validated(client, auth, employee):
    h = auth(employee)
    sid = open_chat(client, h)
    assert send(client, h, sid, "x" * 1001).status_code == 422
    assert send(client, h, sid, "").status_code == 422
