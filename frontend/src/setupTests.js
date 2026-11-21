// Runs before every test file.
import "@testing-library/jest-dom/vitest"; // adds toBeInTheDocument(), toBeDisabled(), ...
import { vi } from "vitest";

// Tests never call FastAPI: the signed-in user and every API module are replaced with fake data.
vi.mock("./context/AuthContext", async () => {
  const { mockAuth } = await import("./__tests__/fixtures");
  return { useAuth: () => mockAuth, AuthProvider: ({ children }) => children };
});

vi.mock("./api/trips", async () => {
  const { TRIP } = await import("./__tests__/fixtures");
  return {
    listMyTrips: vi.fn(async () => [TRIP]),
    getTrip: vi.fn(async () => TRIP),
    createTrip: vi.fn(), updateTrip: vi.fn(), decideTrip: vi.fn(), completeTrip: vi.fn(),
    listPendingTrips: vi.fn(async () => []),
    listTripsToComplete: vi.fn(async () => []),
  };
});

vi.mock("./api/tickets", async () => {
  const { TICKET } = await import("./__tests__/fixtures");
  return {
    listPendingTickets: vi.fn(async () => []),
    getTicket: vi.fn(async () => TICKET),
    createTicket: vi.fn(), decideTicket: vi.fn(),
  };
});

vi.mock("./api/dashboard", async () => {
  const { DASHBOARD } = await import("./__tests__/fixtures");
  return { getEmployeeDashboard: vi.fn(async () => DASHBOARD) };
});

vi.mock("./api/policy", () => ({ getPolicyRules: vi.fn(async () => ({ review_thresholds_inr: { MEALS: 1500 } })) }));
vi.mock("./api/reports", () => ({
  getTripExpenseReport: vi.fn(async () => []),
  getSpendByTripCategory: vi.fn(async () => []),
}));
vi.mock("./api/expenses", () => ({ listPendingExpenses: vi.fn(async () => []) }));
