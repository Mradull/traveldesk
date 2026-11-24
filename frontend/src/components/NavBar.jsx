import { useEffect } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { BarChart3, ClipboardCheck, LayoutDashboard, LogOut, Map, Plane, PlusCircle, X } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useApi } from "../hooks/useApi";
import { listPendingTrips, listTripsToComplete } from "../api/trips";
import { listPendingTickets } from "../api/tickets";

// Managers have no Create Trip, no own trips and no Vera
const EMPLOYEE_LINKS = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/trips", label: "My Trips", icon: Map, end: true },
  { to: "/trips/new", label: "Create Trip", icon: PlusCircle },
];
const MANAGER_LINKS = [
  { to: "/manager/approvals", label: "Approvals", icon: ClipboardCheck, badge: "pending" },
  { to: "/manager/reports", label: "Spending Summary", icon: BarChart3 },
];

/** #10: number of items waiting for the manager, refreshed on every page change */
function usePendingCount(enabled) {
  const location = useLocation();
  const { data, reload } = useApi(async () => {
    if (!enabled) return 0;
    const lists = await Promise.all([listPendingTrips(), listPendingTickets(), listTripsToComplete()].map((p) => p.catch(() => [])));
    return lists.reduce((n, list) => n + (list?.length ?? 0), 0);
  }, [enabled]);
  useEffect(() => { if (enabled) reload(); }, [location.pathname, location.search]); // eslint-disable-line react-hooks/exhaustive-deps
  return data ?? 0;
}

/** Executive sidebar; on phones a drawer opened from the top bar (#16) */
export default function NavBar({ open = false, onClose }) {
  const { isManager, logout } = useAuth();
  const links = isManager ? MANAGER_LINKS : EMPLOYEE_LINKS;
  const pending = usePendingCount(isManager);
  const linkClass = ({ isActive }) => (isActive ? "sidebar__link sidebar__link--active" : "sidebar__link");

  return (
    <>
      {open && <div className="sidebar-backdrop" onClick={onClose} aria-hidden="true" />}
      <aside className={open ? "sidebar sidebar--open" : "sidebar"} id="main-sidebar">
        <div className="sidebar__brand">
          <span className="sidebar__logo" aria-hidden="true"><Plane size={18} /></span>
          <span className="sidebar__name">
            TravelDesk
            <small>{isManager ? "Manager view" : "Employee view"}</small>
          </span>
          <button type="button" className="icon-btn sidebar__close" onClick={onClose} aria-label="Close menu"><X size={20} /></button>
        </div>

        <p className="sidebar__label">Menu</p>
        <nav className="sidebar__nav" aria-label="Main">
          {links.map(({ to, label, icon: Icon, end, badge }) => (
            <NavLink key={to} to={to} end={end} className={linkClass} onClick={onClose}>
              <Icon size={18} aria-hidden="true" />
              <span>{label}</span>
              {badge === "pending" && pending > 0 && (
                <span className="sidebar__badge" aria-label={`${pending} waiting`}>{pending}</span>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar__footer">
          <button type="button" className="sidebar__link sidebar__logout" onClick={logout}>
            <LogOut size={18} aria-hidden="true" />
            <span>Logout</span>
          </button>
        </div>
      </aside>
    </>
  );
}
