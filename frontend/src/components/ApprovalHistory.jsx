import StatusBadge from "./StatusBadge";
import { REJECTION_REASON_LABELS } from "../utils/constants";
import { formatDateTime } from "../utils/format";

const reasonLabel = (value) => REJECTION_REASON_LABELS[value] ?? value;

/** SYSTEM rows: auto-approval by the policy rules, or rejection by the receipt check */
function reviewerName(a) {
  if (a.reviewer_type !== "SYSTEM") return a.reviewer_name;
  return a.decision === "REJECTED" ? "Automated receipt check" : "Policy rules (automatic)";
}

/** Decision history with review comments (trip or ticket) */
export default function ApprovalHistory({ approvals = [] }) {
  if (approvals.length === 0) return <p className="muted">No decisions yet.</p>;
  return (
    <ol className="history">
      {approvals.map((a) => (
        <li key={a.approval_id} className="history__item">
          <div className="history__top">
            <StatusBadge status={a.decision} />
            <span className="muted">{formatDateTime(a.decided_at)}</span>
          </div>
          <p>by <strong>{reviewerName(a)}</strong></p>
          {a.rejection_reason && <p>Reason: {reasonLabel(a.rejection_reason)}</p>}
          {a.review_comment && <p className="history__note">"{a.review_comment}"</p>}
        </li>
      ))}
    </ol>
  );
}
