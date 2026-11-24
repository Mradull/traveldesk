// /trips/:id/expenses/new[?replaces=TICKET_ID]: expense lines (max 20), a receipt photo on every line.
// Owner: Mradul (M3)
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useApi } from "../../hooks/useApi";
import { getTrip } from "../../api/trips";
import { getPolicyRules } from "../../api/policy";
import { createTicket } from "../../api/tickets";
import { EXPENSE_CATEGORIES, MAX_LINES_PER_TICKET } from "../../utils/constants";
import { formatDateRange, formatINR, todayISO } from "../../utils/format";
import { fieldErrorsFromApi, validateExpenseLines } from "../../utils/validation";
import Loader from "../../components/Loader";
import ErrorBanner from "../../components/ErrorBanner";
import StatusBadge from "../../components/StatusBadge";
import PolicyFlagList from "../../components/PolicyFlagList";
import ExpenseLineEditor from "../../components/ExpenseLineEditor";

let nextUid = 0;
const newLine = () => ({
  uid: ++nextUid, expense_type: "", amount: "", expense_date: "", description: "", invoice_number: "", evidence: null,
});
const categoryLabel = (value) => EXPENSE_CATEGORIES.find((c) => c.value === value)?.label ?? value;

function TicketResult({ ticket, trip, onAnother }) {
  const auto = ticket.status === "AUTO_APPROVED";
  const allRejectedByCheck = ticket.routing === "AI_CHECK";
  const aiTicket = ticket.ai_rejected_ticket;
  const heading = allRejectedByCheck
    ? "Rejected by the receipt check"
    : auto ? "Ticket approved automatically" : "Ticket sent to your manager";
  return (
    <section className="narrow stack">
      {aiTicket && (
        <div className="alert alert--error">
          <p>
            <strong>{aiTicket.line_count === 1 ? "1 line was" : `${aiTicket.line_count} lines were`} rejected by the receipt check</strong>{" "}
            and moved to <Link to={`/tickets/${aiTicket.ticket_id}`}>{aiTicket.ticket_code}</Link>. Open it to see why and create a new ticket.
          </p>
        </div>
      )}
      <div className="card success">
        <h1>{heading}</h1>
        <p className="success__code">{ticket.ticket_code}</p>
        <p>
          <StatusBadge status={ticket.status} /> {formatINR(ticket.total_amount)}, {ticket.line_count} {ticket.line_count === 1 ? "line" : "lines"}
        </p>
        <p className="muted">
          {allRejectedByCheck
            ? "The receipts didn't match the lines above the review threshold. Open the ticket to see why and create a new one."
            : auto ? "No policy flags, so the system approved it." : "Some lines were flagged for review. Your manager will decide."}
        </p>
      </div>
      <div className="card">
        <h2>Lines</h2>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Expense</th><th>Category</th><th className="num">Amount</th><th>Photo</th><th>Policy flags</th></tr></thead>
            <tbody>
              {ticket.expenses.map((l) => (
                <tr key={l.expense_id}>
                  <td>{l.expense_code}</td>
                  <td>{categoryLabel(l.expense_type)}</td>
                  <td className="num">{formatINR(l.amount)}</td>
                  <td>{l.evidence_code}</td>
                  <td><PolicyFlagList codes={l.flags.map((f) => f.rule_code)} compact /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="form-actions">
        <Link className="btn btn--primary" to={`/tickets/${ticket.ticket_id}`}>View ticket</Link>
        <Link className="btn btn--secondary" to={`/trips/${trip.trip_id}`}>Back to trip</Link>
        <button type="button" className="btn btn--ghost" onClick={onAnother}>Add more expenses</button>
      </div>
    </section>
  );
}

export default function RaiseTicketPage() {
  const { tripId } = useParams();
  const [params] = useSearchParams();
  const replaces = params.get("replaces"); // set by "Create new ticket" on a rejected ticket

  const tripReq = useApi(() => getTrip(tripId), [tripId]);
  const rulesReq = useApi(() => getPolicyRules(), []);
  const [lines, setLines] = useState(() => [newLine()]);
  const [uploading, setUploading] = useState(0);
  const [attempted, setAttempted] = useState(false);
  const [serverErrors, setServerErrors] = useState({});
  const [submitError, setSubmitError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [receiptStatus, setReceiptStatus] = useState({}); // line uid -> "checking" | verdict | ...

  const trip = tripReq.data;
  if (tripReq.loading || rulesReq.loading) return <Loader label="Loading…" />;
  if (tripReq.error) return <ErrorBanner error={tripReq.error} onRetry={tripReq.reload} />;
  if (!trip) return null;

  if (result) {
    return (
      <TicketResult
        ticket={result}
        trip={trip}
        onAnother={() => { setResult(null); setLines([newLine()]); setAttempted(false); }}
      />
    );
  }

  if (!trip.can_raise_ticket) {
    return (
      <section className="narrow">
        <Link to={`/trips/${trip.trip_id}`} className="back-link">← {trip.trip_code}</Link>
        <div className="card">
          <h1>Expenses can't be added</h1>
          <p className="muted">Expenses can only be claimed on an Approved - Active trip. {trip.trip_code} is {trip.status_label}.</p>
        </div>
      </section>
    );
  }

  // What the API receives (amount as a number, photo as its evidence_id)
  const payload = lines.map((l) => ({
    expense_type: l.expense_type,
    amount: l.amount === "" ? "" : Number(l.amount),
    expense_date: l.expense_date,
    description: l.description.trim(),
    invoice_number: l.invoice_number.trim() || null,
    evidence_id: l.evidence?.evidence_id ?? null,
  }));
  const errors = { ...serverErrors, ...(attempted ? validateExpenseLines(payload, trip.created_on) : {}) };
  const total = lines.reduce((s, l) => s + (Number(l.amount) || 0), 0);
  const photoCount = lines.filter((l) => l.evidence).length;
  // Receipt check: wait while a photo is being read; an unreadable photo must be replaced
  const statuses = lines.map((l) => receiptStatus[l.uid]);
  const receiptsChecking = statuses.includes("checking");
  const unreadableCount = statuses.filter((s) => s === "UNREADABLE").length;
  const rejectedLines = lines.filter((l) => receiptStatus[l.uid] === "INVALID_OVER").length;
  const canSubmit = photoCount === lines.length && uploading === 0 && !submitting && !receiptsChecking && unreadableCount === 0;
  const thresholds = rulesReq.data?.review_thresholds_inr;

  function updateLine(index, next) {
    setLines((ls) => ls.map((l, i) => (i === index ? next : l)));
    setServerErrors({});
  }

  function removeLine(index) {
    setLines((ls) => ls.filter((_, i) => i !== index));
    setServerErrors({});
  }

  function receiptStatusFor(uid) {
    return (key) => setReceiptStatus((m) => ({ ...m, [uid]: key }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setAttempted(true);
    if (Object.keys(validateExpenseLines(payload, trip.created_on)).length > 0) return;

    setSubmitting(true);
    setSubmitError(null);
    setServerErrors({});
    try {
      const body = { expenses: payload };
      if (replaces) body.replacement_of_ticket_id = Number(replaces);
      setResult(await createTicket(trip.trip_id, body));
    } catch (err) {
      const fields = fieldErrorsFromApi(err);
      if (Object.keys(fields).length > 0) setServerErrors(fields);
      else setSubmitError(err);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section>
      <Link to={`/trips/${trip.trip_id}`} className="back-link">← {trip.trip_code}, {trip.destination}</Link>
      <div className="page-header">
        <div>
          <h1>Add expenses</h1>
          <p className="muted">{trip.trip_code}, {trip.destination}, {formatDateRange(trip.start_date, trip.end_date)}</p>
        </div>
      </div>

      {replaces && (
        <div className="alert alert--info">
          <p>Replaces <strong>TKT-{String(replaces).padStart(5, "0")}</strong>. Re-enter the lines and upload every photo again.</p>
        </div>
      )}

      <div className="detail-grid">
        <form id="ticket-form" className="stack" onSubmit={handleSubmit} noValidate>
          <ErrorBanner error={submitError} />
          {errors._form && <div className="alert alert--error"><p>{errors._form}</p></div>}

          {lines.map((line, i) => (
            <ExpenseLineEditor
              key={line.uid}
              index={i}
              line={line}
              onChange={(next) => updateLine(i, next)}
              onRemove={() => removeLine(i)}
              canRemove={lines.length > 1}
              errors={errors}
              thresholds={thresholds}
              minDate={trip.created_on}
              maxDate={todayISO()}
              disabled={submitting}
              onUploadingChange={(busy) => setUploading((n) => n + (busy ? 1 : -1))}
              tripId={trip.trip_id}
              onReceiptStatus={receiptStatusFor(line.uid)}
            />
          ))}

          {lines.length < MAX_LINES_PER_TICKET && (
            <button type="button" className="btn btn--secondary" onClick={() => setLines((ls) => [...ls, newLine()])} disabled={submitting}>
              + Add another line
            </button>
          )}
        </form>

        <aside className="stack sticky">
          <div className="card">
            <h2>Ticket summary</h2>
            <dl className="details">
              <dt>Lines</dt><dd>{lines.length} / {MAX_LINES_PER_TICKET}</dd>
              <dt>Photos</dt><dd>{photoCount} of {lines.length}</dd>
              <dt>Total</dt><dd><strong>{formatINR(total)}</strong></dd>
            </dl>
            <button type="submit" form="ticket-form" className="btn btn--primary btn--block" disabled={!canSubmit}>
              {submitting ? "Submitting…" : "Submit ticket"}
            </button>
            {photoCount < lines.length && <p className="hint">Submit unlocks when every line has a receipt photo.</p>}
            {receiptsChecking && <p className="hint">Checking receipts…</p>}
            {unreadableCount > 0 && <p className="field__error">Replace the receipt photo that couldn't be read.</p>}
            {rejectedLines > 0 && (
              <p className="field__warn">
                {rejectedLines === 1 ? "1 line" : `${rejectedLines} lines`} will be rejected by the receipt check on submit.
              </p>
            )}
          </div>

          {thresholds && (
            <div className="card">
              <h2>Review thresholds</h2>
              <ul className="threshold-list">
                {EXPENSE_CATEGORIES.map((c) => (
                  <li key={c.value}><span>{c.label}</span><span>{formatINR(thresholds[c.value])}</span></li>
                ))}
              </ul>
              <p className="hint">Above these, the ticket goes to your manager; equal is fine. Clean tickets are approved automatically. [POL-6.2]</p>
            </div>
          )}
        </aside>
      </div>
    </section>
  );
}
