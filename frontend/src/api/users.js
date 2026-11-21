import { api } from "./client";
import { mockMe } from "./mocks";
import { USE_MOCKS } from "../utils/constants";

/** GET /me -> the signed-in employee, with the role re-read from the database */
export function getMe() {
  if (USE_MOCKS) return mockMe();
  return api.get("/me");
}
