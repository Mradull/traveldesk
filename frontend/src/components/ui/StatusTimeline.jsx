// Status timeline (#3): where a trip or ticket is in its life cycle.
import { Check, X } from "lucide-react";

/** steps: [{ label, state: "done" | "current" | "todo" | "rejected", note? }] */
export function StatusTimeline({ steps, label }) {
  return (
    <ol className="timeline" aria-label={label}>
      {steps.map((s, i) => (
        <li key={s.label} className={`timeline__step timeline__step--${s.state}`} aria-current={s.state === "current" ? "step" : undefined}>
          <span className="timeline__dot" aria-hidden="true">
            {s.state === "done" && <Check size={14} />}
            {s.state === "rejected" && <X size={14} />}
            {(s.state === "current" || s.state === "todo") && i + 1}
          </span>
          <span className="timeline__label">{s.label}</span>
          {s.note && <span className="timeline__note">{s.note}</span>}
          <span className="sr-only">{{ done: "completed", current: "in progress", todo: "not started", rejected: "rejected" }[s.state]}</span>
        </li>
      ))}
    </ol>
  );
}

/** Trip: Requested -> Manager decision -> Active -> Completed (or Rejected) */
export function tripSteps(trip) {
  if (trip.approval_status === "REJECTED") {
    return [{ label: "Requested", state: "done" }, { label: "Rejected", state: "rejected" }];
  }
  const approved = trip.approval_status === "APPROVED";
  const completed = trip.trip_state === "COMPLETED";
  return [
    { label: "Requested", state: "done" },
    { label: "Manager approval", state: approved ? "done" : "current" },
    { label: "Active", state: completed ? "done" : approved ? "current" : "todo", note: approved && !completed ? "Add expenses" : undefined },
    { label: "Completed", state: completed ? "done" : "todo" },
  ];
}

/** Ticket: Submitted -> Receipt check -> Review -> Decision */
export function ticketSteps(ticket) {
  const hasCheck = ticket.expenses?.some((l) => l.receipt_verdict);
  const decided = ticket.status !== "PENDING";
  const steps = [{ label: "Submitted", state: "done" }];
  if (hasCheck) {
    const failed = ticket.routing === "AI_CHECK";
    steps.push({ label: "Receipt check", state: failed ? "rejected" : "done" });
    if (failed) return steps;
  }
  if (ticket.routing === "AUTO") {
    steps.push({ label: "Policy rules", state: "done", note: "No flags" });
    steps.push({ label: "Auto-approved", state: "done" });
    return steps;
  }
  steps.push({ label: "Manager review", state: decided ? "done" : "current" });
  steps.push({
    label: ticket.status === "REJECTED" ? "Rejected" : ticket.status === "APPROVED" ? "Approved" : "Decision",
    state: ticket.status === "REJECTED" ? "rejected" : decided ? "done" : "todo",
  });
  return steps;
}
