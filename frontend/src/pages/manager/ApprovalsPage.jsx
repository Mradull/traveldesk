// /manager/approvals: tabs Trip requests, Expense tickets, Trips to complete.
// Wide screens: split view (#15) - the selected item opens on the right without leaving the page.
// Owner: Mradul (M3)
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { MousePointerClick } from "lucide-react";
import { useApi } from "../../hooks/useApi";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { filterRows, useTableSort } from "../../hooks/useTableSort";
import { listPendingTrips, listTripsToComplete } from "../../api/trips";
import { listPendingTickets } from "../../api/tickets";
import { ageLabel, formatDate, formatDateRange, formatINR, todayISO, tripLengthDays } from "../../utils/format";
import Loader from "../../components/Loader";
import ErrorBanner from "../../components/ErrorBanner";
import EmptyState from "../../components/EmptyState";
import PolicyFlagList from "../../components/PolicyFlagList";
import SortHeader from "../../components/ui/SortHeader";
import SearchBox from "../../components/ui/SearchBox";
import TripReviewPage from "./TripReviewPage";
import TicketReviewPage from "./TicketReviewPage";

const TABS = [
  { value: "trips", label: "Trip requests", empty: "No trip requests to review.", kind: "trip" },
  { value: "tickets", label: "Expense tickets", empty: "No flagged expense tickets to review.", kind: "ticket" },
  { value: "complete", label: "Trips to complete", empty: "No finished trips waiting to be completed.", kind: "trip" },
];

/** "in 12 days", "today", "started 3 days ago" (the list has no created date, so we show how soon it starts) */
function startsLabel(startDate) {
  const days = tripLengthDays(todayISO(), startDate) - 1;
  if (days === 0) return "today";
  if (days > 0) return `in ${days} ${days === 1 ? "day" : "days"}`;
  return `started ${-days} ${days === -1 ? "day" : "days"} ago`;
}

// Column definitions per tab: header, sort key, cell
const COLUMNS = {
  trips: [
    { label: "Trip", key: "trip_code", cell: (t) => t.trip_code, link: true },
    { label: "Employee", key: "employee_name", cell: (t) => t.employee_name },
    { label: "Destination", key: "destination", cell: (t) => t.destination },
    { label: "Dates", key: "start_date", cell: (t) => <>{formatDateRange(t.start_date, t.end_date)}<div className="muted small">{tripLengthDays(t.start_date, t.end_date)} days</div></> },
    { label: "Starts", key: "start_date", sortable: false, inSplit: false, cell: (t) => startsLabel(t.start_date) },
  ],
  tickets: [
    { label: "Ticket", key: "ticket_code", cell: (k) => k.ticket_code, link: true },
    { label: "Employee", key: "employee_name", cell: (k) => k.employee_name },
    { label: "Trip", key: "trip_code", cell: (k) => <>{k.trip_code}<div className="muted small">{k.destination}</div></> },
    { label: "Lines", key: "line_count", num: true, inSplit: false, cell: (k) => k.line_count },
    { label: "Total", key: "total_amount", num: true, cell: (k) => formatINR(k.total_amount) },
    { label: "Policy flags", key: "flag_codes", sortable: false, cell: (k) => <PolicyFlagList codes={k.flag_codes} compact /> },
    { label: "Waiting", key: "submitted_at", inSplit: false, cell: (k) => ageLabel(k.submitted_at) },
  ],
  complete: [
    { label: "Trip", key: "trip_code", cell: (t) => t.trip_code, link: true },
    { label: "Employee", key: "employee_name", cell: (t) => t.employee_name },
    { label: "Destination", key: "destination", inSplit: false, cell: (t) => t.destination },
    { label: "Ended", key: "end_date", cell: (t) => formatDate(t.end_date) },
    { label: "Tickets", key: "ticket_count", num: true, inSplit: false, cell: (t) => t.ticket_count },
    { label: "Auto-completes", key: "auto_complete_on", cell: (t) => formatDate(t.auto_complete_on) },
  ],
};
const SEARCH_FIELDS = ["trip_code", "ticket_code", "employee_name", "destination"];

function QueueTable({ tab, rows, split, selectedId, onSelect }) {
  const kind = TABS.find((t) => t.value === tab).kind;
  const idOf = (r) => (kind === "ticket" ? r.ticket_id : r.trip_id);
  const pathOf = (r) => (kind === "ticket" ? `/manager/tickets/${r.ticket_id}` : `/manager/trips/${r.trip_id}`);
  const { sorted, sort, toggle } = useTableSort(rows);
  // In the split view the list is narrow: drop secondary columns (all shown in the detail pane)
  const columns = COLUMNS[tab].filter((c) => !split || c.inSplit !== false);

  return (
    <div className="card table-card">
      <div className="table-wrap">
        <table className="table table--rows table--responsive">
          <thead>
            <tr>
              {columns.map((c) => (c.sortable === false
                ? <th key={c.label} className={c.num ? "num" : undefined}>{c.label}</th>
                : <SortHeader key={c.label} label={c.label} sortKey={c.key} sort={sort} onSort={toggle} num={c.num} />))}
              {!split && <th><span className="sr-only">Action</span></th>}
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => {
              const selected = split && selectedId === idOf(r);
              return (
                <tr key={idOf(r)} className={selected ? "row--selected" : undefined} aria-selected={split ? selected : undefined}
                    onClick={split ? () => onSelect(idOf(r)) : undefined}>
                  {columns.map((c) => (
                    <td key={c.label} data-label={c.label} className={c.num ? "num" : undefined}>
                      {c.link && !split && <Link to={pathOf(r)}>{c.cell(r)}</Link>}
                      {c.link && split && (
                        <button type="button" className="link-btn" aria-pressed={selected}
                                onClick={(e) => { e.stopPropagation(); onSelect(idOf(r)); }}>
                          {c.cell(r)}
                        </button>
                      )}
                      {!c.link && c.cell(r)}
                    </td>
                  ))}
                  {!split && (
                    <td data-label="">
                      <Link className="btn btn--primary btn--small" to={pathOf(r)}>{tab === "complete" ? "Open" : "Review"}</Link>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function ApprovalsPage() {
  const [params, setParams] = useSearchParams();
  const tab = TABS.some((t) => t.value === params.get("tab")) ? params.get("tab") : "trips"; // tab kept in the URL
  const split = useMediaQuery("(min-width: 1180px)");
  const [selected, setSelected] = useState(null);
  const [query, setQuery] = useState("");

  const trips = useApi(() => listPendingTrips(), []);
  const tickets = useApi(() => listPendingTickets(), []);
  const complete = useApi(() => listTripsToComplete(), []);
  const queues = { trips, tickets, complete };
  const current = queues[tab];
  const currentTab = TABS.find((t) => t.value === tab);
  const rows = filterRows(current.data, query, SEARCH_FIELDS);

  function refreshAll() {
    trips.reload();
    tickets.reload();
    complete.reload();
  }

  function switchTab(value) {
    setParams({ tab: value });
    setSelected(null);
    setQuery("");
  }

  const list = (
    <>
      {current.loading && <Loader label="Loading queue…" />}
      {!current.loading && current.error && <ErrorBanner error={current.error} onRetry={current.reload} />}
      {!current.loading && !current.error && current.data?.length === 0 && (
        <EmptyState title="Nothing waiting for you" message={currentTab.empty} illustration="inbox" />
      )}
      {!current.loading && !current.error && current.data?.length > 0 && (
        <>
          <div className="toolbar">
            <SearchBox value={query} onChange={setQuery} placeholder="Search code, employee or destination" label="Search the queue" />
            <span className="muted small">{rows.length} of {current.data.length}</span>
          </div>
          {rows.length === 0
            ? <p className="muted">No items match "{query}".</p>
            : <QueueTable tab={tab} rows={rows} split={split} selectedId={selected} onSelect={setSelected} />}
        </>
      )}
    </>
  );

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
            className={tab === t.value ? "tab tab--active" : "tab"} onClick={() => switchTab(t.value)}
          >
            {t.label}
            {queues[t.value].data?.length > 0 && <span className="tab__count">{queues[t.value].data.length}</span>}
          </button>
        ))}
      </div>

      {tab === "tickets" && <p className="hint">Tickets with no policy flags are approved automatically and don't appear here.</p>}

      {!split ? list : (
        <div className="split">
          <div className="split__list">{list}</div>
          <div className="split__detail card" aria-live="polite">
            {selected == null ? (
              <div className="split__empty">
                <MousePointerClick size={28} aria-hidden="true" />
                <p>Select an item to review it here.</p>
              </div>
            ) : currentTab.kind === "ticket" ? (
              <TicketReviewPage key={`k${selected}`} ticketId={selected} embedded onChanged={refreshAll} />
            ) : (
              <TripReviewPage key={`t${selected}`} tripId={selected} embedded onChanged={refreshAll} />
            )}
          </div>
        </div>
      )}
    </section>
  );
}
