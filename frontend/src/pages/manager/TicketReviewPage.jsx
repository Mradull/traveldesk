// /manager/tickets/:id: trip details, lines, photos, flags; Approve (comment optional) or Reject (reason + comment).
// Owner: Mradul (M3)  |  Managers see no weather and no AI output.
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApi } from "../../hooks/useApi";
import { decideTicket, getTicket } from "../../api/tickets";
import { getTrip } from "../../api/trips";
import { formatDateRange, formatDateTime, formatINR } from "../../utils/format";
import Loader from "../../components/Loader";
import ErrorBanner from "../../components/ErrorBanner";
import StatusBadge from "../../components/StatusBadge";
import ReadOnlyBanner from "../../components/ReadOnlyBanner";
import TicketLines from "../../components/TicketLines";
import ApprovalHistory from "../../components/ApprovalHistory";
import DecisionPanel from "../../components/DecisionPanel";

export default function TicketReviewPage() {
  const { ticketId } = useParams();
  const { data: ticket, error, loading, reload, setData } = useApi(() => getTicket(ticketId), [ticketId]);
  // A ticket has no trip dates/purpose/status, so load its trip separately
  const tripReq = useApi(() => (ticket ? getTrip(ticket.trip_id) : Promise.resolve(null)), [ticket?.trip_id]);
  const trip = tripReq.data;
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [message, setMessage] = useState(null);

  if (loading) return <Loader label="Loading ticket…" />;
  if (error) return <ErrorBanner error={error} onRetry={reload} />;
  if (!ticket) return null;

  async function handleDecide(body) {
    setBusy(true);
    setActionError(null);
    try {
      setData(await decideTicket(ticket.ticket_id, body));
      setMessage(body.decision === "APPROVED"
        ? "Ticket approved."
        : "Ticket rejected. The employee can see your reason and comment and raise a new ticket.");
    } catch (err) {
      setActionError(err);
      if (err.code === "ALREADY_DECIDED") reload();
    } finally {
      setBusy(false);
    }
  }

  const pending = ticket.status === "PENDING";

  return (
    <section>
      <Link to="/manager/approvals?tab=tickets" className="back-link">← Expense tickets</Link>

      <div className="page-header">
        <div>
          <p className="trip-card__code">{ticket.employee_name}, {ticket.trip_code}</p>
          <h1>{ticket.ticket_code}</h1>
          <StatusBadge status={ticket.status} />
        </div>
      </div>

      {message && <div className="alert alert--info"><p>{message}</p></div>}
      <ErrorBanner error={actionError} />
      {!pending && <ReadOnlyBanner />}

      <div className="detail-grid">
        <div className="stack">
          <div className="card">
            <h2>Trip</h2>
            <dl className="details">
              <dt>Trip</dt><dd><Link to={`/manager/trips/${ticket.trip_id}`}>{ticket.trip_code}</Link>, {ticket.destination}</dd>
              {trip && (
                <>
                  <dt>Dates</dt><dd>{formatDateRange(trip.start_date, trip.end_date)}</dd>
                  <dt>Purpose</dt><dd>{trip.purpose}</dd>
                  <dt>Trip status</dt><dd><StatusBadge status={trip.status_label} /></dd>
                </>
              )}
              {tripReq.loading && <><dt>Dates</dt><dd className="muted">Loading…</dd></>}
            </dl>
          </div>
          <div className="card">
            <h2>Expense lines</h2>
            <TicketLines expenses={ticket.expenses} />
          </div>
        </div>

        <aside className="stack">
          {pending && (
            <DecisionPanel
              title="Decide on this ticket"
              hint="Approve with an optional comment, or reject with a reason and a comment."
              onDecide={handleDecide}
              deciding={busy}
              withReason
            />
          )}
          <div className="card">
            <h2>Summary</h2>
            <dl className="details">
              <dt>Employee</dt><dd>{ticket.employee_name}</dd>
              <dt>Submitted</dt><dd>{formatDateTime(ticket.submitted_at)}</dd>
              <dt>Lines</dt><dd>{ticket.line_count}</dd>
              <dt>Flags</dt><dd>{ticket.flag_count}</dd>
              <dt>Total</dt><dd><strong>{formatINR(ticket.total_amount)}</strong></dd>
            </dl>
          </div>
          <div className="card">
            <h2>Decision history</h2>
            <ApprovalHistory approvals={ticket.history} />
          </div>
        </aside>
      </div>
    </section>
  );
}
