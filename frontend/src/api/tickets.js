import { api } from "./client";
import { USE_MOCKS } from "../utils/constants";
import { mockCreateTicket, mockDecideTicket, mockGetTicket, mockListPendingTickets } from "./mocks";

/** GET /tickets/pending (Manager) */
export function listPendingTickets() {
  if (USE_MOCKS) return mockListPendingTickets();
  return api.get("/tickets/pending");
}

/** POST /trips/{id}/tickets  body: { expenses: [...], replacement_of_ticket_id? } */
export function createTicket(tripId, body) {
  if (USE_MOCKS) return mockCreateTicket(tripId, body);
  return api.post(`/trips/${tripId}/tickets`, body);
}

/** GET /tickets/{id} (owner or approving manager) */
export function getTicket(ticketId) {
  if (USE_MOCKS) return mockGetTicket(ticketId);
  return api.get(`/tickets/${ticketId}`);
}

/** POST /tickets/{id}/decision  body: { decision, rejection_reason?, review_comment } */
export function decideTicket(ticketId, body) {
  if (USE_MOCKS) return mockDecideTicket(ticketId, body);
  return api.post(`/tickets/${ticketId}/decision`, body);
}
