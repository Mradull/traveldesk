import { useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble";

export default function MessageList({ items, sending, onRetry }) {
  const endRef = useRef(null);

  // Keep the newest message in view
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [items.length, sending]);

  return (
    <div className="chat-window__body" role="log" aria-live="polite">
      {items.map((item) => <MessageBubble key={item.id} item={item} onRetry={onRetry} />)}
      {sending && (
        <div className="bubble bubble--ai typing" aria-label="Vera is typing">
          <span /><span /><span />
        </div>
      )}
      <div ref={endRef} />
    </div>
  );
}
