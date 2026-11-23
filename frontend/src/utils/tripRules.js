// =====================================================================
// Helpers for fields the list endpoints don't send.
// GET /trips rows carry no can_edit / can_raise_ticket, so the buttons in
// lists derive them from the status. FastAPI still enforces every rule.
// =====================================================================
import { todayISO } from "./format";

/** Edit: only while In Progress (the list only contains the caller's own trips) */
export function canEditTrip(trip) {
  return trip.can_edit ?? trip.approval_status === "IN_PROGRESS";
}

/** Add expense: Approved - Active and before the auto-complete date */
export function canAddExpense(trip) {
  return trip.can_raise_ticket ?? (
    trip.approval_status === "APPROVED"
    && trip.trip_state === "ACTIVE"
    && (!trip.auto_complete_on || todayISO() < trip.auto_complete_on)
  );
}

/** "TKT-00004" -> 4. Display codes are generated from the id ('TKT-' || lpad(id)), so the code gives the id. */
export function idFromCode(code) {
  const n = Number(String(code ?? "").split("-").pop());
  return Number.isInteger(n) && n > 0 ? n : null;
}
