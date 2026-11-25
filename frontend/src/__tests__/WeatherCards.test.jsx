// One Vera answer can hold several weather cards ("Rome, then Catania"): the bubble shows all of them.
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import MessageBubble from "../components/chat/MessageBubble";

// minimal VeraWeatherAnswer for one city
const card = (place, day) => ({
  destination: place.split(",")[0],
  forecast_basis: {
    source: "Open-Meteo", resolved_location: place, date_from: day, date_to: day, forecast_available: true,
    coverage: "FULL", covered_dates: [day], uncovered_dates: [], retrieved_at: "2026-11-25T11:00:00Z",
  },
  weather_summary: `${place} summary`, travel_checklist: ["Umbrella"], limitations: ["Forecasts can change."],
  days: [{ date: day, condition: "Rain", temp_min_c: 9, temp_max_c: 14, precipitation_probability_max_pct: 60,
           precipitation_sum_mm: 2, wind_speed_max_kmh: 10 }],
  disclaimer: "Weather guidance is informational only.",
});

describe("Vera weather cards", () => {
  it("shows one card per city and the tool label once", () => {
    const item = {
      role: "ai", text: "Rome ... Catania ...",
      weatherCards: [card("Rome, Lazio, Italy", "2026-12-01"), card("Catania, Sicily, Italy", "2026-12-05")],
      tools: [{ tool_name: "get_weather_forecast", status: "ok" }, { tool_name: "get_weather_forecast", status: "ok" }],
    };
    render(<MessageBubble item={item} />);
    expect(screen.getByText("Rome, Lazio, Italy")).toBeInTheDocument();
    expect(screen.getByText("Catania, Sicily, Italy")).toBeInTheDocument();
    expect(screen.getByText("Checked the weather")).toBeInTheDocument();     // not "..., Checked the weather"
  });

  it("still shows the single card of an older reply", () => {
    render(<MessageBubble item={{ role: "ai", text: "Pune ...", weather: card("Pune, Maharashtra, India", "2026-12-01") }} />);
    expect(screen.getByText("Pune, Maharashtra, India")).toBeInTheDocument();
  });
});
