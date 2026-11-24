import { useEffect, useState } from "react";
import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { Menu, Moon, Sun } from "lucide-react";
import { UiProvider } from "./components/ui/UiProvider";
import { useTheme } from "./hooks/useTheme";
import { useAuth } from "./context/AuthContext";
import { homePathFor } from "./utils/constants";
import EmployeeRoute from "./routes/EmployeeRoute";
import ManagerRoute from "./routes/ManagerRoute";
import NavBar from "./components/NavBar";
import Loader from "./components/Loader";
import LoginPage from "./pages/LoginPage";

// Employee view
import DashboardPage from "./pages/employee/DashboardPage";
import MyTripsPage from "./pages/employee/MyTripsPage";
import CreateTripPage from "./pages/employee/CreateTripPage";
import TripDetailPage from "./pages/employee/TripDetailPage";
import RaiseTicketPage from "./pages/employee/RaiseTicketPage";
import TicketDetailPage from "./pages/employee/TicketDetailPage";

// Manager view
import ApprovalsPage from "./pages/manager/ApprovalsPage";
import TripReviewPage from "./pages/manager/TripReviewPage";
import TicketReviewPage from "./pages/manager/TicketReviewPage";
import SpendingSummaryPage from "./pages/manager/SpendingSummaryPage";

/** Sidebar on the left, top bar with the signed-in user, page content */
function AppLayout({ theme }) {
  const { user, isManager } = useAuth();
  const [navOpen, setNavOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setNavOpen(false), [location.pathname]);   // close the phone menu after navigating
  const initials = (user?.full_name ?? "?").split(" ").map((p) => p[0]).join("").slice(0, 2);
  const today = new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  return (
    <div className="shell">
      <NavBar open={navOpen} onClose={() => setNavOpen(false)} />
      <div className="shell__main">
        <header className="topbar">
          <button
            type="button" className="icon-btn topbar__menu" onClick={() => setNavOpen(true)}
            aria-label="Open menu" aria-expanded={navOpen} aria-controls="main-sidebar"
          >
            <Menu size={22} />
          </button>
          <span className="topbar__date">{today}</span>
          <div className="topbar__right">
          <button
            type="button" className="icon-btn theme-toggle" onClick={theme.toggle}
            aria-label={theme.theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            title={theme.theme === "dark" ? "Light mode" : "Dark mode"}
          >
            {theme.theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <div className="user-chip">
            <span className="user-chip__avatar" aria-hidden="true">{initials}</span>
            <div>
              <div className="user-chip__name">{user?.full_name}</div>
              <div className="user-chip__role">{isManager ? "Manager" : "Employee"}</div>
            </div>
          </div>
          </div>
        </header>
        <main className="container">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function HomeRedirect() {
  const { user, checking } = useAuth();
  if (checking) return <Loader label="Checking your session…" />;
  return <Navigate to={user ? homePathFor(user) : "/login"} replace />;
}

export default function App() {
  const theme = useTheme();
  return (
    <UiProvider>
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route element={<EmployeeRoute><AppLayout theme={theme} /></EmployeeRoute>}>
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/trips" element={<MyTripsPage />} />
        <Route path="/trips/new" element={<CreateTripPage />} />
        <Route path="/trips/:tripId" element={<TripDetailPage />} />
        <Route path="/trips/:tripId/expenses/new" element={<RaiseTicketPage />} />
        <Route path="/tickets/:ticketId" element={<TicketDetailPage />} />
      </Route>

      <Route element={<ManagerRoute><AppLayout theme={theme} /></ManagerRoute>}>
        <Route path="/manager/approvals" element={<ApprovalsPage />} />
        <Route path="/manager/trips/:tripId" element={<TripReviewPage />} />
        <Route path="/manager/tickets/:ticketId" element={<TicketReviewPage />} />
        <Route path="/manager/reports" element={<SpendingSummaryPage />} />
      </Route>

      <Route path="*" element={<HomeRedirect />} />
    </Routes>
    </UiProvider>
  );
}
