// /manager/reports: the three required SQL demonstrations.
// Owner: Mradul (M3)
import { Fragment, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, ListChecks, Wallet } from "lucide-react";
import { useApi } from "../../hooks/useApi";
import { getSpendByTripCategory, getTripExpenseReport } from "../../api/reports";
import { listPendingExpenses } from "../../api/expenses";
import { EXPENSE_CATEGORIES } from "../../utils/constants";
import { ageLabel, formatINR } from "../../utils/format";
import Loader from "../../components/Loader";
import ErrorBanner from "../../components/ErrorBanner";
import StatusBadge from "../../components/StatusBadge";
import PolicyFlagList from "../../components/PolicyFlagList";
import CountUp from "../../components/ui/CountUp";
import DonutChart from "../../components/ui/DonutChart";

const categoryLabel = (value) => EXPENSE_CATEGORIES.find((c) => c.value === value)?.label ?? value;

/** Turns GROUPING SETS rows into { trip_code, destination, categories[], total } per trip */
function groupByTrip(rows) {
  const trips = new Map();
  for (const r of rows) {
    if (!trips.has(r.trip_code)) trips.set(r.trip_code, { trip_code: r.trip_code, destination: r.destination, categories: [], total: null });
    const group = trips.get(r.trip_code);
    if (r.expense_type == null) group.total = r;
    else group.categories.push(r);
  }
  return [...trips.values()];
}

/** Each report loads and fails on its own, so one broken query doesn't blank the page */
function Section({ title, subtitle, request, children }) {
  return (
    <div className="card">
      <h2>{title}</h2>
      {subtitle && <p className="muted small">{subtitle}</p>}
      {request.loading && <Loader label="Running query…" />}
      {!request.loading && request.error && <ErrorBanner error={request.error} onRetry={request.reload} />}
      {!request.loading && !request.error && request.data && children(request.data)}
    </div>
  );
}

export default function SpendingSummaryPage() {
  const spend = useApi(() => getSpendByTripCategory(), []);
  const pending = useApi(() => listPendingExpenses(), []);
  const lines = useApi(() => getTripExpenseReport(), []);
  const [search, setSearch] = useState("");

  const tripGroups = useMemo(() => groupByTrip(spend.data ?? []), [spend.data]);
  const approvedTotal = tripGroups.reduce((s, g) => s + Number(g.total?.total_amount ?? 0), 0);
  const pendingTotal = (pending.data ?? []).reduce((s, r) => s + Number(r.amount), 0);
  const query = search.trim().toLowerCase();
  const filteredLines = (lines.data ?? []).filter((r) =>
    !query || [r.employee_name, r.trip_code, r.destination, r.expense_code].some((v) => v.toLowerCase().includes(query)));

  const kpis = [
    { label: "Approved spend", value: spend.data ? <CountUp value={approvedTotal} format={formatINR} /> : "–", icon: Wallet },
    { label: "Expense lines claimed", value: lines.data ? <CountUp value={lines.data.length} /> : "–", icon: ListChecks },
    { label: "Flagged lines pending", value: pending.data ? <>{pending.data.length} <small className="kpi__sub">({formatINR(pendingTotal)})</small></> : "–", icon: AlertTriangle },
  ];

  // Charts (#6): approved spend by category (donut) and by trip (bars), from the same SQL report
  const byCategory = Object.values((spend.data ?? []).filter((r) => r.expense_type != null).reduce((acc, r) => {
    acc[r.expense_type] = acc[r.expense_type] ?? { label: categoryLabel(r.expense_type), value: 0 };
    acc[r.expense_type].value += Number(r.total_amount);
    return acc;
  }, {})).sort((a, b) => b.value - a.value);
  const byTrip = tripGroups.filter((g) => g.total).map((g) => ({ label: `${g.trip_code} · ${g.destination}`, value: Number(g.total.total_amount) }))
    .sort((a, b) => b.value - a.value);
  const maxTrip = Math.max(1, ...byTrip.map((t) => t.value));

  return (
    <section className="stack">
      <div className="page-header">
        <div>
          <h1>Spending Summary</h1>
          <p className="muted">Your team's travel spend, from the three SQL reports.</p>
        </div>
        <button type="button" className="btn btn--secondary" onClick={() => { spend.reload(); pending.reload(); lines.reload(); }}>
          Refresh
        </button>
      </div>

      <div className="kpi-grid">
        {kpis.map(({ label, value, icon: Icon }) => (
          <div key={label} className="card kpi">
            <Icon size={20} className="kpi__icon" aria-hidden="true" />
            <span className="kpi__label">{label}</span>
            <span className="kpi__value">{value}</span>
          </div>
        ))}
      </div>

      {byCategory.length > 0 && (
        <div className="dash-grid">
          <div className="card">
            <h2>Approved spend by category</h2>
            <DonutChart label="Approved spend by category" format={formatINR} data={byCategory} />
          </div>
          <div className="card">
            <h2>Approved spend by trip</h2>
            <ul className="bar-chart">
              {byTrip.map((t, i) => (
                <li key={t.label}>
                  <span className="bar-chart__label bar-chart__label--wide">{t.label}</span>
                  <span className="bar-chart__track"><span className="bar-chart__bar" style={{ width: `${(t.value / maxTrip) * 100}%`, ...(i === 0 ? { background: "var(--brand-yellow)" } : {}) }} /></span>
                  <span className="bar-chart__value">{formatINR(t.value)}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      <Section title="Spend by trip and category" subtitle="Approved and auto-approved lines only, with a total per trip" request={spend}>
        {() => (tripGroups.length === 0 ? <p className="muted">No approved spend yet.</p> : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Trip</th><th>Category</th><th className="num">Lines</th><th className="num">Amount</th></tr></thead>
              <tbody>
                {tripGroups.map((g) => (
                  <Fragment key={g.trip_code}>
                    {g.categories.map((c, i) => (
                      <tr key={`${g.trip_code}-${c.expense_type}`}>
                        <td>{i === 0 ? <><strong>{g.trip_code}</strong> <span className="muted">{g.destination}</span></> : ""}</td>
                        <td>{categoryLabel(c.expense_type)}</td>
                        <td className="num">{c.line_count}</td>
                        <td className="num">{formatINR(c.total_amount)}</td>
                      </tr>
                    ))}
                    {g.total && (
                      <tr className="table__total">
                        <td />
                        <td>Trip total</td>
                        <td className="num">{g.total.line_count}</td>
                        <td className="num">{formatINR(g.total.total_amount)}</td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </Section>

      <Section title="Pending manager approvals" subtitle="Flagged lines in tickets you haven't decided yet" request={pending}>
        {(rows) => (rows.length === 0 ? <p className="muted">No flagged lines waiting.</p> : (
          <div className="table-wrap">
            <table className="table table--rows">
              <thead>
                <tr><th>Expense</th><th>Ticket</th><th>Employee</th><th>Trip</th><th>Category</th><th className="num">Amount</th><th>Flags</th><th>Waiting</th></tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.expense_code}>
                    <td>{r.expense_code}</td>
                    <td>{r.ticket_id ? <Link to={`/manager/tickets/${r.ticket_id}`}>{r.ticket_code}</Link> : r.ticket_code}</td>
                    <td>{r.employee_name}</td>
                    <td>{r.trip_code}<div className="muted small">{r.destination}</div></td>
                    <td>{categoryLabel(r.expense_type)}</td>
                    <td className="num">{formatINR(r.amount)}</td>
                    <td><PolicyFlagList codes={r.flag_codes} compact /></td>
                    <td>{ageLabel(r.submitted_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </Section>

      <Section title="All expense lines" subtitle="Employee, trip, destination, category and amount (every status)" request={lines}>
        {() => (
          <>
            <label className="field search-field">
              <span className="sr-only">Search</span>
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search employee, trip, destination or expense…" />
            </label>
            {filteredLines.length === 0 ? <p className="muted">No matching lines.</p> : (
              <div className="table-wrap">
                <table className="table table--rows">
                  <thead><tr><th>Employee</th><th>Trip</th><th>Destination</th><th>Expense</th><th>Category</th><th className="num">Amount</th><th>Status</th></tr></thead>
                  <tbody>
                    {filteredLines.map((r) => (
                      <tr key={r.expense_code}>
                        <td>{r.employee_name}</td>
                        <td>{r.trip_code}</td>
                        <td>{r.destination}</td>
                        <td>{r.expense_code}</td>
                        <td>{categoryLabel(r.expense_type)}</td>
                        <td className="num">{formatINR(r.amount)}</td>
                        <td><StatusBadge status={r.status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </Section>
    </section>
  );
}
