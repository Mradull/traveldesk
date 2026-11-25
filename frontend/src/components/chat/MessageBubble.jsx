import WeatherAnswerCard from "./WeatherAnswerCard";
import CitationChips from "./CitationChips";

const TOOL_TEXT = {
  search_expense_policy: "Searched the policy",
  get_weather_forecast: "Checked the weather",
};

/** One chat item. Text is always rendered as text (never as HTML). */
export default function MessageBubble({ item, onRetry }) {
  if (item.role === "user") return <div className="bubble bubble--user">{item.text}</div>;
  if (item.role === "notice") return <div className="chat-notice">{item.text}</div>;

  if (item.role === "error") {
    return (
      <div className="bubble bubble--error">
        <p>{item.text}</p>
        {item.retryText && onRetry && (
          <button type="button" className="btn btn--secondary btn--small" onClick={() => onRetry(item)}>Retry</button>
        )}
      </div>
    );
  }

  // every weather card of this answer (one per city); falls back to the single `weather`
  const cards = item.weatherCards?.length ? item.weatherCards : item.weather ? [item.weather] : [];
  const isAnswer = cards.length > 0 || item.citations?.length > 0;
  // "Checked the weather" once, even when Vera checked two cities
  const toolLabels = [...new Set((item.tools ?? []).map(
    (t) => `${TOOL_TEXT[t.tool_name] ?? t.tool_name}${t.status === "error" ? " (unavailable)" : ""}`))];
  const failed = item.status === "FAILED" || item.status === "PARTIAL";
  return (
    <div className={failed ? "bubble bubble--ai bubble--warn" : "bubble bubble--ai"}>
      {/* reply already contains the summary and "What to pack" list, so the card shows only the forecast details */}
      {item.text && <p className="bubble__text">{item.text}</p>}
      {cards.map((card, i) => (
        <WeatherAnswerCard key={`${card.destination}-${i}`} card={card} showSummary={!item.text} />
      ))}
      {item.citations?.length > 0 && <CitationChips citations={item.citations} />}
      {toolLabels.length > 0 && <p className="bubble__tools">{toolLabels.join(", ")}</p>}
      {item.retryText && onRetry && (
        <button type="button" className="btn btn--secondary btn--small bubble__retry" onClick={() => onRetry(item)}>Retry</button>
      )}
      {isAnswer && <p className="bubble__label">AI suggestion - informational only</p>}
    </div>
  );
}
