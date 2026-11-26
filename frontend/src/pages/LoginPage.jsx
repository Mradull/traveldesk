import { useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { CheckCircle2, Eye, EyeOff, Plane } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import ErrorBanner from "../components/ErrorBanner";
import { MOCK_PASSWORD, MOCK_USERS } from "../api/mocks";
import { homePathFor, USE_MOCKS } from "../utils/constants";

const FEATURES = [
  "Request trips and track approvals",
  "Claim expenses with a receipt photo on every line",
  "Ask Vera about the policy and the weather",
];

export default function LoginPage() {
  const { user, login, sessionMessage } = useAuth();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  if (user) {
    // Return to the page they wanted only if it belongs to their role
    const from = location.state?.from?.pathname;
    const fits = from && (user.role === "MANAGER" ? from.startsWith("/manager") : !from.startsWith("/manager"));
    return <Navigate to={fits ? from : homePathFor(user)} replace />;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!email.trim() || !password) {
      setError("Enter your email and password.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await login(email.trim(), password);
    } catch (err) {
      setError(err);
      setSubmitting(false);
    }
  }

  return (
    <div className="login">
      <section className="login__brand" aria-label="About TravelDesk">
        <div className="login__logo-row">
          <span className="sidebar__logo" aria-hidden="true"><Plane size={18} /></span>
          TravelDesk
        </div>
        <div>
          <h2>Business travel and expenses, <span>without the paperwork.</span></h2>
          <ul className="login__features">
            {FEATURES.map((f) => (
              <li key={f}><CheckCircle2 size={18} aria-hidden="true" />{f}</li>
            ))}
          </ul>
        </div>
        <p className="login__foot">Veridian Global Services · Travel &amp; Expense</p>
      </section>

      <main className="login__panel">
        <form className="login__card" onSubmit={handleSubmit} noValidate>
          <h1>TravelDesk</h1>
          <p className="muted">Sign in with your company email.</p>

          {sessionMessage && <div className="alert alert--info"><p>{sessionMessage}</p></div>}
          <ErrorBanner error={error} />

          <label className="field">
            <span>Email</span>
            <input
              type="email" autoComplete="username" value={email} placeholder="name@veridian.example"
              onChange={(e) => setEmail(e.target.value)} disabled={submitting}
            />
          </label>

          <label className="field">
            <span>Password</span>
            <div className="password-field">
              <input
                type={showPassword ? "text" : "password"} autoComplete="current-password" value={password}
                onChange={(e) => setPassword(e.target.value)} disabled={submitting}
              />
              <button type="button" onClick={() => setShowPassword((s) => !s)} aria-label={showPassword ? "Hide password" : "Show password"}>
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </label>

          <button type="submit" className="btn btn--primary btn--block" disabled={submitting}>
            {submitting ? "Signing in…" : "Sign in"}
          </button>

          {USE_MOCKS && (
            <div className="login__demo">
              <p><strong>Mock mode</strong>, password <code>{MOCK_PASSWORD}</code></p>
              {MOCK_USERS.map((u) => (
                <button
                  key={u.email} type="button" className="btn btn--ghost btn--small"
                  onClick={() => { setEmail(u.email); setPassword(MOCK_PASSWORD); }}
                >
                  {u.full_name} ({u.role === "MANAGER" ? "Manager" : "Employee"})
                </button>
              ))}
            </div>
          )}
        </form>
      </main>
    </div>
  );
}
