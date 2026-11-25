// The receipt check box under each photo (Spec v2.1)
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import ReceiptCheck from "../components/ReceiptCheck";
import { receiptStatusKey } from "../hooks/useReceiptCheck";

const done = (result) => ({ status: "done", result: { enabled: true, checks: [], ...result }, retry: vi.fn() });

describe("ReceiptCheck", () => {
  it("shows nothing before a photo is added", () => {
    const { container } = render(<ReceiptCheck check={{ status: "idle" }} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows progress while the receipt is read", () => {
    render(<ReceiptCheck check={{ status: "checking" }} />);
    expect(screen.getByText(/checking receipt/i)).toBeInTheDocument();
  });

  it("shows a verified receipt with what was read", () => {
    render(<ReceiptCheck check={done({
      verdict: "VALID", outcome: "Receipt verified.",
      reading: { status: "READ", merchant: "Hotel Blue", total_amount: 1850, receipt_date: "2026-11-24", city: "Bengaluru" },
    })} />);
    expect(screen.getByText("Receipt verified", { selector: "p" })).toBeInTheDocument();
    expect(screen.getByText(/Hotel Blue/)).toBeInTheDocument();
  });

  it("warns under the threshold and lists the failed checks", () => {
    render(<ReceiptCheck check={done({
      verdict: "INVALID", over_threshold: false, outcome: "The line will go to your manager for review.",
      checks: [
        { check: "AMOUNT", result: "FAIL", message: "Receipt total is Rs 2,400.00, but Rs 1,850.00 was entered" },
        { check: "DATE", result: "PASS", message: "Receipt date matches" },
      ],
    })} />);
    expect(screen.getByText(/doesn't match this line/i)).toBeInTheDocument();
    expect(screen.getByText(/Rs 2,400.00/)).toBeInTheDocument();
    expect(screen.queryByText(/Receipt date matches/)).not.toBeInTheDocument();
  });

  it("says the line will be rejected above the threshold", () => {
    render(<ReceiptCheck check={done({ verdict: "INVALID", over_threshold: true, outcome: "Rejected automatically." })} />);
    expect(screen.getByText(/will be rejected by the receipt check/i)).toBeInTheDocument();
  });

  it("asks for a clearer photo when unreadable", async () => {
    const onReplace = vi.fn();
    render(<ReceiptCheck check={done({ verdict: "UNREADABLE", outcome: "Upload a clearer photo." })} onReplace={onReplace} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Replace photo" }));
    expect(onReplace).toHaveBeenCalled();
  });

  it("shows nothing when the feature is switched off", () => {
    const { container } = render(<ReceiptCheck check={done({ verdict: "NOT_VERIFIED", enabled: false, outcome: "" })} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("maps states to the keys the page uses to block Submit", () => {
    expect(receiptStatusKey({ status: "checking" })).toBe("checking");
    expect(receiptStatusKey(done({ verdict: "UNREADABLE" }))).toBe("UNREADABLE");
    expect(receiptStatusKey(done({ verdict: "INVALID", over_threshold: true }))).toBe("INVALID_OVER");
    expect(receiptStatusKey(done({ verdict: "VALID", enabled: false }))).toBe("none");
  });
});
