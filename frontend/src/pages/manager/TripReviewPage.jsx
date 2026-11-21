// /manager/trips/:id: trip details and history; Approve / Reject with review comment; Mark completed.
// Owner: Mradul (M3)  |  Managers see no weather and no AI output.
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApi } from "../../hooks/useApi";
import { completeTrip, decideTrip, getTrip } from "../../api/trips";
import { formatDate } from "../../utils/format";
import Loader from "../../components/Loader";
import ErrorBanner from "../../components/ErrorBanner";
import StatusBadge from "../../components/StatusBadge";
import TripInfo from "../../components/TripInfo";
import TicketList from "../../components/TicketList";
import ApprovalHistory from "../../components/ApprovalHistory";
import DecisionPanel from "../../components/DecisionPanel";

export default function TripReviewPage() {
  const { tripId } = useParams();
  const { data: trip, error, loading, reload, setData } = useApi(() => getTrip(tripId), [tripId]);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [message, setMessage] = useState(null);

  if (loading) return <Loader label="Loading trip…" />;
  if (error) return <ErrorBanner error={error} onRetry={reload} />;
  if (!trip) return null;

  async function run(action, successText) {
    setBusy(true);
    setActionError(null);
    try {
      const updated = await action();
      setData({ ...trip, ...updated });
      setMessage(successText);
    } catch (err) {
      setActionError(err);
      if (err.code === "ALREADY_DECIDED") reload();
    } finally {
      setBusy(false);
    }
  }

  function handleDecide(body) {
    run(
      () => decideTrip(trip.trip_id, body),
      body.decision === "APPROVED" ? "Trip approved." : "Trip rejected. The employee can see your comment.",
    );
  }

  function handleComplete() {
    if (!window.confirm(`Mark ${trip.trip_code} as completed? ${trip.employee_name} won't be able to add new expenses.`)) return;
    run(() => completeTrip(trip.trip_id), "Trip marked as completed.");
  }

  const canDecide = trip.approval_status === "IN_PROGRESS";
  const activeNotEnded = trip.trip_state === "ACTIVE" && !trip.can_complete;

  return (
    <section>
      <Link to="/manager/approvals" className="back-link">← Approvals</Link>

      <div className="page-header">
        <div>
          <p className="trip-card__code">{trip.trip_code}, {trip.employee_name}</p>
          <h1>{trip.destination}</h1>
          <StatusBadge status={trip.status_label} />
        </div>
      </div>

      {message && <div className="alert alert--info"><p>{message}</p></div>}
      <ErrorBanner error={actionError} />

      <div className="detail-grid">
        <div className="stack">
          <TripInfo trip={trip} showEmployee />
          <div className="card">
            <h2>Expense tickets</h2>
            {trip.tickets.length > 0
              ? <TicketList tickets={trip.tickets} linkBase="/manager/tickets" />
              : <p className="muted">No tickets raised on this trip.</p>}
          </div>
        </div>

        <aside className="stack">
          {canDecide && (
            <DecisionPanel
              title="Approve this trip?"
              hint="Approving lets the employee add expenses for it."
              onDecide={handleDecide}
              deciding={busy}
            />
          )}

          {trip.can_complete && (
            <div className="card">
              <h2>Complete the trip</h2>
              <p className="muted">The trip has ended. Completing it stops new expenses; pending tickets can still be decided.</p>
              <button type="button" className="btn btn--primary btn--block" onClick={handleComplete} disabled={busy}>
                {busy ? "Saving…" : "Mark completed"}
              </button>
            </div>
          )}

          {activeNotEnded && (
            <div className="card">
              <h2>Complete the trip</h2>
              <p className="muted">
                You can complete it from {formatDate(trip.end_date)}. It completes automatically on {formatDate(trip.auto_close_on)}.
              </p>
            </div>
          )}

          <div className="card">
            <h2>Decision history</h2>
            <ApprovalHistory approvals={trip.approvals} />
          </div>
        </aside>
      </div>
    </section>
  );
}
