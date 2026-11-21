// /dashboard: KPI cards, recent trips, expense overview by category.
// Owner: Mradul (M3)
import { Link } from "react-router-dom";
import { Clock, FolderOpen, Plane, Wallet } from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import { useApi } from "../../hooks/useApi";
import { getEmployeeDashboard } from "../../api/dashboard";
import { EXPENSE_CATEGORIES } from "../../utils/constants";
import { formatDateRange, formatINR } from "../../utils/format";
import Loader from "../../components/Loader";
import ErrorBanner from "../../components/ErrorBanner";
import StatusBadge from "../../components/StatusBadge";

const categoryLabel = (value) => EXPENSE_CATEGORIES.find((c) => c.value === value)?.label ?? value;

export default function DashboardPage() {
  const { user } = useAuth();
  const { data, error, loading, reload } = useApi(() => getEmployeeDashboard(), []);

  if (loading) return <Loader label="Loading your dashboard…" />;
  if (error) return <ErrorBanner error={error} onRetry={reload} />;
  if (!data) return null;

  const kpis = [
    { label: "Total trips", value: data.total_trips, icon: Plane },
    { label: "Open trips", value: data.open_trips, icon: FolderOpen },
    { label: "Pending trip approval", value: data.pending_trip_approval, icon: Clock },
    { label: "Total expenses claimed", value: formatINR(data.total_claimed), icon: Wallet },
  ];
  const maxSpend = Math.max(1, ...data.spend_by_category.map((c) => c.total_amount));

  return (
    <section>
      <div className="page-header">
        <div>
          <h1>Dashboard</h1>
          <p className="muted">Welcome back, {user?.full_name?.split(" ")[0]}.</p>
        </div>
        <Link className="btn btn--primary" to="/trips/new">Create trip</Link>
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

      <div className="dash-grid">
        <div className="card">
          <div className="card__header">
            <h2>Recent trips</h2>
            <Link to="/trips" className="link">View all</Link>
          </div>
          {data.recent_trips.length === 0 ? (
            <p className="muted">No trips yet. Create a travel request to get started.</p>
          ) : (
            <div className="table-wrap">
              <table className="table table--rows">
                <thead><tr><th>Trip ID</th><th>Destination</th><th>Dates</th><th>Status</th><th>Actions</th></tr></thead>
                <tbody>
                  {data.recent_trips.map((t) => (
                    <tr key={t.trip_id}>
                      <td><Link to={`/trips/${t.trip_id}`}>{t.trip_code}</Link></td>
                      <td>{t.destination}</td>
                      <td>{formatDateRange(t.start_date, t.end_date)}</td>
                      <td><StatusBadge status={t.status_label} /></td>
                      <td>
                        {t.can_raise_ticket
                          ? <Link className="btn btn--ghost btn--small" to={`/trips/${t.trip_id}/expenses/new`}>Add expense</Link>
                          : <Link className="btn btn--ghost btn--small" to={`/trips/${t.trip_id}`}>View</Link>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="card">
          <h2>Expense overview</h2>
          <p className="muted small">Claimed by category (rejected tickets excluded)</p>
          {data.spend_by_category.length === 0 ? (
            <p className="muted">No expenses claimed yet.</p>
          ) : (
            <ul className="bar-chart">
              {data.spend_by_category.map((c) => (
                <li key={c.expense_type}>
                  <span className="bar-chart__label">{categoryLabel(c.expense_type)}</span>
                  <span className="bar-chart__track">
                    <span className="bar-chart__bar" style={{ width: `${(c.total_amount / maxSpend) * 100}%` }} />
                  </span>
                  <span className="bar-chart__value">{formatINR(c.total_amount)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}
