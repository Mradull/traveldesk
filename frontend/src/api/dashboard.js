import { api } from "./client";
import { USE_MOCKS } from "../utils/constants";
import { mockGetEmployeeDashboard } from "./mocks";

/** GET /dashboard/employee -> KPIs, recent trips, spend by category (new endpoint: ask Joyal) */
export function getEmployeeDashboard() {
  if (USE_MOCKS) return mockGetEmployeeDashboard();
  return api.get("/dashboard/employee");
}
