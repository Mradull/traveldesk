"""
test_vera_isolation.py (M2) - Vera has no code path to business data.
1. Every module under app/chat, app/rag, app/ai (and weather_service) may import only the
   allowed modules; any trip/ticket/expense/evidence/approval/employee repository or service fails.
2. The two tool schemas contain no id fields and nothing but their documented arguments.
3. The LLM never receives session/employee ids, and business-data questions never reach it.
"""
import ast
from pathlib import Path

import pytest

from app.chat import chat_service, session_manager, tools
from tests.conftest import tool_call

pytestmark = pytest.mark.usefixtures("vera_db")   # Vera fixtures: test DB, frozen today, fakes

APP = Path(__file__).resolve().parents[1] / "app"
VERA_CODE = [*(APP / "chat").glob("*.py"), *(APP / "rag").glob("*.py"), *(APP / "ai").glob("*.py"),
             APP / "services" / "weather_service.py"]
ALLOWED_PREFIXES = ("app.schemas", "app.core", "app.ai", "app.rag", "app.chat",
                    "app.repositories.chat_repo", "app.repositories.log_repo", "app.repositories.policy_chunk_repo",
                    "app.services.weather_service")
ALLOWED_NAMES = {"app": {"schemas"}, "app.repositories": {"chat_repo", "log_repo", "policy_chunk_repo"},
                 "app.services": {"weather_service"}}


def app_imports(path: Path) -> list[str]:
    """Every 'app...' module a file imports, as dotted names (from-imports include the name)."""
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.startswith("app")]
        elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("app"):
            if node.module in ALLOWED_NAMES:
                found += [f"{node.module}.{a.name}" for a in node.names]
            else:
                found.append(node.module)
    return found


@pytest.mark.parametrize("path", VERA_CODE, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_vera_code_imports_no_business_module(path):
    bad = [m for m in app_imports(path) if not m.startswith(ALLOWED_PREFIXES)]
    assert bad == [], f"{path.name} imports business code: {bad}"


def test_the_scan_really_catches_a_business_import(tmp_path):
    f = tmp_path / "x.py"
    f.write_text("from app.repositories import trip_repo\nimport app.services.ticket_service\n")
    assert [m for m in app_imports(f) if not m.startswith(ALLOWED_PREFIXES)] == [
        "app.repositories.trip_repo", "app.services.ticket_service"]


def test_tool_schemas_have_no_id_fields():
    fields = {name: set(t.args) for name, t in tools.TOOLS_BY_NAME.items()}
    assert fields == {"search_expense_policy": {"query"},
                      "get_weather_forecast": {"destination", "start_date", "end_date"}}
    for names in fields.values():
        assert not any("id" in n.split("_") or n.startswith(("trip", "ticket", "expense", "employee")) for n in names)


def test_llm_never_receives_ids(employee, fake_llm, weather_api):
    model = fake_llm(tool_call("get_weather_forecast", {"destination": "Bengaluru", "start_date": "2026-11-23",
                                                        "end_date": "2026-11-23"}),
                     '{"weather_summary": "Rain, 19.4 °C to 27.8 °C.", "travel_checklist": '
                     '["Carry an umbrella", "Check again", "Keep documents handy"], "limitations": ["Can change."]}')
    sid = session_manager.open_session(employee).session_id
    chat_service.handle_message(employee, sid, "Weather in Bengaluru on 23 Nov?", "r", "corr-iso")
    sent = " ".join(str(m.content) for messages, _ in model.calls for m in messages)
    for secret in (str(sid), "corr-iso", "employee_id", "session_id", "Rohan", "rohan.mehta"):
        assert secret not in sent


@pytest.mark.parametrize("message", ["Show my trips", "What is the status of TKT-00003?"])
def test_business_data_questions_get_a_boundary_and_no_llm_call(employee, fake_llm, message):
    model = fake_llm()
    sid = session_manager.open_session(employee).session_id
    reply = chat_service.handle_message(employee, sid, message, "r", "c")
    assert "can't see your trips" in reply.reply and model.calls == [] and reply.tools_used == []
