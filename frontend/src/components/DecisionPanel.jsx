import { useState } from "react";
import { MIN_REVIEW_COMMENT_CHARS, REJECTION_REASONS } from "../utils/constants";

/**
 * Approve (comment optional) or Reject (comment of 10+ characters required).
 * withReason: tickets also need a rejection reason from the list.
 * Calls onDecide({ decision, review_comment, rejection_reason? }).
 */
export default function DecisionPanel({ title = "Your decision", hint, onDecide, deciding = false, withReason = false }) {
  const [comment, setComment] = useState("");
  const [reason, setReason] = useState("");

  const trimmed = comment.trim();
  const canReject = trimmed.length >= MIN_REVIEW_COMMENT_CHARS && (!withReason || Boolean(reason));

  function approve() {
    onDecide({ decision: "APPROVED", review_comment: trimmed || null });
  }

  function reject() {
    const body = { decision: "REJECTED", review_comment: trimmed };
    if (withReason) body.rejection_reason = reason;
    onDecide(body);
  }

  return (
    <div className="card decision">
      <h2>{title}</h2>
      {hint && <p className="muted">{hint}</p>}

      {withReason && (
        <label className="field">
          <span>Rejection reason <small className="muted">(required to reject)</small></span>
          <select value={reason} onChange={(e) => setReason(e.target.value)} disabled={deciding}>
            <option value="">Choose a reason…</option>
            {REJECTION_REASONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
        </label>
      )}

      <label className="field">
        <span>Review comment <small className="muted">(required to reject, {MIN_REVIEW_COMMENT_CHARS}+ characters)</small></span>
        <textarea rows={3} maxLength={500} value={comment} onChange={(e) => setComment(e.target.value)} disabled={deciding} />
        <span className="hint">{trimmed.length} / {MIN_REVIEW_COMMENT_CHARS} minimum to reject</span>
      </label>

      <div className="form-actions">
        <button type="button" className="btn btn--danger" onClick={reject} disabled={deciding || !canReject}>
          {deciding ? "Saving…" : "Reject"}
        </button>
        <button type="button" className="btn btn--success" onClick={approve} disabled={deciding}>
          {deciding ? "Saving…" : "Approve"}
        </button>
      </div>
    </div>
  );
}
