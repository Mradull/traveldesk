import { api } from "./client";
import { mockLogin } from "./mocks";
import { USE_MOCKS } from "../utils/constants";

/** POST /auth/login -> { access_token, token_type, expires_in, user } */
export function login(email, password) {
  if (USE_MOCKS) return mockLogin(email, password);
  return api.post("/auth/login", { email, password }, { auth: false });
}
