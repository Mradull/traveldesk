// /tickets/:id: lines, photos, flags, decision with reason and comment; Create new ticket when rejected.
// Owner: Mradul (M3)
import { Link, useParams } from "react-router-dom";
import { useApi } from "../../hooks/useApi";
import { getTicket } from "../../api/tickets";
import { REJECTION_REASON_LABELS } from "../../utils/constants";
import { formatDateTime, formatINR } from "../../utils/format";
import { idFromCode } from "../../utils/tripRules";
import Loader from "../../components/Loader";
import ErrorBanner from "../../components/ErrorBanner";
import StatusBadge from "../../components/StatusBadge";
import ReadOnlyBanner from "../../components/ReadOnlyBanner";
import TicketLines from "../../components/TicketLines";
import ApprovalHistory from "../../components/ApprovalHistory";

const reasonLabel = (value) => REJECTION_REASON_LABELS[value] ?? value;

export default function TicketDetailPage() {
  const { ticketId } = useParams();
  const { data: ticket, error, loading, reload } = useApi(() => getTicket(ticketId), [ticketId]);

  if (loading) return <Loader label="Loading ticket…" />;
  if (error) return <ErrorBanner error={error} onRetry={reload} />;
  if (!ticket) return null;

  const decided = ticket.status !== "PENDING";
  // Rejected by the manager, or by the automated receipt check (SYSTEM, AI_RECEIPT_INVALID)
  const rejection = ticket.history.find((h) => h.decision === "REJECTED");
  const rejectedBy = rejection?.reviewer_type === "SYSTEM" ? "the automated receipt check" : rejection?.reviewer_name;
  const replaceUrl = `/trips/${ticket.trip_id}/expenses/new?replaces=${ticket.ticket_id}`;
  // The contract sends only the codes of linked tickets; the code gives the id
  const replacesId = ticket.replacement_of_ticket_id ?? idFromCode(ticket.replacement_of_ticket_code);
  const replacedById = ticket.replaced_by_ticket_id ?? idFromCode(ticket.replaced_by_ticket_code);

  return (
    <section>
      <Link to={`/trips/${ticket.trip_id}`} className="back-link">← {ticket.trip_code}, {ticket.destination}</Link>

      <div className="page-header">
        <div>
          <p className="trip-card__code">{ticket.trip_code}, {ticket.destination}</p>
          <h1>{ticket.ticket_code}</h1>
          <StatusBadge status={ticket.status} />
        </div>
        {ticket.can_create_replacement && <Link className="btn btn--primary" to={replaceUrl}>Create new ticket</Link>}
      </div>

      {(ticket.replacement_of_ticket_code || ticket.replaced_by_ticket_code) && (
        <div className="replace-links">
          {ticket.replacement_of_ticket_code && (
            <span>Replaces <Link to={`/tickets/${replacesId}`}>{ticket.replacement_of_ticket_code}</Link></span>
          )}
          {ticket.replaced_by_ticket_code && (
            <span>Replaced by <Link to={`/tickets/${replacedById}`}>{ticket.replaced_by_ticket_code}</Link></span>
          )}
        </div>
      )}

      {ticket.status === "REJECTED" && rejection && (
        <div className="alert alert--error">
          <div>
            <p><strong>Rejected by {rejectedBy}: {reasonLabel(rejection.rejection_reason)}</strong></p>
            <p>{rejection.review_comment}</p>
            {ticket.can_create_replacement && (
              <p className="small">To correct it, create a new ticket and upload clear photos again. This ticket stays unchanged.</p>
            )}
            {!ticket.can_create_replacement && !ticket.replaced_by_ticket_code && (
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
              <dt>Routing</dt>
              <dd>{{ AUTO: "Policy engine (no flags)", AI_CHECK: "Automated receipt check" }[ticket.routing] ?? "Manager review"}</dd>
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
