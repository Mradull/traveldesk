// Each role only reaches its own view; signed-out users go to the login page.
import { screen } from "@testing-library/react";
import { renderAt } from "./testUtils";

describe("Route guards", () => {
  it("sends a signed-out user to the login page", async () => {
    renderAt("/trips", null);
    expect(await screen.findByRole("heading", { name: "TravelDesk" })).toBeInTheDocument();
  });

  it("sends an employee home to the Dashboard", async () => {
    renderAt("/", "EMPLOYEE");
    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
  });

  it("sends a manager home to Approvals", async () => {
    renderAt("/", "MANAGER");
    expect(await screen.findByRole("heading", { name: "Approvals" })).toBeInTheDocument();
  });

  it("keeps an employee out of manager pages", async () => {
    renderAt("/manager/approvals", "EMPLOYEE");
    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Approvals" })).not.toBeInTheDocument();
  });

  it("keeps a manager out of employee pages", async () => {
    renderAt("/trips/new", "MANAGER");
    expect(await screen.findByRole("heading", { name: "Approvals" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "New travel request" })).not.toBeInTheDocument();
  });

  it("shows managers no Create Trip link", async () => {
    renderAt("/manager/approvals", "MANAGER");
    await screen.findByRole("heading", { name: "Approvals" });
    expect(screen.queryByRole("link", { name: /create trip/i })).not.toBeInTheDocument();
  });
});
