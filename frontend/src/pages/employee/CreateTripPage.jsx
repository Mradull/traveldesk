// /trips/new: TripForm with date limits (today..+365, end > start, <= 30 days).
// Owner: Mradul (M3)
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import TripForm from "../../components/TripForm";
import ErrorBanner from "../../components/ErrorBanner";
import StatusBadge from "../../components/StatusBadge";
import { createTrip } from "../../api/trips";
import { fieldErrorsFromApi } from "../../utils/validation";
import { formatDateRange } from "../../utils/format";

export default function CreateTripPage() {
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [serverErrors, setServerErrors] = useState({});
  const [created, setCreated] = useState(null);
  const [formKey, setFormKey] = useState(0); // changing the key resets the form

  async function handleSubmit(values) {
    setSubmitting(true);
    setError(null);
    setServerErrors({});
    try {
      setCreated(await createTrip(values));
    } catch (err) {
      const fields = fieldErrorsFromApi(err);
      if (Object.keys(fields).length > 0) setServerErrors(fields);
      else setError(err);
    } finally {
      setSubmitting(false);
    }
  }

  function startAnother() {
    setCreated(null);
    setFormKey((k) => k + 1);
  }

  if (created) {
    return (
      <section className="narrow">
        <div className="card success">
          <h1>Travel request submitted</h1>
          <p className="success__code">{created.trip_code}</p>
          <p><strong>{created.destination}</strong>, {formatDateRange(created.start_date, created.end_date)}</p>
          <p>Status: <StatusBadge status={created.status_label} /></p>
          <p className="muted">Your manager will review it. You can still edit it until they decide.</p>
          <div className="form-actions">
            <Link className="btn btn--primary" to={`/trips/${created.trip_id}`}>View trip</Link>
            <Link className="btn btn--secondary" to="/trips">Back to My Trips</Link>
            <button type="button" className="btn btn--ghost" onClick={startAnother}>Request another trip</button>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="narrow">
      <div className="page-header">
        <div>
          <h1>New travel request</h1>
          <p className="muted">Your manager approves or rejects it. You can edit it until then.</p>
        </div>
      </div>
      <div className="card">
        <ErrorBanner error={error} />
        <TripForm key={formKey} onSubmit={handleSubmit} submitting={submitting} serverErrors={serverErrors} onCancel={() => navigate("/trips")} />
      </div>
    </section>
  );
}
