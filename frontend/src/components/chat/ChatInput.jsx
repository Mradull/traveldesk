import { useState } from "react";
import { Send } from "lucide-react";
import { MAX_CHAT_MESSAGE_CHARS } from "../../utils/constants";

/** Enter sends, Shift+Enter adds a new line, 1000-character limit */
export default function ChatInput({ onSend, disabled }) {
  const [text, setText] = useState("");

  function submit() {
    if (disabled || !text.trim()) return;
    onSend(text);
    setText("");
  }

  return (
    <footer className="chat-window__footer">
      <div className="chat-input">
        <textarea
          rows={2}
          value={text}
          maxLength={MAX_CHAT_MESSAGE_CHARS}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder="Ask about the expense policy or the weather…"
          disabled={disabled}
          aria-label="Message Vera"
        />
        <span className="chat-input__count">{text.length}/{MAX_CHAT_MESSAGE_CHARS}</span>
      </div>
      <button type="button" className="btn btn--primary" onClick={submit} disabled={disabled || !text.trim()} aria-label="Send message">
        <Send size={16} aria-hidden="true" />
      </button>
    </footer>
  );
}
