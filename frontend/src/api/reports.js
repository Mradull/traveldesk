import { api } from "./client";
import { USE_MOCKS } from "../utils/constants";
import { mockReportSpendByTripCategory, mockReportTripExpenses } from "./mocks";

/** GET /reports/trip-expenses (Manager) -> SQL demo 1 */
export function getTripExpenseReport() {
  if (USE_MOCKS) return mockReportTripExpenses();
  return api.get("/reports/trip-expenses");
}

/** GET /reports/spend-by-trip-category (Manager) -> SQL demo 2 (expense_type null = trip total row) */
export function getSpendByTripCategory() {
  if (USE_MOCKS) return mockReportSpendByTripCategory();
  return api.get("/reports/spend-by-trip-category");
}
