import { api } from "./client";
import { USE_MOCKS } from "../utils/constants";
import { mockGetEmployeeDashboard } from "./mocks";
import { listMyTrips } from "./trips";

/**
 * Builds the dashboard numbers in the browser from GET /trips and GET /trips/{id}/expenses.
 * Used only while the backend has no GET /dashboard/employee (it answers 404).
 */
async function buildDashboardFromTrips() {
  const trips = await listMyTrips({ when: "all" });
  const expenseLists = await Promise.all(
    trips.map((t) => api.get(`/trips/${t.trip_id}/expenses`).catch(() => [])),
  );
  const claimed = expenseLists.flat().filter((e) => e.status !== "REJECTED");

  const byCategory = {};
  claimed.forEach((e) => {
    byCategory[e.expense_type] = (byCategory[e.expense_type] ?? 0) + Number(e.amount);
  });

  return {
    total_trips: trips.length,
    open_trips: trips.filter((t) => t.approval_status === "APPROVED" && t.trip_state === "ACTIVE").length,
    pending_trip_approval: trips.filter((t) => t.approval_status === "IN_PROGRESS").length,
    total_claimed: claimed.reduce((s, e) => s + Number(e.amount), 0),
    recent_trips: [...trips]
      .sort((a, b) => String(b.created_at ?? b.start_date).localeCompare(String(a.created_at ?? a.start_date)))
      .slice(0, 5),
    spend_by_category: Object.entries(byCategory)
      .map(([expense_type, total_amount]) => ({ expense_type, total_amount }))
      .sort((a, b) => b.total_amount - a.total_amount),
  };
}

/** GET /dashboard/employee, with a fallback until Joyal adds the endpoint */
export async function getEmployeeDashboard() {
  if (USE_MOCKS) return mockGetEmployeeDashboard();
  try {
    return await api.get("/dashboard/employee");
  } catch (err) {
    if (err.status === 404) return buildDashboardFromTrips();
    throw err;
  }
}