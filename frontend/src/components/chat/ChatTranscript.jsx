import { useApi } from "../../hooks/useApi";
import { getChatHistory, historyToItems } from "../../api/chat";
import Loader from "../Loader";
import ErrorBanner from "../ErrorBanner";
import MessageBubble from "./MessageBubble";

/** Read-only view of an ended chat. It is never loaded into a new session. */
export default function ChatTranscript({ sessionId }) {
  const { data, error, loading, reload } = useApi(() => getChatHistory(sessionId), [sessionId]);

  return (
    <div className="chat-window__body" role="log">
      {loading && <Loader label="Loading chat…" />}
      {!loading && error && <ErrorBanner error={error} onRetry={reload} />}
      {!loading && !error && data && (
        <>
          <p className="chat-notice">Read-only transcript</p>
          {historyToItems(data).map((item) => <MessageBubble key={item.id} item={item} />)}
        </>
      )}
    </div>
  );
}
