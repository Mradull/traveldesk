// Reject stays disabled until the required fields are filled (spec: reason + 10-character comment).
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import DecisionPanel from "../components/DecisionPanel";

describe("DecisionPanel", () => {
  it("keeps Reject disabled until a reason and a 10-character comment are given (tickets)", async () => {
    const user = userEvent.setup();
    const onDecide = vi.fn();
    render(<DecisionPanel onDecide={onDecide} withReason />);

    const reject = screen.getByRole("button", { name: "Reject" });
    expect(reject).toBeDisabled();

    await user.type(screen.getByRole("textbox"), "Too short");         // 9 characters
    await user.selectOptions(screen.getByRole("combobox"), "INSUFFICIENT_EVIDENCE");
    expect(reject).toBeDisabled();

    await user.type(screen.getByRole("textbox"), "!");                 // now 10 characters
    expect(reject).toBeEnabled();

    await user.click(reject);
    expect(onDecide).toHaveBeenCalledWith({
      decision: "REJECTED", review_comment: "Too short!", rejection_reason: "INSUFFICIENT_EVIDENCE",
    });
  });

  it("needs only the comment for trips (no reason list)", async () => {
    const user = userEvent.setup();
    render(<DecisionPanel onDecide={vi.fn()} />);
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    await user.type(screen.getByRole("textbox"), "Dates clash with the audit week");
    expect(screen.getByRole("button", { name: "Reject" })).toBeEnabled();
  });

  it("allows Approve without a comment", async () => {
    const user = userEvent.setup();
    const onDecide = vi.fn();
    render(<DecisionPanel onDecide={onDecide} withReason />);
    await user.click(screen.getByRole("button", { name: "Approve" }));
    expect(onDecide).toHaveBeenCalledWith({ decision: "APPROVED", review_comment: null });
  });
});
