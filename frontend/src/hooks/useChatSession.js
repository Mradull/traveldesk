import { useCallback, useEffect, useRef, useState } from "react";
import { closeChatSession, createChatSession, normalizeReply, sendChatMessage } from "../api/chat";

let nextItemId = 0;
const makeItem = (fields) => ({ id: `ui-${++nextItemId}`, ...fields });
const SESSION_ENDED = ["SESSION_EXPIRED", "SESSION_CLOSED"];

/**
 * One Vera session per open window.
 * - Opening creates a new session (no memory of earlier chats).
 * - On 410 (expired or closed) it starts a new session, shows a notice and resends ONCE.
 * - A FAILED/PARTIAL answer with retryable: true gets a Retry button.
 * - close() is called by the X button.
 */
export function useChatSession() {
  const sessionRef = useRef(null);
  const startedRef = useRef(false); // React StrictMode runs effects twice in development
  const [items, setItems] = useState([]);
  const [starting, setStarting] = useState(true);
  const [sending, setSending] = useState(false);
  const [startError, setStartError] = useState(null);

  const add = (...newItems) => setItems((list) => [...list, ...newItems]);

  const startSession = useCallback(async () => {
    setStarting(true);
    setStartError(null);
    try {
      const session = await createChatSession();
      sessionRef.current = session.session_id;
      return session;
    } catch (err) {
      setStartError(err);
      return null;
    } finally {
      setStarting(false);
    }
  }, []);

  const openNew = useCallback(async () => {
    const session = await startSession();
    if (session) setItems([makeItem({ role: "ai", text: session.intro_message })]);
  }, [startSession]);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    openNew();
  }, [openNew]);

  const deliver = useCallback(async (message, echo) => {
    if (echo) add(makeItem({ role: "user", text: message }));
    setSending(true);
    try {
      let reply;
      try {
        reply = await sendChatMessage(sessionRef.current, message);
      } catch (err) {
        if (!SESSION_ENDED.includes(err.code)) throw err;
        const session = await startSession();
        if (!session) throw err;
        add(makeItem({ role: "notice", text: "Started a new chat (the previous one ended)." }));
        reply = await sendChatMessage(sessionRef.current, message); // resend once
      }
      const answer = normalizeReply(reply);
      // A tool failure (e.g. weather timeout) comes back as HTTP 200 with status FAILED/PARTIAL and retryable: true
      const canRetry = ["FAILED", "PARTIAL"].includes(answer.status) && answer.retryable;
      add(makeItem({ role: "ai", ...answer, retryText: canRetry ? message : null }));
    } catch (err) {
      const canRetry = !["VALIDATION_ERROR", "FORBIDDEN"].includes(err.code);
      add(makeItem({ role: "error", text: err.message, retryText: canRetry ? message : null }));
    } finally {
      setSending(false);
    }
  }, [startSession]);

  const send = useCallback((text) => {
    const message = text.trim();
    if (message && sessionRef.current) deliver(message, true);
  }, [deliver]);

  const retry = useCallback((errorItem) => {
    setItems((list) => list.filter((i) => i.id !== errorItem.id));
    deliver(errorItem.retryText, false);
  }, [deliver]);

  const close = useCallback(async () => {
    const id = sessionRef.current;
    sessionRef.current = null;
    if (!id) return;
    try {
      await closeChatSession(id);
    } catch {
      /* closing is best effort; the backend expires idle sessions anyway */
    }
  }, []);

  return { items, starting, sending, startError, send, retry, close, retryStart: openNew };
}
