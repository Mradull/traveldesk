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

export default function NavBar() {
  const { isManager, logout } = useAuth();
  const links = isManager ? MANAGER_LINKS : EMPLOYEE_LINKS;
  const linkClass = ({ isActive }) => (isActive ? "sidebar__link sidebar__link--active" : "sidebar__link");

  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <Plane size={20} aria-hidden="true" />
        <span>TravelDesk</span>
      </div>
      <nav className="sidebar__nav" aria-label="Main">
        {links.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className={linkClass}>
            <Icon size={18} aria-hidden="true" />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
      <button type="button" className="sidebar__link sidebar__logout" onClick={logout}>
        <LogOut size={18} aria-hidden="true" />
        <span>Logout</span>
      </button>
    </aside>
  );
}
