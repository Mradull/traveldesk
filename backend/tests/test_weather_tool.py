"""
test_weather_tool.py (M2) - WeatherService with Open-Meteo mocked by respx.
Covers: inputs required, invalid dates, unknown argument, out of range, partial, available
(values copied exactly), not found, ambiguous, qualifier, timeout, connection, 5xx, 429,
invalid JSON, empty response, cache (no ids in the key) and the log rows.
"""
from datetime import timedelta

import httpx
import pytest

from app.core.config import get_settings
from app.schemas import ErrorCode, ToolContext, WeatherStatus
from app.services import weather_service as ws
from tests.conftest import TODAY, forecast_json, rows

pytestmark = pytest.mark.usefixtures("vera_db")   # Vera fixtures: test DB, frozen today, fakes


def iso(days_from_today: int) -> str:
    return (TODAY + timedelta(days=days_from_today)).isoformat()


@pytest.fixture
def ctx(employee):
    """A real session + turn so the log rows can reference them."""
    from app.repositories import chat_repo
    from app.core.database import transaction
    with transaction() as conn:
        s = chat_repo.create_session(conn, employee.employee_id)
        c = chat_repo.create_conversation(conn, s["session_id"], "req-1", "corr-weather", "fake")
    return ToolContext(employee_id=employee.employee_id, session_id=s["session_id"],
                       conversation_id=c["conversation_id"], correlation_id="corr-weather")


def call(args, ctx=None):
    return ws.get_weather_forecast(args, ctx, "call-1")


@pytest.mark.parametrize("args, code", [
    ({"destination": "Bengaluru", "start_date": iso(3)}, ErrorCode.WEATHER_INPUT_MISSING),
    ({"start_date": iso(3), "end_date": iso(4)}, ErrorCode.WEATHER_INPUT_MISSING),
    ({"destination": "Bengaluru", "start_date": iso(5), "end_date": iso(3)}, ErrorCode.WEATHER_INVALID_DATES),
    ({"destination": "Bengaluru", "start_date": iso(1), "end_date": iso(40)}, ErrorCode.WEATHER_INVALID_DATES),
    ({"destination": "Bengaluru", "start_date": "05/06", "end_date": iso(4)}, ErrorCode.WEATHER_INVALID_DATES),
    ({"destination": "Bengaluru", "start_date": iso(3), "end_date": iso(4), "trip_id": 2}, ErrorCode.VALIDATION_ERROR),
])
def test_bad_inputs_never_call_the_provider(weather_api, args, code):
    result = call(args)
    assert not result.ok and result.error_code == code
    assert not weather_api.calls                     # Open-Meteo NOT called


def test_available_values_are_copied_exactly(weather_api):
    result = call({"destination": "Bengaluru", "start_date": iso(3), "end_date": iso(6)})
    assert result.ok and result.error_code is None
    data = result.data
    assert data["status"] == WeatherStatus.AVAILABLE
    assert data["resolved_location"] == "Bengaluru, Karnataka, India"
    assert len(data["days"]) == 4 and data["uncovered_dates"] == []
    day = data["days"][0]
    assert (day["temp_min_c"], day["temp_max_c"], day["precipitation_probability_max_pct"],
            day["precipitation_sum_mm"], day["wind_speed_max_kmh"], day["condition"]) == (19.4, 27.8, 70, 4.2, 14.0, "Rain")
    params = weather_api["forecast"].calls.last.request.url.params
    assert params["daily"] == ws.DAILY_FIELDS and params["timezone"] == "auto"


def test_partial_when_some_dates_are_past_the_horizon(weather_api):
    result = call({"destination": "Bengaluru", "start_date": iso(13), "end_date": iso(18)})
    data = result.data
    assert data["status"] == WeatherStatus.PARTIAL
    assert data["covered_dates"] == [iso(13), iso(14), iso(15)]          # today + 15 is the last day
    assert data["uncovered_dates"] == [iso(16), iso(17), iso(18)]
    assert weather_api["forecast"].calls.last.request.url.params["end_date"] == iso(15)


def test_out_of_range_has_no_values_and_no_forecast_call(weather_api):
    result = call({"destination": "Bengaluru", "start_date": iso(40), "end_date": iso(44)})
    assert result.ok and result.error_code == ErrorCode.FORECAST_OUT_OF_RANGE
    assert result.data["status"] == WeatherStatus.FORECAST_OUT_OF_RANGE and result.data["days"] == []
    assert len(result.data["uncovered_dates"]) == 5
    assert not weather_api["forecast"].called


def test_location_not_found(weather_api):
    weather_api["geo"].mock(return_value=httpx.Response(200, json={"generationtime_ms": 0.4}))
    result = call({"destination": "Atlantisville", "start_date": iso(1), "end_date": iso(2)})
    assert result.data["status"] == WeatherStatus.LOCATION_NOT_FOUND
    assert result.error_code == ErrorCode.WEATHER_LOCATION_NOT_FOUND


HYDERABADS = {"results": [
    {"name": "Hyderabad", "admin1": "Telangana", "country": "India", "country_code": "IN",
     "latitude": 17.38, "longitude": 78.46, "population": 6809970},
    {"name": "Hyderabad", "admin1": "Sindh", "country": "Pakistan", "country_code": "PK",
     "latitude": 25.39, "longitude": 68.37, "population": 1386330}]}


def test_ambiguous_place_asks_with_candidates(weather_api):
    weather_api["geo"].mock(return_value=httpx.Response(200, json=HYDERABADS))
    result = call({"destination": "Hyderabad", "start_date": iso(1), "end_date": iso(2)})
    assert result.data["status"] == WeatherStatus.LOCATION_AMBIGUOUS
    assert result.data["candidates"] == ["Hyderabad, Telangana, India", "Hyderabad, Sindh, Pakistan"]
    assert not weather_api["forecast"].called


def test_comma_qualifier_resolves_the_ambiguity(weather_api):
    weather_api["geo"].mock(return_value=httpx.Response(200, json=HYDERABADS))
    result = call({"destination": "Hyderabad, Pakistan", "start_date": iso(1), "end_date": iso(2)})
    assert result.data["resolved_location"] == "Hyderabad, Sindh, Pakistan"
    assert weather_api["geo"].calls.last.request.url.params["name"] == "Hyderabad"


@pytest.mark.parametrize("response, code", [
    (httpx.TimeoutException("slow"), ErrorCode.WEATHER_TIMEOUT),
    (httpx.ConnectError("down"), ErrorCode.WEATHER_CONNECTION_FAILED),
    (httpx.Response(503), ErrorCode.WEATHER_PROVIDER_ERROR),
    (httpx.Response(429), ErrorCode.WEATHER_RATE_LIMITED),
    (httpx.Response(200, text="<html>not json</html>"), ErrorCode.WEATHER_INVALID_RESPONSE),
    (httpx.Response(200, json={"daily": {"time": []}}), ErrorCode.WEATHER_EMPTY_RESPONSE),
])
def test_provider_failures_are_safe_and_logged(weather_api, ctx, response, code):
    route = weather_api["forecast"]
    route.mock(side_effect=response) if isinstance(response, Exception) else route.mock(return_value=response)
    result = call({"destination": "Bengaluru", "start_date": iso(3), "end_date": iso(4)}, ctx)
    assert not result.ok and result.error_code == code and result.data is None   # no fallback forecast
    assert result.error_message == ws.SAFE_MESSAGES[code]
    log = rows("SELECT * FROM weather_tool_logs")[0]
    assert (log["result_status"], log["error_code"], log["correlation_id"]) == ("ERROR", code.value, "corr-weather")
    err = rows("SELECT * FROM error_logs")[0]
    assert err["error_code"] == code.value and err["session_id"] == ctx.session_id
    assert err["tool_call_id"] == "call-1"


def test_cache_hit_skips_the_provider_and_key_has_no_ids(weather_api, ctx):
    args = {"destination": " Bengaluru ", "start_date": iso(3), "end_date": iso(4)}
    first, second = call(args, ctx), call({**args, "destination": "bengaluru"}, ctx)
    assert not first.data["from_cache"] and second.data["from_cache"]
    assert weather_api["forecast"].call_count == 1
    key = next(iter(ws._cache))
    assert key == ("bengaluru", TODAY + timedelta(days=3), TODAY + timedelta(days=4))   # place + dates only
    assert [r["cache_hit"] for r in rows("SELECT cache_hit FROM weather_tool_logs ORDER BY weather_call_id")] == [False, True]


def test_every_call_writes_a_weather_log(weather_api, ctx):
    call({"destination": "Bengaluru", "start_date": iso(3), "end_date": iso(4)}, ctx)
    call({"destination": "Bengaluru"}, ctx)
    logs = rows("SELECT * FROM weather_tool_logs ORDER BY weather_call_id")
    assert len(logs) == 2
    assert logs[0]["result_status"] == "AVAILABLE" and logs[0]["resolved_location"] == "Bengaluru, Karnataka, India"
    assert logs[0]["http_status"] == 200 and logs[0]["provider"] == "Open-Meteo"
    assert logs[1]["error_code"] == "WEATHER_INPUT_MISSING" and logs[1]["start_date"] is None


def test_wmo_mapping_table():
    assert [ws.wmo_condition(c) for c in (0, 2, 45, 53, 63, 75, 81, 96)] == [
        "Clear sky", "Partly cloudy", "Fog", "Drizzle", "Rain", "Snow", "Rain showers", "Thunderstorm"]
    assert get_settings().weather_forecast_horizon_days == 16
    assert forecast_json(TODAY, 1)["daily"]["weather_code"] == [61]
