import { useState } from "react";
import { MAX_DAYS_IN_ADVANCE, MAX_PURPOSE_CHARS, MAX_TRIP_DAYS } from "../utils/constants";
import { addDaysISO, todayISO } from "../utils/format";
import { validateTrip } from "../utils/validation";

const EMPTY = { destination: "", start_date: "", end_date: "", purpose: "" };

function FieldError({ id, message }) {
  if (!message) return null;
  return <span id={id} className="field__error">{message}</span>;
}

/**
 * Create and edit trip form.
 *  initialValues  values to start with (edit mode)
 *  onSubmit       called with clean values when the form is valid
 *  submitting     disables the form while the request runs
 *  serverErrors   { field: message } from a 422 response
 */
export default function TripForm({
  initialValues = EMPTY, onSubmit, submitting = false, serverErrors = {},
  submitLabel = "Submit request", onCancel,
}) {
  const [values, setValues] = useState(initialValues);
  const [errors, setErrors] = useState({});
  const [attempted, setAttempted] = useState(false); // validate live only after the first submit

  const shown = { ...serverErrors, ...errors };
  const today = todayISO();
  const latestStart = addDaysISO(today, MAX_DAYS_IN_ADVANCE);
  const earliestEnd = values.start_date ? addDaysISO(values.start_date, 1) : today;
  const latestEnd = values.start_date ? addDaysISO(values.start_date, MAX_TRIP_DAYS - 1) : undefined;

  function update(field, value) {
    const next = { ...values, [field]: value };
    setValues(next);
    if (attempted) setErrors(validateTrip(next));
  }

  function handleSubmit(event) {
    event.preventDefault();
    setAttempted(true);
    const found = validateTrip(values);
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    onSubmit({
      destination: values.destination.trim().replace(/\s+/g, " "),
      start_date: values.start_date,
      end_date: values.end_date,
      purpose: values.purpose.trim(),
    });
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      {shown._form && <div className="alert alert--error"><p>{shown._form}</p></div>}

      <label className="field">
        <span>Destination</span>
        <input
          value={values.destination}
          onChange={(e) => update("destination", e.target.value)}
          placeholder="e.g. Bengaluru"
          disabled={submitting}
          aria-invalid={Boolean(shown.destination)}
          aria-describedby="destination-error"
        />
        <FieldError id="destination-error" message={shown.destination} />
      </label>

      <div className="form-row">
        <label className="field">
          <span>Start date</span>
          <input
            type="date"
            value={values.start_date}
            min={today}
            max={latestStart}
            onChange={(e) => update("start_date", e.target.value)}
            disabled={submitting}
            aria-invalid={Boolean(shown.start_date)}
            aria-describedby="start-error"
          />
          <FieldError id="start-error" message={shown.start_date} />
        </label>

        <label className="field">
          <span>End date</span>
          <input
            type="date"
            value={values.end_date}
            min={earliestEnd}
            max={latestEnd}
            onChange={(e) => update("end_date", e.target.value)}
            disabled={submitting}
            aria-invalid={Boolean(shown.end_date)}
            aria-describedby="end-error"
          />
          <FieldError id="end-error" message={shown.end_date} />
        </label>
      </div>
      <p className="hint">
        Trips start today or later (up to {MAX_DAYS_IN_ADVANCE} days ahead), end after the start date and last at most {MAX_TRIP_DAYS} days.
      </p>

      <label className="field">
        <span>Purpose</span>
        <textarea
          rows={4}
          value={values.purpose}
          maxLength={MAX_PURPOSE_CHARS}
          onChange={(e) => update("purpose", e.target.value)}
          placeholder="e.g. Client workshop for FY27 audit planning"
          disabled={submitting}
          aria-invalid={Boolean(shown.purpose)}
          aria-describedby="purpose-error"
        />
        <span className="hint">{values.purpose.trim().length} / {MAX_PURPOSE_CHARS}</span>
        <FieldError id="purpose-error" message={shown.purpose} />
      </label>

      <div className="form-actions">
        {onCancel && (
          <button type="button" className="btn btn--secondary" onClick={onCancel} disabled={submitting}>Cancel</button>
        )}
        <button type="submit" className="btn btn--primary" disabled={submitting}>
          {submitting ? "Saving…" : submitLabel}
        </button>
      </div>
    </form>
  );
}
