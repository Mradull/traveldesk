import { formatDate, formatDateRange, formatDateTime, tripLengthDays } from "../utils/format";

/** Read-only trip facts (employee Trip Detail and manager Trip review) */
export default function TripInfo({ trip, showEmployee = false }) {
  const days = tripLengthDays(trip.start_date, trip.end_date);
  const active = trip.approval_status === "APPROVED" && trip.trip_state === "ACTIVE";

  return (
    <div className="card">
      <h2>Trip details</h2>
      <dl className="details">
        {showEmployee && (<><dt>Employee</dt><dd>{trip.employee_name}, {trip.department}</dd></>)}
        <dt>Dates</dt>
        <dd>{formatDateRange(trip.start_date, trip.end_date)} ({days} days)</dd>
        <dt>Purpose</dt>
        <dd>{trip.purpose}</dd>
        <dt>Requested on</dt>
        <dd>{formatDate(trip.created_on ?? trip.created_at)}</dd>
        {active && (<><dt>Auto-completes on</dt><dd>{formatDate(trip.auto_close_on)}</dd></>)}
        {trip.trip_state === "COMPLETED" && (
          <>
            <dt>Completed</dt>
            <dd>
              {trip.completion_type === "AUTO"
                ? "By the system (start date + 90 days)"
                : `${formatDateTime(trip.completed_at)} by ${trip.completed_by_name}`}
            </dd>
          </>
        )}
      </dl>
    </div>
  );
}
