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

from app.ai.output_validators import (COLD_MAX_C, FOG_CODES, HOT_MIN_C, RAIN_CODES, RAIN_GEAR_MIN_PCT,
                                      STRONG_WIND_KMH)

MILD_WARM_MIN_C = 25        # highs 25-32 C: light, breathable clothes (>= 32 is 'hot', see HOT_MIN_C)
COOL_MORNING_MAX_C = 20     # lows 15-20 C: a light layer for mornings (<= 15 is 'cold', see COLD_MAX_C)
from app.core.config import get_settings
from app.schemas import (Citation, ForecastBasis, RetrievedChunk, ToolResult, VeraWeatherAnswer,
                         VeraWeatherLLMOutput, WeatherForecastResult, WeatherStatus)


def fmt_day(d: date) -> str:
    return d.strftime("%d %b %Y").lstrip("0")


def _short_day(d: date) -> str:
    return f"{d.day} {d:%b}"                                  # "9 Dec"


def _date_list(days: list[date]) -> str:
    """'8–9 Dec 2026' for a run in one month, '30 Nov 2026 to 2 Dec 2026' across months, else a comma list."""
    if not days:
        return ""
    if len(days) > 1 and (days[-1] - days[0]).days == len(days) - 1:          # consecutive dates
        if (days[0].month, days[0].year) == (days[-1].month, days[-1].year):
            return f"{days[0].day}–{days[-1].day} {days[0]:%b %Y}"
        return f"{fmt_day(days[0])} to {fmt_day(days[-1])}"
    return ", ".join(fmt_day(d) for d in days)


def forecast_basis(r: WeatherForecastResult) -> ForecastBasis:
    coverage = "NONE" if not r.covered_dates else ("PARTIAL" if r.uncovered_dates else "FULL")
    return ForecastBasis(source=r.source, resolved_location=r.resolved_location, date_from=r.requested_from,
                         date_to=r.requested_to, forecast_available=bool(r.covered_dates), coverage=coverage,
                         covered_dates=r.covered_dates, uncovered_dates=r.uncovered_dates,
                         retrieved_at=r.retrieved_at)


def weather_answer(r: WeatherForecastResult, out: VeraWeatherLLMOutput) -> VeraWeatherAnswer:
    """The brief's five fields: destination + forecast_basis + limitations (+ the daily table) come from CODE
    (facts the model must not invent); weather_summary + travel_checklist come from the checked LLM output
    or the template."""
    return VeraWeatherAnswer(destination=r.destination, forecast_basis=forecast_basis(r),
                             weather_summary=out.weather_summary, travel_checklist=out.travel_checklist,
                             limitations=_limitations(r), days=r.days)   # daily table: exact tool values


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
    conditions = list(dict.fromkeys(d.condition.lower() for d in r.days if d.condition))
    fog_days = [d.date for d in r.days if d.weather_code in FOG_CODES]
    # "Chennai, Tamil Nadu, India (8–9 Dec 2026): partly cloudy, with fog on 9 Dec."
    sky = " and ".join(c for c in conditions if c != "fog") or "fog"
    fog_note = f", with fog on {', '.join(_short_day(d) for d in fog_days)}" if fog_days and sky != "fog" else ""
    parts = [f"{place} ({_date_list(r.covered_dates)}): {sky}{fog_note}."]
    if lows and highs:
        parts.append(f"Temperatures from {min(lows)} °C to {max(highs)} °C.")
    sums = [d.precipitation_sum_mm for d in r.days if d.precipitation_sum_mm is not None]
    if rain_pct and max(rain_pct) > 0:
        parts.append(f"Chance of rain up to {max(rain_pct)}%.")
    elif rain_pct and not any(sums):
        parts.append("No rain expected.")
    if winds:
        parts.append(f"Wind up to {max(winds)} km/h.")

    rainy = any((d.precipitation_probability_max_pct or 0) >= RAIN_GEAR_MIN_PCT or (d.precipitation_sum_mm or 0) > 0
                or d.weather_code in RAIN_CODES for d in r.days)                  # rain gear only for real risk
    checklist = []
    # each tip names its reason, using only values from the forecast (so the grounding check always passes)
    if rainy:
        reason = f"rain chance up to {max(rain_pct)}%" if rain_pct and max(rain_pct) > 0 else "rain in the forecast"
        checklist.append(f"Umbrella or raincoat, and extra travel time - {reason}")
    if highs and max(highs) >= HOT_MIN_C:
        checklist.append(f"Light clothing, water and sun protection - highs up to {max(highs)} °C")
    elif highs and max(highs) >= MILD_WARM_MIN_C:
        checklist.append(f"Light, breathable clothing - highs up to {max(highs)} °C")
    if lows and min(lows) <= COLD_MAX_C:
        checklist.append(f"Warm layers - lows down to {min(lows)} °C")
    elif lows and min(lows) <= COOL_MORNING_MAX_C:
        checklist.append(f"A light layer for cooler mornings - lows around {min(lows)} °C")
    if fog_days:
        checklist.append(f"Allow extra travel time on {', '.join(_short_day(d) for d in fog_days)} - fog expected")
    if winds and max(winds) >= STRONG_WIND_KMH:
        checklist.append(f"Strong wind up to {max(winds)} km/h - secure loose items and check transport updates")
    # general items (no weather claim) only when the forecast gives fewer than 3 tips
    for general in ("Comfortable shoes for meetings and getting around", "Your ID and travel documents",
                    "Phone charger and a power bank"):
        if len(checklist) < 3:
            checklist.append(general)
    return VeraWeatherLLMOutput(weather_summary=" ".join(parts)[:700], travel_checklist=checklist[:5],
                                limitations=_limitations(r))


def city_name(r: WeatherForecastResult) -> str:
    """'Bengaluru' from 'Bengaluru, Karnataka, India' (never the employee's own spelling like 'blr')."""
    return (r.resolved_location or r.destination).split(",")[0].strip()


def trip_dates(forecasts: list[WeatherForecastResult]) -> str:
    """'1–9 Dec' for the whole trip (or '30 Nov – 4 Dec' across months)."""
    first, last = forecasts[0].covered_dates[0], forecasts[-1].covered_dates[-1]
    if (first.month, first.year) == (last.month, last.year):
        return f"{first.day}–{last.day} {first:%b}"
    return f"{_short_day(first)} – {_short_day(last)}"


def _city_dates(r: WeatherForecastResult) -> str:
    days = r.covered_dates
    return _short_day(days[0]) if len(days) == 1 else f"{days[0].day}–{_short_day(days[-1])}" \
        if days[0].month == days[-1].month else f"{_short_day(days[0])} – {_short_day(days[-1])}"


def _city_facts_sentence(r: WeatherForecastResult) -> str:
    """Fallback sentence for one place, from its data only."""
    conditions = list(dict.fromkeys(d.condition.lower() for d in r.days if d.condition))
    sky = " and ".join(c for c in conditions if c != "fog") or "fog"
    fog_days = [d.date for d in r.days if d.weather_code in FOG_CODES]
    lows = [d.temp_min_c for d in r.days if d.temp_min_c is not None]
    highs = [d.temp_max_c for d in r.days if d.temp_max_c is not None]
    rain = [d.precipitation_probability_max_pct for d in r.days if d.precipitation_probability_max_pct is not None]
    text = sky[0].upper() + sky[1:]
    if fog_days and sky != "fog":
        text += f", with fog on {', '.join(_short_day(d) for d in fog_days)}"
    if lows and highs:
        text += f", {min(lows)}–{max(highs)} °C"
    text += f", rain chance up to {max(rain)}%." if rain and max(rain) > 0 else ", no rain expected."
    return text


def trip_checklist(forecasts: list[WeatherForecastResult]) -> list[str]:
    """Fallback packing list for the whole trip: one tip per kind of condition, naming the places."""
    def places(pred) -> list[str]:
        return [city_name(r) for r in forecasts if any(pred(d) for d in r.days)]

    def join(names: list[str]) -> str:
        return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    tips = []
    cold = places(lambda d: d.temp_min_c is not None and d.temp_min_c <= COLD_MAX_C)
    if cold:
        low = min(d.temp_min_c for r in forecasts for d in r.days if d.temp_min_c is not None)
        tips.append(f"Warm layers for {join(cold)} - lows down to {low} °C")
    hot = places(lambda d: d.temp_max_c is not None and d.temp_max_c >= HOT_MIN_C)
    if hot:
        high = max(d.temp_max_c for r in forecasts for d in r.days if d.temp_max_c is not None)
        tips.append(f"Light clothing, water and sun protection for {join(hot)} - highs up to {high} °C")
    mild = [n for n in places(lambda d: d.temp_max_c is not None and d.temp_max_c >= MILD_WARM_MIN_C) if n not in hot]
    if mild:
        tips.append(f"Light, breathable clothes for {join(mild)}")
    wet = places(lambda d: (d.precipitation_probability_max_pct or 0) >= RAIN_GEAR_MIN_PCT
                 or (d.precipitation_sum_mm or 0) > 0 or d.weather_code in RAIN_CODES)
    if wet:
        tips.append(f"Umbrella or raincoat for {join(wet)}")
    for r in forecasts:
        fog = [d.date for d in r.days if d.weather_code in FOG_CODES]
        if fog:
            tips.append(f"Extra travel time on {', '.join(_short_day(d) for d in fog)} in {city_name(r)} - fog expected")
    windy = places(lambda d: (d.wind_speed_max_kmh or 0) >= STRONG_WIND_KMH)
    if windy:
        tips.append(f"Secure loose items in {join(windy)} - strong wind expected")
    for general in ("Comfortable shoes for meetings and getting around", "Your ID and travel documents"):
        if len(tips) < 3:
            tips.append(general)
    return tips[:6]


def trip_reply_text(forecasts: list[WeatherForecastResult], overview: str, summaries: list[str],
                    checklist: list[str]) -> str:
    """The whole-trip answer: overview, one short section per place, ONE packing list, ONE closing note.
    The layout is fixed by code; only the sentences come from the AI (or from the data, as fallback)."""
    sections = [f"{city_name(r)} · {_city_dates(r)}\n{text}" for r, text in zip(forecasts, summaries)]
    tips = "\n".join(f"• {tip}" for tip in checklist)
    return "\n\n".join([overview, *sections, f"What to pack for the whole trip:\n{tips}",
                         "Forecasts can change, so check again a day before you travel."])


def trip_fallback(forecasts: list[WeatherForecastResult]) -> tuple[str, list[str], list[str]]:
    """(overview, per-place sentences, checklist) built only from the data."""
    overview = f"Here's the weather for your {len(forecasts)}-stop trip ({trip_dates(forecasts)})."
    return overview, [_city_facts_sentence(r) for r in forecasts], trip_checklist(forecasts)


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

