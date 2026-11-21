import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { homePathFor, ROLES } from "../utils/constants";
import Loader from "../components/Loader";

/** Employee view only. Managers are sent to their own home page. */
export default function EmployeeRoute({ children }) {
  const { user, checking } = useAuth();
  const location = useLocation();
  if (checking) return <Loader label="Checking your session…" />;
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />;
  if (user.role !== ROLES.EMPLOYEE) return <Navigate to={homePathFor(user)} replace />;
  return children;
}
