// Renders the whole app at a URL as a given role, using the fake user from fixtures.js
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "../App";
import { mockAuth } from "./fixtures";

/** role: "EMPLOYEE", "MANAGER" or null (signed out) */
export function renderAt(path, role) {
  mockAuth.user = role ? { employee_id: role === "MANAGER" ? 1 : 3, full_name: "Test User", role } : null;
  mockAuth.isManager = role === "MANAGER";
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}
