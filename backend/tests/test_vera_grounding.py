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


# ----------------------------------------------------------------------------- follow-up questions (memory evals)
GROUND = RetrievedChunk(chunk_id=7, ref_id="POL-6.2", section_title="Review thresholds per expense line",
                        content="AIRFARE 20,000 ... GROUND TRANSPORT 3,000 ... MEALS 1,500", similarity=0.81)


def _topic_aware_search(monkeypatch):
    """Fake retriever: a bare follow-up matches nothing; with the previous question it finds POL-6.2."""
    searched = []

    def top_chunks(query, top_k=None):
        searched.append(query)
        return [GROUND] if "airfare" in query.lower() else [GROUND.model_copy(update={"similarity": 0.12})]
    monkeypatch.setattr(retriever, "top_chunks", top_chunks)
    return searched


def test_inherited_follow_up_searches_with_the_previous_question(employee, fake_llm, monkeypatch):
    searched = _topic_aware_search(monkeypatch)
    fake_llm("", "Airfare lines above INR 20,000 need manager review [POL-6.2].",        # turn 1
             "", "Ground transport lines above INR 3,000 need manager review [POL-6.2].")  # turn 2
    sid = session_manager.open_session(employee).session_id
    chat_service.handle_message(employee, sid, "What is the review threshold for airfare?", "r", "c")
    reply = chat_service.handle_message(employee, sid, "What about ground transport?", "r", "c")
    assert searched[-1].startswith("What is the review threshold for airfare? What about ground transport?")
    assert "3,000" in reply.reply and [c.ref_id for c in reply.citations] == ["POL-6.2"]


def test_follow_up_with_no_match_is_retried_with_the_previous_question(employee, fake_llm, monkeypatch):
    searched = _topic_aware_search(monkeypatch)
    fake_llm("", "Airfare lines above INR 20,000 need manager review [POL-6.2].",
             tool_call("search_expense_policy", {"query": "ground transport"}),          # model's own weak query
             "Ground transport lines above INR 3,000 need manager review [POL-6.2].")
    sid = session_manager.open_session(employee).session_id
    chat_service.handle_message(employee, sid, "What is the review threshold for airfare?", "r", "c")
    reply = chat_service.handle_message(employee, sid, "And for ground transport?", "r", "c")
    assert searched[-2:] == ["ground transport",
                             "What is the review threshold for airfare? And for ground transport?"]
    assert "3,000" in reply.reply and "couldn't find" not in reply.reply
    assert [t.tool_name.value for t in reply.tools_used] == ["search_expense_policy", "search_expense_policy"]



def test_claim_question_also_searches_the_procedure(employee, fake_llm, monkeypatch):
    """'What should I do to get reimbursed for a meal?' -> searches the steps (raise a ticket, receipt photo) too."""
    searched = []

    def top_chunks(query, top_k=None):
        searched.append(query)
        return [RetrievedChunk(chunk_id=1, ref_id="GUIDE-6", section_title="Raising an expense ticket",
                               content="Open Expense Management, choose the trip, add a line, attach the receipt photo, submit.",
                               similarity=0.8),
                RetrievedChunk(chunk_id=2, ref_id="POL-6.2", section_title="Review thresholds per expense line",
                               content="MEALS 1,500", similarity=0.7)]
    monkeypatch.setattr(retriever, "top_chunks", top_chunks)
    fake_llm("", "1. Keep the receipt and take a photo. 2. In Expense Management raise a ticket on the trip [GUIDE-6]. "
                 "Meals above INR 1,500 go to your manager [POL-6.2].")
    sid = session_manager.open_session(employee).session_id
    reply = chat_service.handle_message(employee, sid, "If I eat in Rome, what should I do to get reimbursed?", "r", "c")
    assert chat_service.PROCEDURE_QUERY in searched
    assert {c.ref_id for c in reply.citations} == {"GUIDE-6", "POL-6.2"}


# ----------------------------------------------------------------------------- several destinations in one message
def _geocode_any(weather_api, places):
    import httpx

    def geocode(request):
        name, admin1, country = places[request.url.params["name"]]
        return httpx.Response(200, json={"results": [{"name": name, "admin1": admin1, "country": country,
                                                      "latitude": 20.0, "longitude": 77.0, "population": 5000000}]})
    weather_api["geo"].mock(side_effect=geocode)


def test_single_destination_makes_no_extra_round(employee, fake_llm, weather_api):
    model = fake_llm(tool_call("get_weather_forecast", {"destination": "Bengaluru", "start_date": "2026-11-23",
                                                        "end_date": "2026-11-26"}),
                     card("Rain likely (70%), 19.4 °C to 27.8 °C."))
    sid = session_manager.open_session(employee).session_id
    chat_service.handle_message(employee, sid, "Weather in Bengaluru from 23rd to 26th?", "r", "c")
    assert len(model.calls) == 2                                         # tool round + card, nothing extra


def test_fallback_reads_naturally_with_condition_tips():
    """Fallback text: compact dates, fog day named, tips from the conditions (no filler when not needed)."""
    from datetime import date
    f = forecast(date=TODAY + timedelta(days=18), weather_code=45, condition="Fog", temp_min_c=21.8, temp_max_c=28.4,
                 precipitation_probability_max_pct=0, precipitation_sum_mm=0.0, wind_speed_max_kmh=13.0)
    out = formatter.template_weather_output(f)
    assert out.weather_summary.startswith("Bengaluru, Karnataka, India (8 Dec 2026): fog.")
    assert "Light, breathable clothing - highs up to 28.4 °C" in out.travel_checklist
    assert "Allow extra travel time on 8 Dec - fog expected" in out.travel_checklist
    assert formatter._date_list([date(2026, 12, 8), date(2026, 12, 9)]) == "8–9 Dec 2026"
    assert formatter._date_list([date(2026, 11, 30), date(2026, 12, 1)]) == "30 Nov 2026 to 1 Dec 2026"


def test_slow_ai_text_never_holds_the_reply_back(employee, fake_llm, weather_api, monkeypatch):
    """Weather texts are written in parallel within a time budget; a city whose AI text is late gets
    the grounded fallback text, so the reply still arrives quickly."""
    import time as _time
    monkeypatch.setattr(chat_service, "WEATHER_CARDS_BUDGET_SECONDS", 0.3)
    def slow_card(forecast, question, ctx, out):
        _time.sleep(3)                                                   # a stalled free-tier call
        return formatter.template_weather_output(forecast)               # (no AI or logging: nothing left behind)
    monkeypatch.setattr(chat_service, "_weather_card", slow_card)
    fake_llm(WEATHER_CALL)
    sid = session_manager.open_session(employee).session_id
    started = _time.monotonic()
    reply = chat_service.handle_message(employee, sid, "Weather in Bengaluru on 23 Nov?", "r", "c")
    assert _time.monotonic() - started < 2                              # not 3 s: the budget cut it off
    assert reply.reply.startswith("Bengaluru, Karnataka, India (23 Nov 2026)")   # grounded fallback text
    assert reply.weather is not None and reply.weather.days
    assert reply.guardrail_status == GuardrailStatus.OUTPUT_REWRITTEN


# ----------------------------------------------------------------------------- rain gear + per-city texts
@pytest.mark.parametrize("pct, mm, code, advice_allowed", [
    (0, 0.0, 2, False),     # "umbrella - rain chance 0% but carry anyway": rejected
    (2, 0.0, 0, False),     # 2% is not a reason for rain gear
    (14, 0.6, 53, True),    # drizzle with rain in mm: rain gear makes sense
    (23, 0.0, 2, True),     # 20% or more: rain gear makes sense
])
def test_rain_gear_advice_needs_a_real_rain_risk(pct, mm, code, advice_allowed):
    facts = ov.weather_facts([forecast(precipitation_probability_max_pct=pct, precipitation_sum_mm=mm, weather_code=code)])
    problems = ov.check_weather_grounding(f"Umbrella or raincoat - rain chance up to {pct}%", facts)
    assert (problems == []) is advice_allowed
    assert ov.check_weather_grounding(f"Mostly dry, with a {pct}% chance of rain.", facts) == []   # honest mention ok


def test_fallback_suggests_no_umbrella_for_a_small_rain_chance():
    f = forecast(weather_code=0, precipitation_probability_max_pct=2, precipitation_sum_mm=0.0)
    assert not any("umbrella" in t.lower() for t in formatter.template_weather_output(f).travel_checklist)


def test_comma_date_lists_count_as_trip_legs():
    msg = "I will be in delhi on 1,2,3 dec, then in mumbai on 4,5 dec, then in blr on 6, 7 dec and chennai on 8 and 9 dec"
    assert chat_service._expected_destinations(msg) == 4



# ----------------------------------------------------------------------------- several places: ONE trip answer
def _trip_json(cities, checklist=("Light, breathable clothes for Delhi and Mumbai", "Umbrella or raincoat for Delhi and Mumbai",
                                  "Comfortable shoes for meetings")):
    return json.dumps({"overview": "Wet in both places, mild temperatures.",
                       "cities": [{"place": c, "summary": f"Rain likely (70%), 19.4 °C to 27.8 °C in {c}."} for c in cities],
                       "travel_checklist": list(checklist)})


def _two_city_turn(employee, fake_llm, weather_api, *trip_replies):
    from langchain_core.messages import AIMessage
    _geocode_any(weather_api, {"Delhi": ("Delhi", "Delhi", "India"), "Mumbai": ("Mumbai", "Maharashtra", "India")})
    both = AIMessage(content="", tool_calls=[
        {"name": "get_weather_forecast", "args": {"destination": "Delhi", "start_date": "2026-11-22",
                                                  "end_date": "2026-11-24"}, "id": "c-d"},
        {"name": "get_weather_forecast", "args": {"destination": "Mumbai", "start_date": "2026-11-25",
                                                  "end_date": "2026-11-26"}, "id": "c-m"}])
    model = fake_llm(both, *trip_replies)
    sid = session_manager.open_session(employee).session_id
    reply = chat_service.handle_message(employee, sid, "Delhi 22nd to 24th, Mumbai 25th to 26th - what to pack?", "r", "c")
    return model, reply


def test_several_places_give_one_well_formatted_answer(employee, fake_llm, weather_api):
    """Overview, one short section per place, ONE packing list, ONE closing note; one card per place."""
    model, reply = _two_city_turn(employee, fake_llm, weather_api, _trip_json(["Delhi", "Mumbai"]))
    text = reply.reply
    assert text.startswith("Here's the weather for your 2-stop trip (22–26 Nov). Wet in both places")
    assert "\n\nDelhi · 22–24 Nov\nRain likely" in text and "\n\nMumbai · 25–26 Nov\nRain likely" in text
    assert text.count("What to pack for the whole trip:") == 1 and text.count("Forecasts can change") == 1
    assert "What to pack:" not in text                                     # no per-city lists glued together
    assert [c.destination for c in reply.weather_cards] == ["Delhi", "Mumbai"] and all(c.days for c in reply.weather_cards)
    assert len(model.calls) == 2                                           # tool round + ONE writing call
    assert reply.guardrail_status == GuardrailStatus.PASSED


def test_trip_text_with_a_wrong_number_falls_back_to_the_same_layout(employee, fake_llm, weather_api):
    wrong = json.dumps({"overview": "Hot everywhere.", "cities": [{"place": "Delhi", "summary": "Up to 41 °C."},
                        {"place": "Mumbai", "summary": "Up to 41 °C."}], "travel_checklist": ["a", "b", "c"]})
    _, reply = _two_city_turn(employee, fake_llm, weather_api, wrong, wrong)
    assert "41" not in reply.reply                                         # never shown
    assert reply.reply.startswith("Here's the weather for your 2-stop trip (22–26 Nov).")
    assert "Delhi · 22–24 Nov\nRain, 19.4–27.8 °C, rain chance up to 70%." in reply.reply
    assert reply.reply.count("What to pack for the whole trip:") == 1
    assert reply.guardrail_status == GuardrailStatus.OUTPUT_REWRITTEN


def test_trip_text_missing_a_place_falls_back(employee, fake_llm, weather_api):
    one = _trip_json(["Delhi"])
    _, reply = _two_city_turn(employee, fake_llm, weather_api, one, one)
    assert "Mumbai · 25–26 Nov" in reply.reply and "Delhi · 22–24 Nov" in reply.reply


def test_slow_trip_text_uses_the_layout_from_the_data(employee, fake_llm, weather_api, monkeypatch):
    import time as _time
    monkeypatch.setattr(chat_service, "WEATHER_CARDS_BUDGET_SECONDS", 0.3)
    monkeypatch.setattr(chat_service, "_trip_text", lambda *a: _time.sleep(3))
    started = _time.monotonic()
    _, reply = _two_city_turn(employee, fake_llm, weather_api)
    assert _time.monotonic() - started < 2
    assert "Delhi · 22–24 Nov" in reply.reply and "Mumbai · 25–26 Nov" in reply.reply


def test_missing_destinations_are_looked_up_in_a_second_round(employee, fake_llm, weather_api):
    """Three places with dates; the model looks up only Delhi -> Vera asks it once more -> one 3-stop answer."""
    from langchain_core.messages import AIMessage
    _geocode_any(weather_api, {"Delhi": ("Delhi", "Delhi", "India"), "Mumbai": ("Mumbai", "Maharashtra", "India"),
                               "Chennai": ("Chennai", "Tamil Nadu", "India")})
    delhi = tool_call("get_weather_forecast", {"destination": "Delhi", "start_date": "2026-11-22",
                                               "end_date": "2026-11-24"}, call_id="c-delhi")
    rest = AIMessage(content="", tool_calls=[
        {"name": "get_weather_forecast", "args": {"destination": "Mumbai", "start_date": "2026-11-25",
                                                  "end_date": "2026-11-27"}, "id": "c-mumbai"},
        {"name": "get_weather_forecast", "args": {"destination": "Chennai", "start_date": "2026-11-28",
                                                  "end_date": "2026-11-29"}, "id": "c-chennai"}])
    model = fake_llm(delhi, rest, _trip_json(["Delhi", "Mumbai", "Chennai"]))
    sid = session_manager.open_session(employee).session_id
    msg = "Delhi from 22nd to 24th\nMumbai 25th to 27th\nChennai 28th and 29th - what should I pack?"
    reply = chat_service.handle_message(employee, sid, msg, "r", "c")
    assert [c.destination for c in reply.weather_cards] == ["Delhi", "Mumbai", "Chennai"]
    assert reply.reply.startswith("Here's the weather for your 3-stop trip")
    assert model.calls[1][1] == ["get_weather_forecast"]                  # the second round offers the weather tool


def test_fallback_trip_packing_list_names_places_and_follows_the_data():
    from datetime import datetime, timezone
    def fc(place, code, lo, hi, pct, mm):
        d = DailyForecast(date=TODAY + timedelta(days=11), weather_code=code, condition="Clear sky", temp_min_c=lo,
                          temp_max_c=hi, precipitation_probability_max_pct=pct, precipitation_sum_mm=mm, wind_speed_max_kmh=8)
        return WeatherForecastResult(status=WeatherStatus.AVAILABLE, destination=place, resolved_location=f"{place}, India",
                                     requested_from=d.date, requested_to=d.date, covered_dates=[d.date], days=[d],
                                     retrieved_at=datetime(2026, 11, 25, tzinfo=timezone.utc))
    trip = [fc("Delhi", 2, 11.4, 22.6, 0, 0.0), fc("Mumbai", 0, 21.2, 34.3, 2, 0.0), fc("Chennai", 2, 21.8, 28.4, 23, 0.0)]
    tips = formatter.trip_checklist(trip)
    assert "Warm layers for Delhi - lows down to 11.4 °C" in tips
    assert "Light clothing, water and sun protection for Mumbai - highs up to 34.3 °C" in tips
    assert "Umbrella or raincoat for Chennai" in tips                       # 23%: yes; Mumbai 2%: no
    assert ov.check_weather_grounding(" ".join(tips), ov.weather_facts(trip)) == []
