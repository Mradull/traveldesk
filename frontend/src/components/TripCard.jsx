import { Link } from "react-router-dom";
import StatusBadge from "./StatusBadge";
import { formatDate, formatDateRange, formatINR } from "../utils/format";

export default function TripCard({ trip }) {
  const active = trip.approval_status === "APPROVED" && trip.trip_state === "ACTIVE";
  return (
    <Link to={`/trips/${trip.trip_id}`} className="card trip-card">
      <div className="trip-card__top">
        <span className="trip-card__code">{trip.trip_code}</span>
        <StatusBadge status={trip.status_label} />
      </div>
      <h3 className="trip-card__dest">{trip.destination}</h3>
      <p className="muted">{formatDateRange(trip.start_date, trip.end_date)}</p>
      {active && <p className="muted small">Auto-completes {formatDate(trip.auto_close_on)}</p>}
      <div className="trip-card__meta">
        <span>{trip.ticket_count} {trip.ticket_count === 1 ? "ticket" : "tickets"}</span>
        <span>{formatINR(trip.total_claimed)} claimed</span>
      </div>
    </Link>
  );
}