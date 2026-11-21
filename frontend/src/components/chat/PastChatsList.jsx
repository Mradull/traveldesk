import { useApi } from "../../hooks/useApi";
import { listChatSessions } from "../../api/chat";
import { formatDateTime } from "../../utils/format";
import Loader from "../Loader";
import ErrorBanner from "../ErrorBanner";

/** Ended chats only; opening one shows a read-only transcript */
export default function PastChatsList({ onOpen }) {
  const { data, error, loading, reload } = useApi(() => listChatSessions(), []);
  const ended = (data ?? []).filter((s) => s.status !== "ACTIVE");

  return (
    <div className="chat-window__body">
      {loading && <Loader label="Loading past chats…" />}
      {!loading && error && <ErrorBanner error={error} onRetry={reload} />}
      {!loading && !error && ended.length === 0 && <p className="muted">No past chats yet.</p>}
      {!loading && !error && ended.length > 0 && (
        <ul className="past-chats">
          {ended.map((s) => (
            <li key={s.session_id}>
              <button type="button" className="past-chats__item" onClick={() => onOpen(s.session_id)}>
                <span>{s.first_message_preview || "Chat with no messages"}</span>
                <span className="muted small">
                  {formatDateTime(s.started_at)}, {s.turn_count} {s.turn_count === 1 ? "message" : "messages"}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
