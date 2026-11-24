// UI enhancements: dialogs (#2), toasts (#1), sorting/search (#9), timeline steps (#3)
import { act, render, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { UiProvider, useConfirm, useToast } from "../components/ui/UiProvider";
import { filterRows, useTableSort } from "../hooks/useTableSort";
import { ticketSteps, tripSteps } from "../components/ui/StatusTimeline";

function Demo({ onAnswer }) {
  const confirm = useConfirm();
  const toast = useToast();
  return (
    <>
      <button onClick={async () => onAnswer(await confirm({ title: "Reject TKT-00003?", message: "Sure?", confirmLabel: "Reject ticket", tone: "danger" }))}>Ask</button>
      <button onClick={() => toast("Ticket submitted")}>Toast</button>
    </>
  );
}

describe("Confirmation dialog", () => {
  it("resolves true on confirm and false on cancel / Escape", async () => {
    const user = userEvent.setup();
    const answers = [];
    render(<UiProvider><Demo onAnswer={(a) => answers.push(a)} /></UiProvider>);

    await user.click(screen.getByText("Ask"));
    expect(screen.getByRole("alertdialog", { name: "Reject TKT-00003?" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reject ticket" }));

    await user.click(screen.getByText("Ask"));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    await user.click(screen.getByText("Ask"));
    await user.keyboard("{Escape}");

    expect(answers).toEqual([true, false, false]);
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("shows a toast that can be dismissed", async () => {
    const user = userEvent.setup();
    render(<UiProvider><Demo onAnswer={() => {}} /></UiProvider>);
    await user.click(screen.getByText("Toast"));
    expect(screen.getByText("Ticket submitted")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByText("Ticket submitted")).not.toBeInTheDocument();
  });
});

describe("Sorting and search", () => {
  const rows = [{ code: "TRP-00010", amount: 500 }, { code: "TRP-00002", amount: 1500 }, { code: "TRP-00003", amount: 50 }];

  it("sorts numerically and reverses on the second click", () => {
    const { result } = renderHook(() => useTableSort(rows));
    act(() => result.current.toggle("amount"));
    expect(result.current.sorted.map((r) => r.amount)).toEqual([50, 500, 1500]);
    act(() => result.current.toggle("amount"));
    expect(result.current.sorted.map((r) => r.amount)).toEqual([1500, 500, 50]);
    act(() => result.current.toggle("code"));
    expect(result.current.sorted[0].code).toBe("TRP-00002");
  });

  it("filters across fields, case-insensitively", () => {
    const people = [{ name: "Rohan Mehta", city: "Bengaluru" }, { name: "Sara Thomas", city: "Singapore" }];
    expect(filterRows(people, "beng", ["name", "city"])).toHaveLength(1);
    expect(filterRows(people, "  ", ["name"])).toHaveLength(2);
  });
});

describe("Status timeline steps", () => {
  it("tracks a trip through approval and completion", () => {
    expect(tripSteps({ approval_status: "IN_PROGRESS" }).map((s) => s.state)).toEqual(["done", "current", "todo", "todo"]);
    expect(tripSteps({ approval_status: "APPROVED", trip_state: "ACTIVE" }).map((s) => s.state)).toEqual(["done", "done", "current", "todo"]);
    expect(tripSteps({ approval_status: "REJECTED" }).map((s) => s.label)).toEqual(["Requested", "Rejected"]);
  });

  it("shows the receipt check and the rejection by it", () => {
    const aiRejected = { status: "REJECTED", routing: "AI_CHECK", expenses: [{ receipt_verdict: "INVALID" }] };
    expect(ticketSteps(aiRejected).map((s) => [s.label, s.state])).toEqual([["Submitted", "done"], ["Receipt check", "rejected"]]);
    const pending = { status: "PENDING", routing: "MANAGER", expenses: [{ receipt_verdict: "VALID" }] };
    expect(ticketSteps(pending).map((s) => s.state)).toEqual(["done", "done", "current", "todo"]);
  });
});
