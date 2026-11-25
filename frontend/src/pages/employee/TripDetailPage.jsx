// /trips/:id: trip info, decision history, tickets; Edit (In Progress); Raise ticket (Active).
// Owner: Mradul (M3)
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useApi } from "../../hooks/useApi";
import { getTrip, updateTrip } from "../../api/trips";
import { fieldErrorsFromApi } from "../../utils/validation";
import Loader from "../../components/Loader";
import ErrorBanner from "../../components/ErrorBanner";
import StatusBadge from "../../components/StatusBadge";
import TripForm from "../../components/TripForm";
import TripInfo from "../../components/TripInfo";
import TicketList from "../../components/TicketList";
import ApprovalHistory from "../../components/ApprovalHistory";
import Breadcrumbs from "../../components/ui/Breadcrumbs";
import VeraLauncher from "../../components/chat/VeraLauncher";
import { StatusTimeline, tripSteps } from "../../components/ui/StatusTimeline";
import { useToast } from "../../components/ui/UiProvider";

function ticketEmptyMessage(trip) {
  if (trip.approval_status === "IN_PROGRESS") return "Tickets can be raised once your manager approves the trip.";
  if (trip.approval_status === "REJECTED") return "This trip was rejected, so no expenses can be claimed.";
  if (trip.trip_state === "COMPLETED") return "This trip is completed. No new tickets can be raised.";
  return "No tickets yet. Raise one for the expenses on this trip.";
}

export default function TripDetailPage() {
  const { tripId } = useParams();
  const [params] = useSearchParams();
  const { data: trip, error, loading, reload, setData } = useApi(() => getTrip(tripId), [tripId]);
  const [editing, setEditing] = useState(params.get("edit") === "1"); // "Edit" on My Trips opens the form directly
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [serverErrors, setServerErrors] = useState({});
  const toast = useToast();

  if (loading) return <Loader label="Loading trip…" />;
  if (error) return <ErrorBanner error={error} onRetry={reload} />;
  if (!trip) return null;

  async function handleSave(values) {
    setSaving(true);
    setSaveError(null);
    setServerErrors({});
    try {
      const updated = await updateTrip(trip.trip_id, values);
      setData({ ...trip, ...updated });
      setEditing(false);
      toast("Changes saved");
    } catch (err) {
      const fields = fieldErrorsFromApi(err);
      if (Object.keys(fields).length > 0) setServerErrors(fields);
      else setSaveError(err);
      if (err.code === "TRIP_NOT_EDITABLE") reload(); // the manager decided meanwhile
    } finally {
      setSaving(false);
    }
  }

  function cancelEdit() {
    setEditing(false);
    setSaveError(null);
    setServerErrors({});
  }

  const rejection = trip.approval_status === "REJECTED" ? trip.approvals.find((a) => a.decision === "REJECTED") : null;
  const raiseUrl = `/trips/${trip.trip_id}/expenses/new`;

  return (
    <section>
      <Breadcrumbs items={[{ label: "My Trips", to: "/trips" }, { label: trip.trip_code }]} />

      <div className="page-header">
        <div>
          <p className="trip-card__code">{trip.trip_code}</p>
          <h1>{trip.destination}</h1>
          <StatusBadge status={trip.status_label} />
        </div>
        <div className="page-header__actions">
          {trip.can_edit && !editing && (
            <button type="button" className="btn btn--secondary" onClick={() => setEditing(true)}>
              Edit request
            </button>
          )}
          {trip.can_raise_ticket && <Link className="btn btn--primary" to={raiseUrl}>Add expense</Link>}
        </div>
      </div>

      <StatusTimeline steps={tripSteps(trip)} label="Trip progress" />
      {rejection && (
        <div className="alert alert--error">
          <div>
            <p><strong>Rejected by {rejection.reviewer_name}</strong></p>
            <p>{rejection.review_comment}</p>
          </div>
        </div>
      )}

      <div className="detail-grid">
        <div className="stack">
          {editing && trip.can_edit ? (
            <div className="card">
              <h2>Edit request</h2>
              <ErrorBanner error={saveError} />
              <TripForm
                initialValues={{ destination: trip.destination, start_date: trip.start_date, end_date: trip.end_date, purpose: trip.purpose }}
                onSubmit={handleSave}
                submitting={saving}
                serverErrors={serverErrors}
                submitLabel="Save changes"
                onCancel={cancelEdit}
              />
            </div>
          ) : (
            <TripInfo trip={trip} />
          )}

          <div className="card">
            <div className="card__header">
              <h2>Expense tickets</h2>
              {trip.can_raise_ticket && <Link className="btn btn--ghost btn--small" to={raiseUrl}>+ Add expense</Link>}
            </div>
            {trip.tickets.length > 0
              ? <TicketList tickets={trip.tickets} linkBase="/tickets" />
              : <p className="muted">{ticketEmptyMessage(trip)}</p>}
          </div>
        </div>

        <aside className="stack">
          <div className="card">
            <h2>Decision history</h2>
            <ApprovalHistory approvals={trip.approvals} />
          </div>
        </aside>
      </div>

      {/* Vera: policy and weather questions about this trip */}
      <VeraLauncher />
    </section>
  );
}
