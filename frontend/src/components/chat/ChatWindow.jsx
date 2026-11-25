import { useState } from "react";
import { ArrowLeft, History, X } from "lucide-react";
import { useChatSession } from "../../hooks/useChatSession";
import Loader from "../Loader";
import MessageList from "./MessageList";
import ChatInput from "./ChatInput";
import PastChatsList from "./PastChatsList";
import ChatTranscript from "./ChatTranscript";

const SUBTITLES = { chat: "TravelDesk assistant", past: "Past chats", transcript: "Transcript" };

export default function ChatWindow({ onClose }) {
  const chat = useChatSession();
  const [view, setView] = useState("chat"); // chat | past | transcript
  const [transcriptId, setTranscriptId] = useState(null);

  async function handleClose() {
    await chat.close(); // X ends the session (CLOSED, USER_CLOSED)
    onClose();
  }

  return (
    <section className="chat-window" role="dialog" aria-label="Vera - TravelDesk assistant">
      <header className="chat-window__header">
        <div className="chat-window__title">
          {view !== "chat" && (
            <button type="button" className="icon-btn" onClick={() => setView(view === "transcript" ? "past" : "chat")} aria-label="Back">
              <ArrowLeft size={18} aria-hidden="true" />
            </button>
          )}
          <div><strong>Vera</strong><span>{SUBTITLES[view]}</span></div>
        </div>
        <div className="chat-window__actions">
          {view === "chat" && (
            <button type="button" className="icon-btn" onClick={() => setView("past")} aria-label="Past chats" title="Past chats">
              <History size={18} aria-hidden="true" />
            </button>
          )}
          <button type="button" className="icon-btn" onClick={handleClose} aria-label="Close chat">
            <X size={18} aria-hidden="true" />
          </button>
        </div>
      </header>

      {view === "chat" && (
        <>
          {chat.starting && <div className="chat-window__body"><Loader label="Starting a chat…" /></div>}
          {!chat.starting && chat.startError && (
            <div className="chat-window__body">
              <div className="bubble bubble--error">
                <p>{chat.startError.message}</p>
                <button type="button" className="btn btn--secondary btn--small" onClick={chat.retryStart}>Retry</button>
              </div>
            </div>
          )}
          {!chat.starting && !chat.startError && (
            <MessageList items={chat.items} sending={chat.sending} onRetry={chat.retry} onSuggest={chat.send} />
          )}
          <ChatInput onSend={chat.send} disabled={chat.starting || chat.sending || Boolean(chat.startError)} />
        </>
      )}

      {view === "past" && <PastChatsList onOpen={(id) => { setTranscriptId(id); setView("transcript"); }} />}
      {view === "transcript" && transcriptId && <ChatTranscript sessionId={transcriptId} />}
    </section>
  );
}
