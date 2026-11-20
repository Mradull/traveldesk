"""
chat/formatter.py - turn tool results into what the employee sees (owner: Piyush, M2).

* ForecastBasis and destination are built by CODE from WeatherForecastResult, never by the LLM.
* template_weather_output() is the deterministic fallback when the LLM's weather text fails
  grounding twice or the AI is down: every number in it is copied from the tool result.
* weather_status_reply() gives fixed, honest texts for out-of-range, not-found, ambiguous and
  provider errors (no LLM involved, so nothing can be invented).
"""
import json
from datetime import date

from app.ai.output_validators import COLD_MAX_C, HOT_MIN_C, STRONG_WIND_KMH, RAIN_CODES
from app.core.config import get_settings
from app.schemas import (Citation, ForecastBasis, RetrievedChunk, ToolResult, VeraWeatherAnswer,
                         VeraWeatherLLMOutput, WeatherForecastResult, WeatherStatus)


def fmt_day(d: date) -> str:
    return d.strftime("%d %b %Y").lstrip("0")


def _date_list(days: list[date]) -> str:
    """'23 Nov 2026 to 26 Nov 2026' for a run, or a comma list."""
    if not days:
        return ""
    if len(days) > 2 and (days[-1] - days[0]).days == len(days) - 1:
        return f"{fmt_day(days[0])} to {fmt_day(days[-1])}"
    return ", ".join(fmt_day(d) for d in days)


def forecast_basis(r: WeatherForecastResult) -> ForecastBasis:
    coverage = "NONE" if not r.covered_dates else ("PARTIAL" if r.uncovered_dates else "FULL")
    return ForecastBasis(source=r.source, resolved_location=r.resolved_location, date_from=r.requested_from,
                         date_to=r.requested_to, forecast_available=bool(r.covered_dates), coverage=coverage,
                         covered_dates=r.covered_dates, uncovered_dates=r.uncovered_dates,
                         retrieved_at=r.retrieved_at)


def weather_answer(r: WeatherForecastResult, out: VeraWeatherLLMOutput) -> VeraWeatherAnswer:
    """The brief's five fields: destination + forecast_basis + limitations come from CODE (facts the model
    must not invent); weather_summary + travel_checklist come from the checked LLM output or the template."""
    return VeraWeatherAnswer(destination=r.destination, forecast_basis=forecast_basis(r),
                             weather_summary=out.weather_summary, travel_checklist=out.travel_checklist,
                             limitations=_limitations(r))


def weather_reply_text(answer: VeraWeatherAnswer) -> str:
    """The chat bubble: summary, the packing tips, and one honest closing note (plain text, no HTML)."""
    tips = "\n".join(f"• {tip}" for tip in answer.travel_checklist)
    basis = answer.forecast_basis
    if basis.uncovered_dates:
        note = (f"Forecast not available for {_date_list(basis.uncovered_dates)}, so check again closer to "
                f"your travel date.")
    else:
        note = "Forecasts can change, so check again a day before you travel."
    return f"{answer.weather_summary}\n\nWhat to pack:\n{tips}\n\n{note}"


def _limitations(r: WeatherForecastResult) -> list[str]:
    items = [f"Forecast from {r.source}, retrieved {r.retrieved_at:%d %b %Y %H:%M} UTC; forecasts can change."]
    if r.uncovered_dates:
        items.append(f"Forecast not available for {_date_list(r.uncovered_dates)} (outside the "
                     f"{get_settings().weather_forecast_horizon_days}-day forecast range). Check again closer to travel.")
    return items


def template_weather_output(r: WeatherForecastResult) -> VeraWeatherLLMOutput:
    """Deterministic summary and checklist built only from the returned values."""
    place = r.resolved_location or r.destination
    if not r.days:
        return VeraWeatherLLMOutput(
            weather_summary=f"Forecast not available for {place} on {_date_list(r.uncovered_dates)}.",
            travel_checklist=["Comfortable shoes for meetings and getting around", "Your ID and travel documents",
                              "Phone charger and a power bank"],
            limitations=_limitations(r))
    lows = [d.temp_min_c for d in r.days if d.temp_min_c is not None]
    highs = [d.temp_max_c for d in r.days if d.temp_max_c is not None]
    rain_pct = [d.precipitation_probability_max_pct for d in r.days if d.precipitation_probability_max_pct is not None]
    winds = [d.wind_speed_max_kmh for d in r.days if d.wind_speed_max_kmh is not None]
    conditions = list(dict.fromkeys(d.condition for d in r.days if d.condition))
    parts = [f"{place}, {_date_list(r.covered_dates)}: {', '.join(conditions).lower() or 'no condition data'}."]
    if lows and highs:
        parts.append(f"Temperatures from {min(lows)} °C to {max(highs)} °C.")
    sums = [d.precipitation_sum_mm for d in r.days if d.precipitation_sum_mm is not None]
    if rain_pct and max(rain_pct) > 0:
        parts.append(f"Chance of rain up to {max(rain_pct)}%.")
    elif rain_pct and not any(sums):
        parts.append("No rain expected.")
    if winds:
        parts.append(f"Maximum wind {max(winds)} km/h.")

    rainy = any((d.precipitation_probability_max_pct or 0) > 0 or (d.precipitation_sum_mm or 0) > 0
                or d.weather_code in RAIN_CODES for d in r.days)
    checklist = []
    if rainy:
        checklist.append("Carry an umbrella or raincoat and allow extra travel time")
    if lows and min(lows) <= COLD_MAX_C:
        checklist.append("Pack warm layers")
    if highs and max(highs) >= HOT_MIN_C:
        checklist.append("Wear light clothing, carry water and use sun protection")
    if winds and max(winds) >= STRONG_WIND_KMH:
        checklist.append("Secure loose items and check transport updates")
    # general items (no weather claim) to reach at least 3 tips
    for general in ("Comfortable shoes for meetings and getting around", "Your ID and travel documents",
                    "Phone charger and a power bank"):
        if len(checklist) < 3:
            checklist.append(general)
    return VeraWeatherLLMOutput(weather_summary=" ".join(parts)[:700], travel_checklist=checklist[:5],
                                limitations=_limitations(r))


def weather_status_reply(result: ToolResult) -> str | None:
    """Fixed reply for every weather outcome that has no forecast values; None if values exist."""
    if not result.ok:
        return f"{result.error_message} Please try again." if result.retryable else result.error_message
    r = WeatherForecastResult.model_validate(result.data)
    if r.status == WeatherStatus.LOCATION_AMBIGUOUS:
        return (f"I found more than one place called {r.destination}: {'; '.join(r.candidates)}. "
                f"Which one do you mean? You can write it like \"{r.destination}, <country>\".")
    if r.status == WeatherStatus.LOCATION_NOT_FOUND:
        return (f"I couldn't find a place called \"{r.destination}\". Please check the spelling or add the "
                f"state or country, for example \"{r.destination}, India\".")
    if r.status == WeatherStatus.FORECAST_OUT_OF_RANGE:
        return (f"Forecast not available for {r.resolved_location or r.destination} on "
                f"{_date_list(r.uncovered_dates)}. Forecasts cover today plus "
                f"{get_settings().weather_forecast_horizon_days - 1} days, so please ask again closer to your travel date.")
    return None


def compact_weather_for_llm(r: WeatherForecastResult) -> str:
    """Only the facts the LLM may use, as small JSON (keeps the tool-results budget)."""
    return json.dumps({
        "place": r.resolved_location, "covered_dates": [d.isoformat() for d in r.covered_dates],
        "uncovered_dates_forecast_not_available": [d.isoformat() for d in r.uncovered_dates],
        "days": [{k: v for k, v in d.model_dump(mode="json").items() if v is not None} for d in r.days]})


def citations(chunks: list[RetrievedChunk], used_ids: list[str]) -> list[Citation]:
    """Citation chips for the ids the answer really used, best score per id."""
    best: dict[str, RetrievedChunk] = {}
    for c in chunks:
        if c.ref_id in used_ids and (c.ref_id not in best or c.similarity > best[c.ref_id].similarity):
            best[c.ref_id] = c
    return [Citation(ref_id=i, title=best[i].section_title, similarity=best[i].similarity)
            for i in used_ids if i in best]

