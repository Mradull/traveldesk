import { api } from "./client";
import { USE_MOCKS } from "../utils/constants";
import { mockListPendingExpenses } from "./mocks";

/** GET /expenses/pending (Manager) -> SQL demo 3: flagged lines in pending tickets */
export function listPendingExpenses() {
  if (USE_MOCKS) return mockListPendingExpenses();
  return api.get("/expenses/pending");
}
