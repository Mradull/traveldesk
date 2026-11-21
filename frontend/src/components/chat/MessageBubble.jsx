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

  const isAnswer = Boolean(item.weather) || item.citations?.length > 0;
  return (
    <div className="bubble bubble--ai">
      {item.text && <p className="bubble__text">{item.text}</p>}
      {item.weather && <WeatherAnswerCard card={item.weather} />}
      {item.citations?.length > 0 && <CitationChips citations={item.citations} />}
      {item.tools?.length > 0 && (
        <p className="bubble__tools">
          {item.tools.map((t) => `${TOOL_TEXT[t.tool_name] ?? t.tool_name}${t.status === "error" ? " (unavailable)" : ""}`).join(", ")}
        </p>
      )}
      {isAnswer && <p className="bubble__label">AI suggestion - informational only</p>}
    </div>
  );
}
