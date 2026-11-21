import { api } from "./client";
import { USE_MOCKS } from "../utils/constants";
import { mockGetPolicyRules } from "./mocks";

/** GET /policy/rules -> thresholds, limits, rules_version */
export function getPolicyRules() {
  if (USE_MOCKS) return mockGetPolicyRules();
  return api.get("/policy/rules");
}
