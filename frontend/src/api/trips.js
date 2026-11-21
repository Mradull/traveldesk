import { api } from "./client";
import { USE_MOCKS } from "../utils/constants";
import {
  mockCompleteTrip, mockCreateTrip, mockDecideTrip, mockGetTrip, mockListPendingTrips,
  mockListTrips, mockListTripsToComplete, mockUpdateTrip,
} from "./mocks";

/** GET /trips?when=upcoming|past|all (Employee, own trips) */
export function listMyTrips({ when = "all" } = {}) {
  if (USE_MOCKS) return mockListTrips({ when });
  return api.get(`/trips?when=${when}`);
}

/** POST /trips (Employee) */
export function createTrip(input) {
  if (USE_MOCKS) return mockCreateTrip(input);
  return api.post("/trips", input);
}

/** GET /trips/{id} (owner or approving manager) -> trip + approvals + tickets */
export function getTrip(tripId) {
  if (USE_MOCKS) return mockGetTrip(tripId);
  return api.get(`/trips/${tripId}`);
}

/** PUT /trips/{id} (owner, only while In Progress) */
export function updateTrip(tripId, input) {
  if (USE_MOCKS) return mockUpdateTrip(tripId, input);
  return api.put(`/trips/${tripId}`, input);
}

/** POST /trips/{id}/decision  body: { decision: "APPROVED" | "REJECTED", review_comment } */
export function decideTrip(tripId, body) {
  if (USE_MOCKS) return mockDecideTrip(tripId, body);
  return api.post(`/trips/${tripId}/decision`, body);
}

/** POST /trips/{id}/complete (approving manager, on/after end date) */
export function completeTrip(tripId) {
  if (USE_MOCKS) return mockCompleteTrip(tripId);
  return api.post(`/trips/${tripId}/complete`);
}

/** GET /trips/pending (Manager) */
export function listPendingTrips() {
  if (USE_MOCKS) return mockListPendingTrips();
  return api.get("/trips/pending");
}

/** GET /trips/to-complete (Manager) */
export function listTripsToComplete() {
  if (USE_MOCKS) return mockListTripsToComplete();
  return api.get("/trips/to-complete");
}
