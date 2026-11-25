// /trips: trip table with Add expense / Edit / View actions, filters, search, sorting, Vera bubble.
// Owner: Mradul (M3)
import { useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../../hooks/useApi";
import { filterRows, useTableSort } from "../../hooks/useTableSort";
import { listMyTrips } from "../../api/trips";
import { TRIP_FILTERS } from "../../utils/constants";
import { formatDate, formatDateRange, formatINR, todayISO } from "../../utils/format";
import { canAddExpense, canEditTrip } from "../../utils/tripRules";
import Loader from "../../components/Loader";
import ErrorBanner from "../../components/ErrorBanner";
import EmptyState from "../../components/EmptyState";
import StatusBadge from "../../components/StatusBadge";
import SortHeader from "../../components/ui/SortHeader";
import SearchBox from "../../components/ui/SearchBox";
import VeraLauncher from "../../components/chat/VeraLauncher";

export default function MyTripsPage() {
  const [when, setWhen] = useState("upcoming");
  const [query, setQuery] = useState("");
  // Load all trips once and filter in the browser
  const { data, error, loading, reload } = useApi(() => listMyTrips({ when: "all" }), []);
  const today = todayISO();
  const inTab = (data ?? []).filter((t) => when === "all" || (when === "upcoming" ? t.end_date >= today : t.end_date < today));
  const trips = filterRows(inTab, query, ["trip_code", "destination", "status_label"]);
  const { sorted, sort, toggle } = useTableSort(trips, { key: "start_date", dir: when === "past" ? "desc" : "asc" }, {
    total_claimed: (t) => Number(t.total_claimed),
    ticket_count: (t) => Number(t.ticket_count),
  });

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
      {!loading && !error && inTab.length === 0 && (
        <EmptyState
          illustration="trips"
          title="No trips here yet"
          message={when === "past" ? "Trips that have ended will show up here." : "Create a travel request to get started."}
          action={<Link className="btn btn--primary" to="/trips/new">Create trip</Link>}
        />
      )}

      {!loading && !error && inTab.length > 0 && (
        <>
          <div className="toolbar">
            <SearchBox value={query} onChange={setQuery} placeholder="Search trip, destination or status" label="Search trips" />
            <span className="muted small">{trips.length} of {inTab.length}</span>
          </div>
          {trips.length === 0 ? <p className="muted">No trips match "{query}".</p> : (
            <div className="card table-card">
              <div className="table-wrap">
                <table className="table table--rows table--responsive">
                  <thead>
                    <tr>
                      <SortHeader label="Trip ID" sortKey="trip_code" sort={sort} onSort={toggle} />
                      <SortHeader label="Destination" sortKey="destination" sort={sort} onSort={toggle} />
                      <SortHeader label="Dates" sortKey="start_date" sort={sort} onSort={toggle} />
                      <SortHeader label="Status" sortKey="status_label" sort={sort} onSort={toggle} />
                      <SortHeader label="Tickets" sortKey="ticket_count" sort={sort} onSort={toggle} num />
                      <SortHeader label="Claimed" sortKey="total_claimed" sort={sort} onSort={toggle} num />
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sorted.map((t) => (
                      <tr key={t.trip_id}>
                        <td data-label="Trip ID"><Link to={`/trips/${t.trip_id}`}>{t.trip_code}</Link></td>
                        <td data-label="Destination">{t.destination}</td>
                        <td data-label="Dates">{formatDateRange(t.start_date, t.end_date)}</td>
                        <td data-label="Status">
                          <StatusBadge status={t.status_label} />
                          {t.trip_state === "ACTIVE" && <div className="muted small">Auto-completes {formatDate(t.auto_complete_on)}</div>}
                        </td>
                        <td data-label="Tickets" className="num">{t.ticket_count}</td>
                        <td data-label="Claimed" className="num">{formatINR(t.total_claimed)}</td>
                        <td data-label="">
                          <div className="row-actions">
                            {canAddExpense(t) && (
                              <Link className="btn btn--primary btn--small" to={`/trips/${t.trip_id}/expenses/new`}>Add expense</Link>
                            )}
                            {canEditTrip(t) && (
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
        </>
      )}

      <VeraLauncher />
    </section>
  );
}
