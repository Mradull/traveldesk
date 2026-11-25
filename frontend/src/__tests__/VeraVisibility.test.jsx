// The Vera chat icon appears ONLY on My Trips, Trip Detail and the Add expense page, and never for managers.
import { screen } from "@testing-library/react";
import { renderAt } from "./testUtils";

const VERA = { name: /open vera/i };

describe("Vera visibility", () => {
  it("shows the Vera icon on My Trips", async () => {
    renderAt("/trips", "EMPLOYEE");
    expect(await screen.findByRole("button", VERA)).toBeInTheDocument();
  });

  it("shows the Vera icon on Trip Detail", async () => {
    renderAt("/trips/2", "EMPLOYEE");
    await screen.findByRole("heading", { name: "Bengaluru", level: 1 });
    expect(screen.getByRole("button", VERA)).toBeInTheDocument();
  });

  it("shows the Vera icon on the Add expense page", async () => {
    renderAt("/trips/2/expenses/new", "EMPLOYEE");
    await screen.findByRole("heading", { name: "Add expenses", level: 1 });
    expect(screen.getByRole("button", VERA)).toBeInTheDocument();
  });

  const employeePagesWithoutVera = [
    ["/dashboard", "Dashboard"],
    ["/trips/new", "New travel request"],
    ["/tickets/3", "TKT-00003"],
  ];

  it.each(employeePagesWithoutVera)("hides the Vera icon on %s", async (path, heading) => {
    renderAt(path, "EMPLOYEE");
    await screen.findByRole("heading", { name: heading, level: 1 });
    expect(screen.queryByRole("button", VERA)).not.toBeInTheDocument();
  });

  const managerPages = [
    ["/manager/approvals", "Approvals"],
    ["/manager/trips/2", "Bengaluru"],
    ["/manager/tickets/3", "TKT-00003"],
    ["/manager/reports", "Spending Summary"],
  ];

  it.each(managerPages)("never shows the Vera icon to a manager on %s", async (path, heading) => {
    renderAt(path, "MANAGER");
    await screen.findByRole("heading", { name: heading, level: 1 });
    expect(screen.queryByRole("button", VERA)).not.toBeInTheDocument();
  });
});
