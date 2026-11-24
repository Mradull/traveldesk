// /manager/tickets/:id: trip details, lines, photos, flags, receipt check; Approve or Reject (reason + comment).
// Also shown inside the Approvals split view (embedded). Managers see no weather and no Vera.
// Owner: Mradul (M3)
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ExternalLink } from "lucide-react";
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
import Breadcrumbs from "../../components/ui/Breadcrumbs";
import { StatusTimeline, ticketSteps } from "../../components/ui/StatusTimeline";
import { useConfirm, useToast } from "../../components/ui/UiProvider";

export default function TicketReviewPage({ ticketId: ticketIdProp, embedded = false, onChanged }) {
  const params = useParams();
  const ticketId = ticketIdProp ?? params.ticketId;
  const { data: ticket, error, loading, reload, setData } = useApi(() => getTicket(ticketId), [ticketId]);
  // A ticket has no trip dates/purpose/status, so load its trip separately
  const tripReq = useApi(() => (ticket ? getTrip(ticket.trip_id) : Promise.resolve(null)), [ticket?.trip_id]);
  const trip = tripReq.data;
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(null);
  const toast = useToast();
  const confirm = useConfirm();

  if (loading) return <Loader label="Loading ticket…" />;
  if (error) return <ErrorBanner error={error} onRetry={reload} />;
  if (!ticket) return null;

  async function handleDecide(body) {
    if (body.decision === "REJECTED") {
      const ok = await confirm({
        title: `Reject ${ticket.ticket_code}?`,
        message: <>{ticket.employee_name} will see your reason and comment, and can raise a new ticket to correct it.</>,
        confirmLabel: "Reject ticket", tone: "danger",
      });
      if (!ok) return;
    }
    setBusy(true);
    setActionError(null);
    try {
      setData(await decideTicket(ticket.ticket_id, body));
      toast(body.decision === "APPROVED" ? `${ticket.ticket_code} approved` : `${ticket.ticket_code} rejected`);
      onChanged?.();
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
      {!embedded && (
        <Breadcrumbs items={[
          { label: "Approvals", to: "/manager/approvals" },
          { label: "Expense tickets", to: "/manager/approvals?tab=tickets" },
          { label: ticket.ticket_code },
        ]} />
      )}

      <div className="page-header">
        <div>
          <p className="trip-card__code">{ticket.employee_name}, {ticket.trip_code}</p>
          <h1>{ticket.ticket_code}</h1>
          <StatusBadge status={ticket.status} />
        </div>
        {embedded && (
          <Link className="btn btn--ghost btn--small" to={`/manager/tickets/${ticket.ticket_id}`}>
            Open full page <ExternalLink size={14} aria-hidden="true" />
          </Link>
        )}
      </div>

      <StatusTimeline steps={ticketSteps(ticket)} label="Ticket progress" />
      <ErrorBanner error={actionError} />
      {!pending && <ReadOnlyBanner />}

      <div className={embedded ? "stack" : "detail-grid"}>
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
            <p className="muted small">Click a receipt to see it large with the automated check.</p>
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
