"""
services/weather_service.py - the get_weather_forecast tool's engine (owner: Piyush, M2).

Used ONLY by the chat package (Vera). It never reads trips: the three inputs are what the
employee typed in the chat. Steps (Agile Spec v2.0, "Weather tool"):

  validate -> cache -> geocode -> range split -> forecast -> map -> log
  * validate : WeatherToolInput; missing -> WEATHER_INPUT_MISSING, bad dates -> WEATHER_INVALID_DATES,
               unknown argument (e.g. trip_id) -> VALIDATION_ERROR. Open-Meteo is NOT called.
  * geocode  : "City" or "City, State/Country". Qualifier must match; 2+ big matches
               (population >= 100,000) in different countries/states -> LOCATION_AMBIGUOUS.
  * range    : covered = requested dates within today .. today+15; the rest are uncovered.
               Nothing covered -> FORECAST_OUT_OF_RANGE without calling the forecast API.
  * forecast : only the six daily fields of the spec; values copied exactly.
  * errors   : timeout / connection / 5xx / 429 / invalid JSON / empty / other, each with a safe
               message; never a fallback forecast.
  * log      : one weather_tool_logs row per call (+ error_logs for provider failures).
Everything is returned as a ToolResult so the LLM always sees the same shape.
"""
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone

import httpx
from pydantic import ValidationError

from app import schemas
from app.core.config import get_settings
from app.repositories import log_repo
from app.schemas import (DailyForecast, ErrorCategory, ErrorCode, ErrorLogRecord, ErrorSeverity, ToolContext,
                         ToolResult, WeatherForecastResult, WeatherStatus, WeatherToolInput, WeatherToolLog)


DAILY_FIELDS = ("weather_code,temperature_2m_min,temperature_2m_max,precipitation_probability_max,"
                "precipitation_sum,wind_speed_10m_max")

# Safe, user-facing messages per error code (no internals).
SAFE_MESSAGES = {
    ErrorCode.WEATHER_INPUT_MISSING: "I need a destination, a start date and an end date to check the weather.",
    ErrorCode.WEATHER_INVALID_DATES: "The dates are not valid: the end date must be on or after the start "
                                     "date, and one request can cover at most 30 days.",
    ErrorCode.VALIDATION_ERROR: "The weather tool only accepts a destination, a start date and an end date.",
    ErrorCode.WEATHER_TIMEOUT: "The weather service did not answer in time.",
    ErrorCode.WEATHER_CONNECTION_FAILED: "The weather service could not be reached.",
    ErrorCode.WEATHER_PROVIDER_ERROR: "The weather service had a problem.",
    ErrorCode.WEATHER_RATE_LIMITED: "The weather service is busy right now.",
    ErrorCode.WEATHER_INVALID_RESPONSE: "The weather service sent data I could not read.",
    ErrorCode.WEATHER_EMPTY_RESPONSE: "The weather service returned no forecast data.",
    ErrorCode.WEATHER_UNEXPECTED_ERROR: "Something went wrong while checking the weather.",
}
RETRYABLE = {ErrorCode.WEATHER_TIMEOUT, ErrorCode.WEATHER_CONNECTION_FAILED, ErrorCode.WEATHER_PROVIDER_ERROR,
             ErrorCode.WEATHER_RATE_LIMITED, ErrorCode.WEATHER_EMPTY_RESPONSE}
CATEGORY = {ErrorCode.WEATHER_TIMEOUT: ErrorCategory.TIMEOUT, ErrorCode.WEATHER_RATE_LIMITED: ErrorCategory.RATE_LIMIT,
            ErrorCode.WEATHER_INVALID_RESPONSE: ErrorCategory.PARSING}


def wmo_condition(code: int | None) -> str | None:
    """Fixed WMO weather-code table from the spec."""
    if code is None:
        return None
    for codes, text in (((0,), "Clear sky"), ((1, 2, 3), "Partly cloudy"), ((45, 48), "Fog"),
                        (range(51, 58), "Drizzle"), (range(61, 68), "Rain"), (range(71, 78), "Snow"),
                        (range(80, 83), "Rain showers"), (range(95, 100), "Thunderstorm")):
        if code in codes:
            return text
    return "Unknown"


class _Fail(Exception):
    """Internal: a provider/parsing failure with its error code and the HTTP status seen."""

    def __init__(self, code: ErrorCode, http_status: int | None = None, detail: str = ""):
        super().__init__(detail or code.value)
        self.code, self.http_status, self.detail = code, http_status, detail


# ----------------------------------------------------------------------------- cache
# In-memory, per process. Key = (normalised destination, start, end): no employee/trip/ticket id.
_cache: dict[tuple[str, date, date], tuple[float, WeatherForecastResult]] = {}
_cache_lock = threading.Lock()


def cache_key(destination: str, start: date, end: date) -> tuple[str, date, date]:
    return re.sub(r"\s+", " ", destination.strip().lower()), start, end


def _cache_get(key) -> WeatherForecastResult | None:
    with _cache_lock:
        hit = _cache.get(key)
        if hit and hit[0] > time.monotonic():
            return hit[1].model_copy(update={"from_cache": True})
        _cache.pop(key, None)
        return None


def _cache_put(key, result: WeatherForecastResult) -> None:
    with _cache_lock:
        _cache[key] = (time.monotonic() + get_settings().weather_cache_ttl_minutes * 60, result)


def clear_cache() -> None:
    """Used by tests and evals."""
    with _cache_lock:
        _cache.clear()


# ----------------------------------------------------------------------------- HTTP
def _get_json(url: str, params: dict) -> tuple[dict, int]:
    """GET with the 8-second timeout; map every failure to a weather error code."""
    try:
        resp = httpx.get(url, params=params, timeout=get_settings().weather_timeout_seconds)
    except httpx.TimeoutException as exc:
        raise _Fail(ErrorCode.WEATHER_TIMEOUT, detail=str(exc)) from exc
    except httpx.TransportError as exc:                     # DNS, refused, network down
        raise _Fail(ErrorCode.WEATHER_CONNECTION_FAILED, detail=str(exc)) from exc
    if resp.status_code == 429:
        raise _Fail(ErrorCode.WEATHER_RATE_LIMITED, 429)
    if resp.status_code >= 500:
        raise _Fail(ErrorCode.WEATHER_PROVIDER_ERROR, resp.status_code)
    if resp.status_code != 200:
        raise _Fail(ErrorCode.WEATHER_UNEXPECTED_ERROR, resp.status_code, resp.text[:200])
    try:
        data = resp.json()
    except ValueError as exc:
        raise _Fail(ErrorCode.WEATHER_INVALID_RESPONSE, 200, "body is not JSON") from exc
    if not isinstance(data, dict):
        raise _Fail(ErrorCode.WEATHER_INVALID_RESPONSE, 200, "JSON is not an object")
    return data, resp.status_code


def _place_name(r: dict) -> str:
    return ", ".join(p for p in (r.get("name"), r.get("admin1"), r.get("country")) if p)


def _geocode(destination: str) -> tuple[dict | None, list[str], int]:
    """Return (chosen place, ambiguity candidates, http_status). Place None = not found / ambiguous."""
    name, *qualifiers = [p.strip() for p in destination.split(",") if p.strip()]
    data, status = _get_json(get_settings().weather_geocoding_url,
                             {"name": name, "count": 5, "language": "en", "format": "json"})
    results = data.get("results") or []          # Open-Meteo omits "results" when nothing matches
    if not isinstance(results, list):
        raise _Fail(ErrorCode.WEATHER_INVALID_RESPONSE, status, "results is not a list")

    def matches(r: dict, q: str) -> bool:
        q = q.lower()
        return any(q == (r.get(k) or "").lower() for k in ("country", "admin1", "country_code"))

    if qualifiers:                                # "Hyderabad, India" -> keep only Indian results
        results = [r for r in results if all(matches(r, q) for q in qualifiers)]
        return (results[0] if results else None), [], status
    if not results:
        return None, [], status
    big = [r for r in results if (r.get("population") or 0) >= get_settings().weather_ambiguity_min_population]
    regions = {(r.get("country"), r.get("admin1")) for r in big}
    if len(regions) >= 2:                         # several big places share the name: ask the user
        return None, [_place_name(r) for r in big], status
    return (big[0] if big else results[0]), [], status


def _forecast(place: dict, first: date, last: date) -> tuple[list[DailyForecast], int]:
    """Daily values for first..last, copied exactly from Open-Meteo."""
    data, status = _get_json(get_settings().weather_forecast_url, {
        "latitude": place["latitude"], "longitude": place["longitude"], "timezone": "auto",
        "start_date": first.isoformat(), "end_date": last.isoformat(), "daily": DAILY_FIELDS})
    daily = data.get("daily")
    if not daily or not daily.get("time"):
        raise _Fail(ErrorCode.WEATHER_EMPTY_RESPONSE, status)
    try:
        def col(name: str, i: int):
            values = daily.get(name) or []
            return values[i] if i < len(values) else None
        days = [DailyForecast(date=date.fromisoformat(t), weather_code=col("weather_code", i),
                              condition=wmo_condition(col("weather_code", i)),
                              temp_min_c=col("temperature_2m_min", i), temp_max_c=col("temperature_2m_max", i),
                              precipitation_probability_max_pct=col("precipitation_probability_max", i),
                              precipitation_sum_mm=col("precipitation_sum", i),
                              wind_speed_max_kmh=col("wind_speed_10m_max", i))
                for i, t in enumerate(daily["time"])]
    except (TypeError, ValueError, ValidationError) as exc:
        raise _Fail(ErrorCode.WEATHER_INVALID_RESPONSE, status, str(exc)[:200]) from exc
    return days, status


# ----------------------------------------------------------------------------- validation
def _validate(args: dict) -> tuple[WeatherToolInput | None, ErrorCode | None]:
    """G5: only the three known arguments, all present and valid."""
    unknown = set(args) - set(WeatherToolInput.model_fields)
    if unknown:
        return None, ErrorCode.VALIDATION_ERROR
    try:
        return WeatherToolInput.model_validate(args), None
    except ValidationError as exc:
        errors = exc.errors()
        if any(e["type"] == "missing" for e in errors):
            return None, ErrorCode.WEATHER_INPUT_MISSING
        if any(e["loc"] and e["loc"][0] == "destination" for e in errors):
            return None, ErrorCode.WEATHER_INPUT_MISSING
        return None, ErrorCode.WEATHER_INVALID_DATES      # bad date format, end < start, > 30 days


def _safe_date(value) -> date | None:
    """Best-effort date for the log row when the input itself was invalid."""
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


# ----------------------------------------------------------------------------- entry point
def get_weather_forecast(args: dict, ctx: ToolContext | None = None,
                         tool_call_id: str | None = None) -> ToolResult:
    """Run the whole weather tool for one call and log it. Never raises."""
    started = time.monotonic()
    destination_query = str(args.get("destination", ""))[:100]
    log_row = dict(destination_query=destination_query, start_date=_safe_date(args.get("start_date")),
                   end_date=_safe_date(args.get("end_date")))
    result: ToolResult

    inp, invalid = _validate(args)
    if invalid:
        # Provider is NOT called; the LLM/Vera asks the employee instead.
        result = ToolResult(ok=False, error_code=invalid, error_message=SAFE_MESSAGES[invalid])
        log_row.update(error_code=invalid)
        return _finish(result, log_row, started, ctx, tool_call_id)

    key = cache_key(inp.destination, inp.start_date, inp.end_date)
    cached = _cache_get(key)
    if cached:
        log_row.update(resolved_location=cached.resolved_location, result_status=cached.status,
                       cache_hit=True, retrieved_at=cached.retrieved_at)
        return _finish(ToolResult(ok=True, data=cached.model_dump(mode="json")), log_row, started, ctx, tool_call_id)

    requested = [inp.start_date + timedelta(days=i) for i in range((inp.end_date - inp.start_date).days + 1)]
    base = dict(destination=inp.destination, requested_from=inp.start_date, requested_to=inp.end_date)
    http_status = None
    try:
        place, candidates, http_status = _geocode(inp.destination)
        now = datetime.now(timezone.utc)
        if place is None:
            status = WeatherStatus.LOCATION_AMBIGUOUS if candidates else WeatherStatus.LOCATION_NOT_FOUND
            code = (ErrorCode.WEATHER_LOCATION_AMBIGUOUS if candidates else ErrorCode.WEATHER_LOCATION_NOT_FOUND)
            forecast = WeatherForecastResult(status=status, candidates=candidates, retrieved_at=now,
                                             uncovered_dates=requested, **base)
            result = ToolResult(ok=True, data=forecast.model_dump(mode="json"), error_code=code)
        else:
            # Horizon split: today .. today + 15 (16 days) can have values.
            today = schemas.today()
            horizon_end = today + timedelta(days=get_settings().weather_forecast_horizon_days - 1)
            in_range = [d for d in requested if today <= d <= horizon_end]
            where = dict(resolved_location=_place_name(place), latitude=place.get("latitude"),
                         longitude=place.get("longitude"))
            if not in_range:
                forecast = WeatherForecastResult(status=WeatherStatus.FORECAST_OUT_OF_RANGE, retrieved_at=now,
                                                 uncovered_dates=requested, **where, **base)
                result = ToolResult(ok=True, data=forecast.model_dump(mode="json"),
                                    error_code=ErrorCode.FORECAST_OUT_OF_RANGE)
            else:
                days, http_status = _forecast(place, in_range[0], in_range[-1])
                days = [d for d in days if d.date in set(in_range)]
                if not days:
                    raise _Fail(ErrorCode.WEATHER_EMPTY_RESPONSE, http_status)
                covered = [d.date for d in days]          # only dates that really came back
                uncovered = [d for d in requested if d not in set(covered)]
                forecast = WeatherForecastResult(
                    status=WeatherStatus.PARTIAL if uncovered else WeatherStatus.AVAILABLE,
                    covered_dates=covered, uncovered_dates=uncovered, days=days,
                    retrieved_at=datetime.now(timezone.utc), **where, **base)
                _cache_put(key, forecast)
                result = ToolResult(ok=True, data=forecast.model_dump(mode="json"))
        log_row.update(resolved_location=forecast.resolved_location, result_status=forecast.status,
                       error_code=result.error_code, retrieved_at=forecast.retrieved_at)
    except _Fail as fail:
        result = _error_result(fail.code, fail.detail, fail.http_status, ctx, tool_call_id)
        http_status = fail.http_status
        log_row.update(result_status=WeatherStatus.ERROR, error_code=fail.code)
    except Exception as exc:   # noqa: BLE001 - anything else is WEATHER_UNEXPECTED_ERROR, never a crash
        result = _error_result(ErrorCode.WEATHER_UNEXPECTED_ERROR, f"{type(exc).__name__}: {exc}"[:300],
                               http_status, ctx, tool_call_id)
        log_row.update(result_status=WeatherStatus.ERROR, error_code=ErrorCode.WEATHER_UNEXPECTED_ERROR)
    log_row["http_status"] = http_status
    return _finish(result, log_row, started, ctx, tool_call_id)


def _error_result(code: ErrorCode, detail: str, http_status: int | None,
                  ctx: ToolContext | None, tool_call_id: str | None) -> ToolResult:
    """Provider failure: safe message, retry flag, and an error_logs row with the trace ids."""
    log_repo.log_safely(log_repo.insert_error_log, ErrorLogRecord(
        severity=ErrorSeverity.ERROR, source_component="chat.weather_tool",
        category=CATEGORY.get(code, ErrorCategory.WEATHER), error_code=code, safe_message=SAFE_MESSAGES[code],
        internal_message=detail or code.value, http_status=http_status, retryable=code in RETRYABLE,
        correlation_id=ctx.correlation_id if ctx else None, employee_id=ctx.employee_id if ctx else None,
        session_id=ctx.session_id if ctx else None, conversation_id=ctx.conversation_id if ctx else None,
        tool_call_id=tool_call_id, context={"provider": "Open-Meteo"}))
    return ToolResult(ok=False, error_code=code, error_message=SAFE_MESSAGES[code], retryable=code in RETRYABLE)


def _finish(result: ToolResult, log_row: dict, started: float,
            ctx: ToolContext | None, tool_call_id: str | None) -> ToolResult:
    """Write the weather_tool_logs row (only inside a chat turn, where the ids exist)."""
    if ctx is not None:
        log_repo.log_safely(log_repo.insert_weather_tool_log, WeatherToolLog(
            session_id=ctx.session_id, conversation_id=ctx.conversation_id, correlation_id=ctx.correlation_id,
            tool_call_id=tool_call_id, latency_ms=int((time.monotonic() - started) * 1000), **log_row))
    return result


# ----------------------------------------------------------------------------- health
_ping: dict = {"at": 0.0, "ok": False, "latency_ms": None}


def ping_geocoding() -> tuple[bool, int | None]:
    """/health check: one tiny geocoding call, cached for 60 seconds."""
    if time.monotonic() - _ping["at"] < 60:
        return _ping["ok"], _ping["latency_ms"]
    started = time.monotonic()
    try:
        _get_json(get_settings().weather_geocoding_url, {"name": "London", "count": 1, "format": "json"})
        ok = True
    except _Fail:
        ok = False
    _ping.update(at=time.monotonic(), ok=ok, latency_ms=int((time.monotonic() - started) * 1000))
    return ok, _ping["latency_ms"]
