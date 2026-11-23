import { NavLink } from "react-router-dom";
import { BarChart3, ClipboardCheck, LayoutDashboard, LogOut, Map, Plane, PlusCircle } from "lucide-react";
import { useAuth } from "../context/AuthContext";

// Managers have no Create Trip, no own trips and no Vera
const EMPLOYEE_LINKS = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/trips", label: "My Trips", icon: Map, end: true },
  { to: "/trips/new", label: "Create Trip", icon: PlusCircle },
];
const MANAGER_LINKS = [
  { to: "/manager/approvals", label: "Approvals", icon: ClipboardCheck },
  { to: "/manager/reports", label: "Spending Summary", icon: BarChart3 },
];

/** Executive sidebar: charcoal, yellow active bar, logout at the bottom */
export default function NavBar() {
  const { isManager, logout } = useAuth();
  const links = isManager ? MANAGER_LINKS : EMPLOYEE_LINKS;
  const linkClass = ({ isActive }) => (isActive ? "sidebar__link sidebar__link--active" : "sidebar__link");

  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <span className="sidebar__logo" aria-hidden="true"><Plane size={18} /></span>
        <span className="sidebar__name">
          TravelDesk
          <small>{isManager ? "Manager view" : "Employee view"}</small>
        </span>
      </div>

      <p className="sidebar__label">Menu</p>
      <nav className="sidebar__nav" aria-label="Main">
        {links.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className={linkClass}>
            <Icon size={18} aria-hidden="true" />
            <span>{label}</span>
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
  );
}
