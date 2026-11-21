import { formatDate, formatDateTime } from "../../utils/format";

const shortDate = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });

function describeDates(dates) {
  if (dates.length <= 3) return dates.map(formatDate).join(", ");
  return `${formatDate(dates[0])} – ${formatDate(dates[dates.length - 1])} (${dates.length} days)`;
}

/** Vera's weather answer: every number comes from the weather tool result */
export default function WeatherAnswerCard({ card }) {
  const basis = card.forecast_basis ?? {};
  const uncovered = basis.uncovered_dates ?? [];
  const days = card.days ?? [];

  return (
    <div className="weather-card">
      <div className="weather-card__head">
        <strong>{basis.resolved_location ?? card.destination}</strong>
        <span className="muted small">{formatDate(basis.date_from)} – {formatDate(basis.date_to)}</span>
      </div>
      <p className="muted small">Source: {basis.source ?? "Open-Meteo"}, retrieved {formatDateTime(basis.retrieved_at)}</p>

      {days.length > 0 && (
        <div className="table-wrap">
          <table className="weather-table">
            <thead>
              <tr><th>Day</th><th>Conditions</th><th className="num">°C</th><th className="num">Rain</th><th className="num">Wind</th></tr>
            </thead>
            <tbody>
              {days.map((d) => (
                <tr key={d.forecast_date}>
                  <td>{shortDate(d.forecast_date)}</td>
                  <td>{d.condition ?? "–"}</td>
                  <td className="num">{d.temp_min_c ?? "–"}–{d.temp_max_c ?? "–"}</td>
                  <td className="num">{d.precipitation_probability_max_pct ?? "–"}%, {d.precipitation_sum_mm ?? "–"} mm</td>
                  <td className="num">{d.wind_speed_max_kmh ?? "–"} km/h</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {uncovered.length > 0 && (
        <p className="weather-card__na">
          <strong>Forecast not available</strong> for {describeDates(uncovered)}. Forecasts cover about the next 16 days.
        </p>
      )}

      {card.weather_summary && <p>{card.weather_summary}</p>}

      {card.travel_checklist?.length > 0 && (
        <>
          <p className="weather-card__title">Travel checklist</p>
          <ul>{card.travel_checklist.map((item) => <li key={item}>{item}</li>)}</ul>
        </>
      )}

      {card.limitations?.length > 0 && (
        <>
          <p className="weather-card__title">Limitations</p>
          <ul className="muted small">{card.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
        </>
      )}

      {card.disclaimer && <p className="muted small">{card.disclaimer}</p>}
    </div>
  );
}
