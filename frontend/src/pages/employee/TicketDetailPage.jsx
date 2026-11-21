// /tickets/:id: lines, photos, flags, decision with reason and comment; Create new ticket when rejected.
// Owner: Mradul (M3)
import { Link, useParams } from "react-router-dom";
import { useApi } from "../../hooks/useApi";
import { getTicket } from "../../api/tickets";
import { REJECTION_REASONS } from "../../utils/constants";
import { formatDateTime, formatINR } from "../../utils/format";
import Loader from "../../components/Loader";
import ErrorBanner from "../../components/ErrorBanner";
import StatusBadge from "../../components/StatusBadge";
import ReadOnlyBanner from "../../components/ReadOnlyBanner";
import TicketLines from "../../components/TicketLines";
import ApprovalHistory from "../../components/ApprovalHistory";

const reasonLabel = (value) => REJECTION_REASONS.find((r) => r.value === value)?.label ?? value;

export default function TicketDetailPage() {
  const { ticketId } = useParams();
  const { data: ticket, error, loading, reload } = useApi(() => getTicket(ticketId), [ticketId]);

  if (loading) return <Loader label="Loading ticket…" />;
  if (error) return <ErrorBanner error={error} onRetry={reload} />;
  if (!ticket) return null;

  const decided = ticket.status !== "PENDING";
  const managerDecision = ticket.history.find((h) => h.reviewer_type === "MANAGER");
  const replaceUrl = `/trips/${ticket.trip_id}/expenses/new?replaces=${ticket.ticket_id}`;

  return (
    <section>
      <Link to={`/trips/${ticket.trip_id}`} className="back-link">← {ticket.trip_code}, {ticket.destination}</Link>

      <div className="page-header">
        <div>
          <p className="trip-card__code">{ticket.trip_code}, {ticket.destination}</p>
          <h1>{ticket.ticket_code}</h1>
          <StatusBadge status={ticket.status} />
        </div>
        {ticket.can_replace && <Link className="btn btn--primary" to={replaceUrl}>Create new ticket</Link>}
      </div>

      {(ticket.replaces_ticket_code || ticket.replaced_by_ticket_code) && (
        <div className="replace-links">
          {ticket.replaces_ticket_code && (
            <span>Replaces <Link to={`/tickets/${ticket.replacement_of_ticket_id}`}>{ticket.replaces_ticket_code}</Link></span>
          )}
          {ticket.replaced_by_ticket_code && (
            <span>Replaced by <Link to={`/tickets/${ticket.replaced_by_ticket_id}`}>{ticket.replaced_by_ticket_code}</Link></span>
          )}
        </div>
      )}

      {ticket.status === "REJECTED" && managerDecision && (
        <div className="alert alert--error">
          <div>
            <p><strong>Rejected by {managerDecision.reviewer_name}: {reasonLabel(managerDecision.rejection_reason)}</strong></p>
            <p>{managerDecision.review_comment}</p>
            {ticket.can_replace && (
              <p className="small">To correct it, create a new ticket and upload clear photos again. This ticket stays unchanged.</p>
            )}
            {!ticket.can_replace && !ticket.replaced_by_ticket_code && (
              <p className="small">The trip is no longer active, so a new ticket can't be created.</p>
            )}
          </div>
        </div>
      )}

      {ticket.status === "PENDING" && (
        <div className="alert alert--info"><p>Some lines were flagged, so this ticket is waiting for your manager's review.</p></div>
      )}
      {decided && <ReadOnlyBanner />}

      <div className="detail-grid">
        <div className="stack">
          <div className="card">
            <h2>Expense lines</h2>
            <TicketLines expenses={ticket.expenses} />
          </div>
        </div>

        <aside className="stack">
          <div className="card">
            <h2>Summary</h2>
            <dl className="details">
              <dt>Trip</dt><dd>{ticket.trip_code}, {ticket.destination}</dd>
              <dt>Submitted</dt><dd>{formatDateTime(ticket.submitted_at)}</dd>
              <dt>Lines</dt><dd>{ticket.line_count}</dd>
              <dt>Flags</dt><dd>{ticket.flag_count}</dd>
              <dt>Routing</dt><dd>{ticket.routing === "AUTO" ? "Policy engine (no flags)" : "Manager review"}</dd>
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
