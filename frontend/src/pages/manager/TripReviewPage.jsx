// /manager/trips/:id: trip details and history; Approve / Reject with review comment; Mark completed.
// Also shown inside the Approvals split view (embedded). Managers see no weather and no AI output.
// Owner: Mradul (M3)
import { Link, useParams } from "react-router-dom";
import { useState } from "react";
import { ExternalLink } from "lucide-react";
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
import Breadcrumbs from "../../components/ui/Breadcrumbs";
import { StatusTimeline, tripSteps } from "../../components/ui/StatusTimeline";
import { useConfirm, useToast } from "../../components/ui/UiProvider";

/** embedded: shown in the Approvals split view (no breadcrumbs, calls onChanged after a decision) */
export default function TripReviewPage({ tripId: tripIdProp, embedded = false, onChanged }) {
  const params = useParams();
  const tripId = tripIdProp ?? params.tripId;
  const { data: trip, error, loading, reload, setData } = useApi(() => getTrip(tripId), [tripId]);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(null);
  const toast = useToast();
  const confirm = useConfirm();

  if (loading) return <Loader label="Loading trip…" />;
  if (error) return <ErrorBanner error={error} onRetry={reload} />;
  if (!trip) return null;

  async function run(action, successText) {
    setBusy(true);
    setActionError(null);
    try {
      const updated = await action();
      setData({ ...trip, ...updated });
      toast(successText);
      onChanged?.();
    } catch (err) {
      setActionError(err);
      if (err.code === "ALREADY_DECIDED") reload();
    } finally {
      setBusy(false);
    }
  }

  async function handleDecide(body) {
    if (body.decision === "REJECTED") {
      const ok = await confirm({
        title: `Reject ${trip.trip_code}?`,
        message: <>{trip.employee_name} will see your comment. A rejected trip can't be reopened; they would need to request a new one.</>,
        confirmLabel: "Reject trip", tone: "danger",
      });
      if (!ok) return;
    }
    run(() => decideTrip(trip.trip_id, body), body.decision === "APPROVED" ? `${trip.trip_code} approved` : `${trip.trip_code} rejected`);
  }

  async function handleComplete() {
    const ok = await confirm({
      title: `Mark ${trip.trip_code} as completed?`,
      message: <>{trip.employee_name} won't be able to add new expenses. Pending tickets can still be decided.</>,
      confirmLabel: "Mark completed",
    });
    if (ok) run(() => completeTrip(trip.trip_id), `${trip.trip_code} marked as completed`);
  }

  // The backend says whether a decision is still allowed (e.g. not after the 90-day window)
  const canDecide = trip.can_decide ?? trip.approval_status === "IN_PROGRESS";
  const activeNotEnded = trip.trip_state === "ACTIVE" && !trip.can_complete;

  return (
    <section>
      {!embedded && <Breadcrumbs items={[{ label: "Approvals", to: "/manager/approvals" }, { label: trip.trip_code }]} />}

      <div className="page-header">
        <div>
          <p className="trip-card__code">{trip.trip_code}, {trip.employee_name}</p>
          <h1>{trip.destination}</h1>
          <StatusBadge status={trip.status_label} />
        </div>
        {embedded && (
          <Link className="btn btn--ghost btn--small" to={`/manager/trips/${trip.trip_id}`}>
            Open full page <ExternalLink size={14} aria-hidden="true" />
          </Link>
        )}
      </div>

      <StatusTimeline steps={tripSteps(trip)} label="Trip progress" />
      <ErrorBanner error={actionError} />

      <div className={embedded ? "stack" : "detail-grid"}>
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
                You can complete it from {formatDate(trip.end_date)}. It completes automatically on {formatDate(trip.auto_complete_on)}.
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
