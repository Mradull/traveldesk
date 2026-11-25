"""
test_intent_router.py (M2) - intent decides the tools BEFORE the LLM runs.
Weather-only never calls RAG; policy calls RAG; mixed; greetings; out of scope (incl. business
data and action requests); follow-up inheritance; embedding fallback.
"""
import pytest

from app.chat import chat_service, session_manager
from app.chat.intent_router import route
from app.schemas import ChatIntent, ToolName
from tests.conftest import tool_call

pytestmark = pytest.mark.usefixtures("vera_db")   # Vera fixtures: test DB, frozen today, fakes

W, P = ToolName.GET_WEATHER_FORECAST, ToolName.SEARCH_EXPENSE_POLICY


@pytest.mark.parametrize("message, intent, tools", [
    ("What will the weather be in Bengaluru from 23 to 26 November?", ChatIntent.WEATHER, [W]),
    ("Will it rain in Pune next week?", ChatIntent.WEATHER, [W]),
    ("What should I pack for Delhi?", ChatIntent.WEATHER, [W]),
    ("What is the meal limit?", ChatIntent.POLICY, [P]),
    ("How do I raise an expense ticket?", ChatIntent.POLICY, [P]),
    ("How do I check the status of my ticket?", ChatIntent.POLICY, [P]),       # how-to, not business data
    ("What is the hotel limit and will it rain in Mumbai?", ChatIntent.POLICY_AND_WEATHER, [P, W]),
    ("Hi Vera!", ChatIntent.GREETING, []),
    ("thank you", ChatIntent.GREETING, []),
    ("Thanks, bye!", ChatIntent.GREETING, []),                                  # several greeting words
    ("I am travelling to italy in first week of dec", ChatIntent.WEATHER, [W]),   # travel plan, no weather word
    ("Visiting Pune next month for a client meeting", ChatIntent.WEATHER, [W]),
    ("Can I claim a taxi when going to the airport?", ChatIntent.POLICY, [P]),     # policy words win
    ("Thanks for the meal limit info", ChatIntent.POLICY, [P]),                 # greeting + a real question
    ("Show my trips", ChatIntent.OUT_OF_SCOPE, []),
    ("What is the status of TKT-00003?", ChatIntent.OUT_OF_SCOPE, []),
    ("Can you approve my expense?", ChatIntent.OUT_OF_SCOPE, []),
    ("Book me a hotel in Goa", ChatIntent.OUT_OF_SCOPE, []),
    ("Who won the cricket match yesterday?", ChatIntent.OUT_OF_SCOPE, []),
])
def test_keyword_routing(message, intent, tools):
    decision = route(message)
    assert decision.intent == intent and decision.allowed_tools == tools


def test_business_and_action_reasons_pick_the_right_boundary():
    assert route("show my tickets").reason == "business_data"
    assert route("please approve my claim").reason == "action_request"


@pytest.mark.parametrize("follow_up", ["and on the 27th?", "from 2026-11-23 to 2026-11-26 please"])
def test_short_follow_up_inherits_previous_intent(follow_up):
    decision = route(follow_up, previous_intent=ChatIntent.WEATHER)
    assert decision.intent == ChatIntent.WEATHER and decision.reason.startswith("inherited")


def test_no_inheritance_without_a_previous_tool_turn():
    assert route("and on the 27th?", previous_intent=ChatIntent.GREETING).intent == ChatIntent.OUT_OF_SCOPE


def test_embedding_similarity_fallback():
    assert route("Is laundry covered on a long assignment?", policy_similarity=lambda _: 0.52).intent == ChatIntent.POLICY
    assert route("Is laundry covered on a long assignment?", policy_similarity=lambda _: 0.10).intent == ChatIntent.OUT_OF_SCOPE


def test_embedding_failure_is_ignored():
    def broken(_):
        raise RuntimeError("model down")
    assert route("Is laundry covered on a long assignment?", policy_similarity=broken).intent == ChatIntent.OUT_OF_SCOPE


# ----------------------------------------------------------------------------- through the chat service
def test_weather_only_message_never_runs_rag(employee, fake_llm, weather_api, monkeypatch, policy_index):
    from app.rag import retriever
    searched = []
    monkeypatch.setattr(retriever, "top_chunks", lambda q, top_k=None: searched.append(q) or [])
    model = fake_llm(tool_call("get_weather_forecast", {"destination": "Bengaluru", "start_date": "2026-11-23",
                                                        "end_date": "2026-11-26"}),
                     '{"weather_summary": "Rain with 19.4 °C to 27.8 °C.", '
                     '"travel_checklist": ["Carry an umbrella", "Check the forecast again", "Keep documents handy"], '
                     '"limitations": ["Forecasts can change."]}')
    s = session_manager.open_session(employee)
    reply = chat_service.handle_message(employee, s.session_id, "Weather in Bengaluru from 23 to 26 November?",
                                        "r", "c")
    assert reply.intent == ChatIntent.WEATHER
    assert searched == []                                       # RAG never ran
    assert model.calls[0][1] == ["get_weather_forecast"]        # only the weather tool was offered


def test_policy_message_always_retrieves_even_if_model_skips_the_tool(employee, fake_llm, policy_index):
    model = fake_llm("Meals are limited to 1,500.",                    # round 1: no tool call
                     "Meal lines above INR 1,500 need manager review [POL-6.2].")
    s = session_manager.open_session(employee)
    reply = chat_service.handle_message(employee, s.session_id, "What is the meal limit per line?", "r", "c")
    assert reply.intent == ChatIntent.POLICY
    assert [t.tool_name for t in reply.tools_used] == [ToolName.SEARCH_EXPENSE_POLICY]
    assert model.calls[0][1] == ["search_expense_policy"]
    assert [c.ref_id for c in reply.citations] == ["POL-6.2"]
