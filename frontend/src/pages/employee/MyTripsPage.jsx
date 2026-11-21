// /trips: trip table with Add expense / Edit / View actions, filters, Vera bubble.
// Owner: Mradul (M3)
import { useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../../hooks/useApi";
import { listMyTrips } from "../../api/trips";
import { TRIP_FILTERS } from "../../utils/constants";
import { formatDate, formatDateRange, formatINR, todayISO } from "../../utils/format";
import Loader from "../../components/Loader";
import ErrorBanner from "../../components/ErrorBanner";
import EmptyState from "../../components/EmptyState";
import StatusBadge from "../../components/StatusBadge";
import VeraLauncher from "../../components/chat/VeraLauncher";

export default function MyTripsPage() {
  const [when, setWhen] = useState("upcoming");
  // Load all trips once and filter in the browser
  const { data, error, loading, reload } = useApi(() => listMyTrips({ when: "all" }), []);
  const today = todayISO();
  const trips = (data ?? []).filter((t) => when === "all" || (when === "upcoming" ? t.end_date >= today : t.end_date < today));

  return (
    <section>
      <div className="page-header">
        <div>
          <h1>My Trips</h1>
          <p className="muted">Your travel requests. Add expenses to approved trips from here.</p>
        </div>
        <Link className="btn btn--primary" to="/trips/new">Create trip</Link>
      </div>

      <div className="tabs" role="tablist" aria-label="Filter trips">
        {TRIP_FILTERS.map((f) => (
          <button
            key={f.value} type="button" role="tab" aria-selected={when === f.value}
            className={when === f.value ? "tab tab--active" : "tab"} onClick={() => setWhen(f.value)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {loading && <Loader label="Loading your trips…" />}
      {!loading && error && <ErrorBanner error={error} onRetry={reload} />}
      {!loading && !error && trips.length === 0 && (
        <EmptyState
          title="No trips here yet"
          message={when === "past" ? "Trips that have ended will show up here." : "Create a travel request to get started."}
          action={<Link className="btn btn--primary" to="/trips/new">Create trip</Link>}
        />
      )}

      {!loading && !error && trips.length > 0 && (
        <div className="card table-card">
          <div className="table-wrap">
            <table className="table table--rows">
              <thead>
                <tr>
                  <th>Trip ID</th><th>Destination</th><th>Dates</th><th>Status</th>
                  <th className="num">Tickets</th><th className="num">Claimed</th><th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {trips.map((t) => (
                  <tr key={t.trip_id}>
                    <td><Link to={`/trips/${t.trip_id}`}>{t.trip_code}</Link></td>
                    <td>{t.destination}</td>
                    <td>{formatDateRange(t.start_date, t.end_date)}</td>
                    <td>
                      <StatusBadge status={t.status_label} />
                      {t.trip_state === "ACTIVE" && <div className="muted small">Auto-completes {formatDate(t.auto_close_on)}</div>}
                    </td>
                    <td className="num">{t.ticket_count}</td>
                    <td className="num">{formatINR(t.total_claimed)}</td>
                    <td>
                      <div className="row-actions">
                        {t.can_raise_ticket && (
                          <Link className="btn btn--primary btn--small" to={`/trips/${t.trip_id}/expenses/new`}>Add expense</Link>
                        )}
                        {t.can_edit && (
                          <Link className="btn btn--secondary btn--small" to={`/trips/${t.trip_id}?edit=1`}>Edit</Link>
                        )}
                        <Link className="btn btn--ghost btn--small" to={`/trips/${t.trip_id}`}>View</Link>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <VeraLauncher />
    </section>
  );
}
