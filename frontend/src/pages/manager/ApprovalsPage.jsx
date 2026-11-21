// /manager/approvals: tabs Trip requests, Expense tickets, Trips to complete.
// Owner: Mradul (M3)
import { Link, useSearchParams } from "react-router-dom";
import { useApi } from "../../hooks/useApi";
import { listPendingTrips, listTripsToComplete } from "../../api/trips";
import { listPendingTickets } from "../../api/tickets";
import { ageLabel, formatDate, formatDateRange, formatINR, tripLengthDays } from "../../utils/format";
import Loader from "../../components/Loader";
import ErrorBanner from "../../components/ErrorBanner";
import EmptyState from "../../components/EmptyState";
import PolicyFlagList from "../../components/PolicyFlagList";

const TABS = [
  { value: "trips", label: "Trip requests", empty: "No trip requests to review." },
  { value: "tickets", label: "Expense tickets", empty: "No flagged expense tickets to review." },
  { value: "complete", label: "Trips to complete", empty: "No finished trips waiting to be completed." },
];

function Table({ head, children }) {
  return (
    <div className="card table-card">
      <div className="table-wrap">
        <table className="table table--rows">
          <thead>
            <tr>{head.map((h, i) => <th key={`${h.label}-${i}`} className={h.num ? "num" : undefined}>{h.label}</th>)}</tr>
          </thead>
          <tbody>{children}</tbody>
        </table>
      </div>
    </div>
  );
}

function TripRequests({ rows }) {
  return (
    <Table head={[{ label: "Trip" }, { label: "Employee" }, { label: "Destination" }, { label: "Dates" }, { label: "Purpose" }, { label: "Waiting" }, { label: "" }]}>
      {rows.map((t) => (
        <tr key={t.trip_id}>
          <td><Link to={`/manager/trips/${t.trip_id}`}>{t.trip_code}</Link></td>
          <td>{t.employee_name}<div className="muted small">{t.department}</div></td>
          <td>{t.destination}</td>
          <td>{formatDateRange(t.start_date, t.end_date)}<div className="muted small">{tripLengthDays(t.start_date, t.end_date)} days</div></td>
          <td className="cell-wrap">{t.purpose}</td>
          <td>{ageLabel(t.created_at)}</td>
          <td><Link className="btn btn--primary btn--small" to={`/manager/trips/${t.trip_id}`}>Review</Link></td>
        </tr>
      ))}
    </Table>
  );
}

function PendingTickets({ rows }) {
  return (
    <Table head={[{ label: "Ticket" }, { label: "Employee" }, { label: "Trip" }, { label: "Lines", num: true }, { label: "Total", num: true }, { label: "Policy flags" }, { label: "Waiting" }, { label: "" }]}>
      {rows.map((k) => (
        <tr key={k.ticket_id}>
          <td><Link to={`/manager/tickets/${k.ticket_id}`}>{k.ticket_code}</Link></td>
          <td>{k.employee_name}</td>
          <td>{k.trip_code}<div className="muted small">{k.destination}</div></td>
          <td className="num">{k.line_count}</td>
          <td className="num">{formatINR(k.total_amount)}</td>
          <td><PolicyFlagList codes={k.flag_codes} compact /></td>
          <td>{ageLabel(k.submitted_at)}</td>
          <td><Link className="btn btn--primary btn--small" to={`/manager/tickets/${k.ticket_id}`}>Review</Link></td>
        </tr>
      ))}
    </Table>
  );
}

function TripsToComplete({ rows }) {
  return (
    <Table head={[{ label: "Trip" }, { label: "Employee" }, { label: "Destination" }, { label: "Ended" }, { label: "Pending tickets", num: true }, { label: "Auto-completes" }, { label: "" }]}>
      {rows.map((t) => (
        <tr key={t.trip_id}>
          <td><Link to={`/manager/trips/${t.trip_id}`}>{t.trip_code}</Link></td>
          <td>{t.employee_name}</td>
          <td>{t.destination}</td>
          <td>{formatDate(t.end_date)}</td>
          <td className="num">{t.pending_ticket_count}</td>
          <td>{formatDate(t.auto_close_on)}</td>
          <td><Link className="btn btn--primary btn--small" to={`/manager/trips/${t.trip_id}`}>Open</Link></td>
        </tr>
      ))}
    </Table>
  );
}

export default function ApprovalsPage() {
  const [params, setParams] = useSearchParams();
  const tab = TABS.some((t) => t.value === params.get("tab")) ? params.get("tab") : "trips"; // tab kept in the URL

  const trips = useApi(() => listPendingTrips(), []);
  const tickets = useApi(() => listPendingTickets(), []);
  const complete = useApi(() => listTripsToComplete(), []);
  const queues = { trips, tickets, complete };
  const current = queues[tab];
  const currentTab = TABS.find((t) => t.value === tab);

  function refreshAll() {
    trips.reload();
    tickets.reload();
    complete.reload();
  }

  return (
    <section>
      <div className="page-header">
        <div>
          <h1>Approvals</h1>
          <p className="muted">Requests from your team waiting for you, oldest first.</p>
        </div>
        <button type="button" className="btn btn--secondary" onClick={refreshAll}>Refresh</button>
      </div>

      <div className="tabs" role="tablist" aria-label="Approval queues">
        {TABS.map((t) => (
          <button
            key={t.value} type="button" role="tab" aria-selected={tab === t.value}
            className={tab === t.value ? "tab tab--active" : "tab"} onClick={() => setParams({ tab: t.value })}
          >
            {t.label}
            {queues[t.value].data?.length > 0 && <span className="tab__count">{queues[t.value].data.length}</span>}
          </button>
        ))}
      </div>

      {tab === "tickets" && <p className="hint">Tickets with no policy flags are approved automatically and don't appear here.</p>}

      {current.loading && <Loader label="Loading queue…" />}
      {!current.loading && current.error && <ErrorBanner error={current.error} onRetry={current.reload} />}
      {!current.loading && !current.error && current.data?.length === 0 && (
        <EmptyState title="Nothing waiting for you" message={currentTab.empty} />
      )}
      {!current.loading && !current.error && current.data?.length > 0 && (
        <>
          {tab === "trips" && <TripRequests rows={current.data} />}
          {tab === "tickets" && <PendingTickets rows={current.data} />}
          {tab === "complete" && <TripsToComplete rows={current.data} />}
        </>
      )}
    </section>
  );
}
