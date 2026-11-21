import StatusBadge from "./StatusBadge";
import { REJECTION_REASONS } from "../utils/constants";
import { formatDateTime } from "../utils/format";

const reasonLabel = (value) => REJECTION_REASONS.find((r) => r.value === value)?.label ?? value;

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
          <p>by <strong>{a.reviewer_name}</strong></p>
          {a.rejection_reason && <p>Reason: {reasonLabel(a.rejection_reason)}</p>}
          {a.review_comment && <p className="history__note">"{a.review_comment}"</p>}
        </li>
      ))}
    </ol>
  );
}
