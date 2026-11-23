"""
test_vera_grounding.py (M2) - with the fake LLM: weather numbers and conditions must match the
tool output, packing advice must be traceable, invalid citations are removed, and a RAG failure
never produces an uncited rule.
"""
import json
from datetime import timedelta

import pytest

from app.ai import output_validators as ov
from app.chat import chat_service, formatter, session_manager
from app.rag import retriever
from app.schemas import (ConversationStatus, DailyForecast, ErrorCode, GuardrailStatus, RetrievedChunk,
                         WeatherForecastResult, WeatherStatus)
from tests.conftest import TODAY, tool_call

pytestmark = pytest.mark.usefixtures("vera_db")   # Vera fixtures: test DB, frozen today, fakes


def forecast(**day) -> WeatherForecastResult:
    d = dict(date=TODAY + timedelta(days=3), weather_code=61, condition="Rain", temp_min_c=19.4, temp_max_c=27.8,
             precipitation_probability_max_pct=70, precipitation_sum_mm=4.2, wind_speed_max_kmh=14.0)
    d.update(day)
    return WeatherForecastResult(status=WeatherStatus.AVAILABLE, destination="Bengaluru",
                                 resolved_location="Bengaluru, Karnataka, India", requested_from=d["date"],
                                 requested_to=d["date"], covered_dates=[d["date"]], days=[DailyForecast(**d)],
                                 retrieved_at="2026-11-20T05:00:00Z")


# ----------------------------------------------------------------------------- O1 unit checks
def test_grounded_numbers_pass_and_invented_ones_fail():
    facts = ov.weather_facts([forecast()])
    assert ov.check_weather_grounding("Between 19.4 °C and 27.8°C, 70% chance of rain, 4.2 mm, wind 14 km/h.", facts) == []
    assert ov.check_weather_grounding("Highs of 31 °C and 90% rain.", facts) == [
        "number 31 °C not in forecast", "number 90% not in forecast"]


def test_condition_words_must_match_the_data():
    dry = ov.weather_facts([forecast(weather_code=1, precipitation_probability_max_pct=0, precipitation_sum_mm=0.0)])
    assert ov.check_weather_grounding("Expect thunderstorms and fog.", dry)
    assert ov.check_weather_grounding("No rain is expected.", dry) == []              # negation is fine
    assert ov.check_weather_grounding("Carry an umbrella.", dry) == ["'umbrella' not supported by forecast"]


@pytest.mark.parametrize("advice, ok", [
    ("Carry an umbrella", True),          # rain 70% -> umbrella is traceable
    ("Pack warm layers", False),          # min 19.4 C is not cold
    ("Use sun protection", False),        # max 27.8 C is not hot
    ("Secure loose items", False),        # wind 14 km/h is not strong
])
def test_packing_advice_is_traceable(advice, ok):
    assert (ov.check_weather_grounding(advice, ov.weather_facts([forecast()])) == []) is ok


def test_out_of_range_allows_no_numbers():
    facts = ov.weather_facts([])
    assert ov.check_weather_grounding("Probably around 30 °C.", facts)


def test_template_is_always_grounded():
    for f in (forecast(), forecast(temp_min_c=9.0, temp_max_c=33.5, wind_speed_max_kmh=45.0, weather_code=95)):
        t = formatter.template_weather_output(f)
        text = " ".join([t.weather_summary, *t.travel_checklist, *t.limitations])
        assert ov.check_weather_grounding(text, ov.weather_facts([f])) == [], text
        assert 3 <= len(t.travel_checklist) <= 5


# ----------------------------------------------------------------------------- O2 unit checks
CHUNK = RetrievedChunk(chunk_id=1, ref_id="POL-6.2", section_title="Review thresholds per expense line",
                       content="MEALS 1,500 ... LODGING 7,500", similarity=0.8)


def test_citations_must_be_retrieved_and_amounts_must_exist():
    assert ov.check_citations("Meals above INR 1,500 need review [POL-6.2].", [CHUNK]).ok
    bad = ov.check_citations("Meals above INR 2,000 need review [POL-6.2][POL-9.9].", [CHUNK])
    assert bad.invalid == ["POL-9.9"] and bad.bad_amounts == ["INR 2,000"]
    assert ov.remove_citations("Rule [POL-6.2][POL-9.9].", ["POL-9.9"]) == "Rule [POL-6.2]."


# ----------------------------------------------------------------------------- end to end, fake LLM
WEATHER_CALL = tool_call("get_weather_forecast", {"destination": "Bengaluru", "start_date": "2026-11-23",
                                                  "end_date": "2026-11-23"})


def card(summary: str, checklist=("Carry an umbrella", "Check the forecast again", "Keep documents handy")) -> str:
    return json.dumps({"weather_summary": summary, "travel_checklist": list(checklist),
                       "limitations": ["Forecasts can change."]})


def test_ungrounded_weather_card_is_regenerated_then_replaced_by_template(employee, fake_llm, weather_api):
    model = fake_llm(WEATHER_CALL, card("Sunny and 35 °C."), card("Still 35 °C and sunny."))
    sid = session_manager.open_session(employee).session_id
    reply = chat_service.handle_message(employee, sid, "Weather in Bengaluru on 23 Nov?", "r", "c")
    assert len(model.calls) == 3                                    # tool round + card + one regeneration
    assert reply.guardrail_status == GuardrailStatus.OUTPUT_REWRITTEN
    assert "35" not in reply.reply and "19.4 °C" in reply.reply     # template built from the data
    assert ov.check_weather_grounding(reply.reply, ov.weather_facts([forecast()])) == []


def test_grounded_card_is_used_with_code_built_forecast_basis(employee, fake_llm, weather_api):
    fake_llm(WEATHER_CALL, card("Rain likely (70%), 19.4 °C to 27.8 °C."))
    sid = session_manager.open_session(employee).session_id
    reply = chat_service.handle_message(employee, sid, "Weather in Bengaluru on 23 Nov?", "r", "c")
    assert reply.guardrail_status == GuardrailStatus.PASSED
    assert reply.weather.weather_summary == "Rain likely (70%), 19.4 °C to 27.8 °C."
    # the chat reply is the whole answer: summary + packing tips + closing note
    assert reply.reply.startswith("Rain likely (70%), 19.4 °C to 27.8 °C.\n\nWhat to pack:\n• Carry an umbrella")
    assert reply.reply.endswith("check again a day before you travel.")
    # limitations are built by code from the facts, not written by the model
    assert reply.weather.limitations[0].startswith("Forecast from Open-Meteo, retrieved")
    # the card's daily table is the tool result copied exactly (never written by the model)
    day = reply.weather.days[0]
    assert (day.date.isoformat(), day.condition, day.temp_min_c, day.temp_max_c,
            day.precipitation_probability_max_pct, day.precipitation_sum_mm, day.wind_speed_max_kmh) == \
        ("2026-11-23", "Rain", 19.4, 27.8, 70, 4.2, 14.0)
    basis = reply.weather.forecast_basis
    assert basis.source == "Open-Meteo" and basis.resolved_location == "Bengaluru, Karnataka, India"


def test_out_of_range_reply_has_no_values(employee, fake_llm, weather_api):
    fake_llm(tool_call("get_weather_forecast", {"destination": "Bengaluru", "start_date": "2026-12-30",
                                                "end_date": "2027-01-03"}))
    sid = session_manager.open_session(employee).session_id
    reply = chat_service.handle_message(employee, sid, "Weather in Bengaluru 30 Dec to 3 Jan?", "r", "c")
    assert reply.reply.startswith("Forecast not available") and not ov.NUMBER_WITH_UNIT.search(reply.reply)
    assert reply.weather.forecast_basis.coverage == "NONE" and reply.status == ConversationStatus.COMPLETED
    assert reply.weather.days == []                                     # out of range: no daily values


def test_weather_provider_failure_gives_safe_retryable_reply(employee, fake_llm, weather_api):
    import httpx
    weather_api["forecast"].mock(side_effect=httpx.TimeoutException("slow"))
    fake_llm(WEATHER_CALL)
    sid = session_manager.open_session(employee).session_id
    reply = chat_service.handle_message(employee, sid, "Weather in Bengaluru on 23 Nov?", "r", "c")
    assert reply.status == ConversationStatus.FAILED and reply.error_code == ErrorCode.WEATHER_TIMEOUT
    assert reply.retryable and reply.weather is None and "°" not in reply.reply


def test_invalid_citation_is_regenerated_and_valid_ones_kept(employee, fake_llm, policy_index):
    fake_llm("", "Meals over INR 1,500 need review [POL-99.1].",
             "Meals over INR 1,500 need review [POL-6.2].")
    sid = session_manager.open_session(employee).session_id
    reply = chat_service.handle_message(employee, sid, "What is the meal limit per line?", "r", "c")
    assert "[POL-6.2]" in reply.reply and "POL-99.1" not in reply.reply
    assert [c.ref_id for c in reply.citations] == ["POL-6.2"]


def test_still_invalid_after_retry_gives_policy_unavailable(employee, fake_llm, policy_index):
    fake_llm("", "Meals over INR 9,999 are fine [POL-99.1].", "Meals over INR 9,999 are fine.")
    sid = session_manager.open_session(employee).session_id
    reply = chat_service.handle_message(employee, sid, "What is the meal limit per line?", "r", "c")
    assert reply.reply.startswith("Policy information is temporarily unavailable") and reply.citations == []


def test_rag_failure_never_gives_an_uncited_rule(employee, fake_llm, monkeypatch):
    def down(query, top_k=None):
        raise retriever.RetrievalError("embeddings down")
    monkeypatch.setattr(retriever, "top_chunks", down)
    model = fake_llm("Meals are limited to INR 1,500.")                # model tries to answer from memory
    sid = session_manager.open_session(employee).session_id
    reply = chat_service.handle_message(employee, sid, "What is the meal limit?", "r", "c")
    assert reply.error_code == ErrorCode.POLICY_RETRIEVAL_FAILED and reply.status == ConversationStatus.FAILED
    assert "1,500" not in reply.reply and "temporarily unavailable" in reply.reply
    assert len(model.calls) == 1                                        # no answer call without chunks


def test_no_match_says_not_in_policy(employee, fake_llm, policy_index, monkeypatch):
    monkeypatch.setattr(retriever, "top_chunks", lambda q, top_k=None: [CHUNK.model_copy(update={"similarity": 0.1})])
    fake_llm("")
    sid = session_manager.open_session(employee).session_id
    reply = chat_service.handle_message(employee, sid, "What is the policy on pets?", "r", "c")
    assert "couldn't find this in the expense policy" in reply.reply and "finance.ops@" in reply.reply


def test_follow_up_packing_advice_uses_this_sessions_forecast(employee, fake_llm, weather_api):
    fake_llm(WEATHER_CALL, card("Rain likely (70%), 19.4 °C to 27.8 °C."),
             "Pack warm layers, it will be 5 °C.",                       # ungrounded follow-up
             "Pack warm layers, it will be 5 °C.")                       # still ungrounded after retry
    sid = session_manager.open_session(employee).session_id
    chat_service.handle_message(employee, sid, "Weather in Bengaluru on 23 Nov?", "r", "c")
    reply = chat_service.handle_message(employee, sid, "What should I pack?", "r", "c")
    assert "5 °C" not in reply.reply and "umbrella" in reply.reply.lower()   # template from the earlier forecast
    assert reply.guardrail_status == GuardrailStatus.OUTPUT_REWRITTEN


def test_promises_are_replaced_with_the_boundary(employee, fake_llm, policy_index):
    fake_llm("", "Your expense will be approved, I guarantee it. Meals over INR 1,500 need review [POL-6.2].")
    sid = session_manager.open_session(employee).session_id
    reply = chat_service.handle_message(employee, sid, "What is the meal limit per line?", "r", "c")
    assert "guarantee" not in reply.reply and "can't approve" in reply.reply and "[POL-6.2]" in reply.reply


def test_reply_answers_weather_and_packing_in_one_message(employee, fake_llm, weather_api):
    """'Weather in Pune 23-27 Nov and what should I pack?' -> summary + tips + note, all grounded."""
    import httpx
    from tests.conftest import forecast_json
    weather_api["forecast"].mock(return_value=httpx.Response(200, json=forecast_json(
        TODAY + timedelta(days=3), 5, weather_code=[2] * 5, temperature_2m_min=[18.5, 19.6, 19.4, 19.7, 20.0],
        temperature_2m_max=[31.0, 31.4, 31.7, 31.9, 32.9], precipitation_probability_max=[0] * 5,
        precipitation_sum=[0.0] * 5, wind_speed_10m_max=[10.2, 11.0, 8.6, 11.7, 7.7])))
    fake_llm(tool_call("get_weather_forecast", {"destination": "Pune", "start_date": "2026-11-23",
                                                "end_date": "2026-11-27"}),
             card("Pune looks dry and warm for your trip: partly cloudy, 18.5 °C at night to 32.9 °C by day, "
                  "with no rain expected.", ("Light cotton clothes - highs up to 32.9 °C",
                                             "A refillable water bottle", "Sun protection for the afternoons")))
    sid = session_manager.open_session(employee).session_id
    reply = chat_service.handle_message(employee, sid, "I am travelling to Pune from 23 nov to 27 nov, "
                                        "tell me what will be the weather and what should I pack", "r", "c")
    assert reply.guardrail_status == GuardrailStatus.PASSED
    assert "What to pack:" in reply.reply and "Light cotton clothes" in reply.reply
    assert "23 Nov" not in reply.reply.split("What to pack:")[0]        # no day-by-day dump


def test_fallback_tips_state_their_reason_from_the_data():
    """Template tips name the condition and its value, e.g. strong wind -> 'Strong wind up to 52.3 km/h ...'."""
    windy = forecast(weather_code=3, precipitation_probability_max_pct=0, precipitation_sum_mm=0.0,
                     temp_min_c=9.0, temp_max_c=33.0, wind_speed_max_kmh=52.3)
    tips = formatter.template_weather_output(windy).travel_checklist
    assert "Strong wind up to 52.3 km/h - secure loose items and check transport updates" in tips
    assert "Warm layers - lows down to 9.0 °C" in tips
    assert "Light clothing, water and sun protection - highs up to 33.0 °C" in tips
    assert not any("umbrella" in t.lower() for t in tips)                       # dry: no rain advice
    assert ov.check_weather_grounding(" ".join(tips), ov.weather_facts([windy])) == []
