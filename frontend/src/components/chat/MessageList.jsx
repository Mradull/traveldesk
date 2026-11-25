import { useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble";

const SUGGESTIONS = [
  "What is the meal limit?",
  "Do I need a receipt for every expense?",
  "How do I raise an expense ticket?",
  "What's the weather in Bengaluru this week?",
];

export default function MessageList({ items, sending, onRetry, onSuggest }) {
  const endRef = useRef(null);

  // Keep the newest message in view
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [items.length, sending]);

  return (
    <div className="chat-window__body" role="log" aria-live="polite">
      {items.map((item) => <MessageBubble key={item.id} item={item} onRetry={onRetry} />)}
      {onSuggest && items.length === 1 && !sending && (
        <div className="suggestions" aria-label="Suggested questions">
          {SUGGESTIONS.map((q) => (
            <button key={q} type="button" className="suggestion" onClick={() => onSuggest(q)}>{q}</button>
          ))}
        </div>
      )}
      {sending && (
        <div className="bubble bubble--ai typing" aria-label="Vera is typing">
          <span /><span /><span />
        </div>
      )}
      <div ref={endRef} />
    </div>
  );
}
