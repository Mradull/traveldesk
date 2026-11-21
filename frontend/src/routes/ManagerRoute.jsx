import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { homePathFor, ROLES } from "../utils/constants";
import Loader from "../components/Loader";

/** Manager view only. Employees are sent to their own home page. */
export default function ManagerRoute({ children }) {
  const { user, checking } = useAuth();
  const location = useLocation();
  if (checking) return <Loader label="Checking your session…" />;
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />;
  if (user.role !== ROLES.MANAGER) return <Navigate to={homePathFor(user)} replace />;
  return children;
}
