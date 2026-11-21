import { api } from "./client";
import { USE_MOCKS } from "../utils/constants";
import { mockChatClose, mockChatCreate, mockChatHistory, mockChatList, mockChatSend } from "./mocks";

/**
 * The ONLY place that knows Vera's reply shape.
 * If Piyush's field names differ, change them here and nowhere else.
 */
export function normalizeReply(r) {
  return {
    text: r.reply ?? "",                      // plain text with line breaks
    intent: r.intent ?? null,                 // POLICY | WEATHER | POLICY_AND_WEATHER | GREETING | OUT_OF_SCOPE
    citations: r.citations ?? [],             // [{ ref_id, title, similarity }]
    tools: r.tools_used ?? [],                // [{ tool_name, status, error_code, latency_ms }]
    weather: r.weather ?? null,               // VeraWeatherAnswer or null
    status: r.status,                         // COMPLETED | PARTIAL | BLOCKED | FAILED
    errorCode: r.error_code ?? null,
    retryable: Boolean(r.retryable),
    guardrail: r.guardrail_status ?? null,
  };
}

/** Stored messages -> chat bubbles (only the employee's messages and Vera's answers) */
export function historyToItems(history) {
  return history.messages
    .filter((m) => m.message_type === "human_message" || m.message_type === "ai_response")
    .map((m) => ({
      id: m.message_id,
      role: m.message_type === "human_message" ? "user" : "ai",
      text: m.content,
      citations: m.metadata?.citations ?? [],
      weather: m.metadata?.weather ?? m.metadata?.weather_card ?? null,
    }));
}

/** POST /chat/sessions -> new session (closes any other active one) */
export function createChatSession() {
  if (USE_MOCKS) return mockChatCreate();
  return api.post("/chat/sessions");
}

/** POST /chat/sessions/{id}/messages  body: { message } */
export function sendChatMessage(sessionId, message) {
  if (USE_MOCKS) return mockChatSend(sessionId, message);
  return api.post(`/chat/sessions/${sessionId}/messages`, { message });
}

/** GET /chat/sessions -> the employee's sessions (Past chats) */
export function listChatSessions() {
  if (USE_MOCKS) return mockChatList();
  return api.get("/chat/sessions");
}

/** GET /chat/sessions/{id}/messages -> read-only transcript */
export function getChatHistory(sessionId) {
  if (USE_MOCKS) return mockChatHistory(sessionId);
  return api.get(`/chat/sessions/${sessionId}/messages`);
}

/** POST /chat/sessions/{id}/close (the X button) */
export function closeChatSession(sessionId) {
  if (USE_MOCKS) return mockChatClose(sessionId);
  return api.post(`/chat/sessions/${sessionId}/close`);
}
