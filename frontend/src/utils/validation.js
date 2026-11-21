// =====================================================================
// Client-side validation (same rules as schemas.py, so most mistakes are
// caught before the request). FastAPI stays the final authority.
// =====================================================================
import {
  DESTINATION_PATTERN, INVOICE_PATTERN, MAX_DAYS_IN_ADVANCE, MAX_DESCRIPTION_CHARS, MAX_LINE_AMOUNT_INR,
  MAX_LINES_PER_TICKET, MAX_PURPOSE_CHARS, MAX_TRIP_DAYS, MIN_DESCRIPTION_CHARS, MIN_PURPOSE_CHARS,
} from "./constants";
import { addDaysISO, formatDate, todayISO, tripLengthDays } from "./format";

/** Trip request rules (TripBase). Returns { field: message }; empty means valid. */
export function validateTrip({ destination, start_date, end_date, purpose }) {
  const errors = {};

  const dest = (destination ?? "").trim().replace(/\s+/g, " ");
  if (!dest) errors.destination = "Enter a destination.";
  else if (!DESTINATION_PATTERN.test(dest)) errors.destination = "Use a city name with letters, spaces and . , ' ( ) -";

  const p = (purpose ?? "").trim();
  if (p.length < MIN_PURPOSE_CHARS) errors.purpose = `Purpose must be at least ${MIN_PURPOSE_CHARS} characters.`;
  else if (p.length > MAX_PURPOSE_CHARS) errors.purpose = `Purpose can be at most ${MAX_PURPOSE_CHARS} characters.`;

  const today = todayISO();
  const latestStart = addDaysISO(today, MAX_DAYS_IN_ADVANCE);
  if (!start_date) errors.start_date = "Choose a start date.";
  else if (start_date < today) errors.start_date = "Start date can't be in the past.";
  else if (start_date > latestStart) errors.start_date = `Trips can be requested at most ${MAX_DAYS_IN_ADVANCE} days ahead.`;

  if (!end_date) errors.end_date = "Choose an end date.";
  else if (start_date && end_date <= start_date) errors.end_date = "End date must be after the start date.";
  else if (start_date && tripLengthDays(start_date, end_date) > MAX_TRIP_DAYS) {
    errors.end_date = `A trip can last at most ${MAX_TRIP_DAYS} days.`;
  }

  return errors;
}

/**
 * Expense lines rules (ExpenseLineCreate / TicketCreate). Errors use the API's paths,
 * e.g. "expenses.1.amount", so client and server errors show in the same place.
 */
export function validateExpenseLines(lines, tripCreatedOn) {
  const errors = {};
  if (lines.length < 1) errors._form = "Add at least one expense line.";
  if (lines.length > MAX_LINES_PER_TICKET) errors._form = `A ticket can have at most ${MAX_LINES_PER_TICKET} lines.`;

  const today = todayISO();
  const photos = new Set();
  const invoices = new Set();

  lines.forEach((line, i) => {
    const p = `expenses.${i}`;
    if (!line.expense_type) errors[`${p}.expense_type`] = "Choose a category.";

    const amount = Number(line.amount);
    if (line.amount === "" || line.amount == null || Number.isNaN(amount) || amount <= 0) {
      errors[`${p}.amount`] = "Enter an amount above 0.";
    } else if (amount > MAX_LINE_AMOUNT_INR) {
      errors[`${p}.amount`] = "The maximum is ₹2,00,000 per line.";
    } else if (!/^\d+(\.\d{1,2})?$/.test(String(line.amount))) {
      errors[`${p}.amount`] = "Use at most 2 decimal places.";
    }

    if (!line.expense_date) errors[`${p}.expense_date`] = "Choose the expense date.";
    else if (line.expense_date > today) errors[`${p}.expense_date`] = "Expense date can't be in the future.";
    else if (tripCreatedOn && line.expense_date < tripCreatedOn) {
      errors[`${p}.expense_date`] = `Must be on or after ${formatDate(tripCreatedOn)}, when the trip was created.`;
    }

    const description = (line.description ?? "").trim();
    if (description.length < MIN_DESCRIPTION_CHARS) errors[`${p}.description`] = "Describe the expense (3+ characters).";
    else if (description.length > MAX_DESCRIPTION_CHARS) errors[`${p}.description`] = "Keep the description under 300 characters.";

    if (!line.evidence_id) errors[`${p}.evidence_id`] = "Attach a receipt photo.";
    else if (photos.has(line.evidence_id)) errors[`${p}.evidence_id`] = "Each line needs its own photo.";
    else photos.add(line.evidence_id);

    const invoice = (line.invoice_number ?? "").trim().toUpperCase();
    if (invoice) {
      if (!INVOICE_PATTERN.test(invoice)) errors[`${p}.invoice_number`] = "3–50 letters, numbers, - _ or /";
      else if (invoices.has(invoice)) errors[`${p}.invoice_number`] = "This invoice number is already on another line.";
      else invoices.add(invoice);
    }
  });

  return errors;
}

/**
 * Turns a 422 from FastAPI into { "field": "message" }.
 * Keeps nested paths: ["body","expenses",0,"expense_date"] -> "expenses.0.expense_date".
 * Errors not tied to a field go under "_form".
 */
export function fieldErrorsFromApi(err) {
  const out = {};
  if (!Array.isArray(err?.details)) return out;
  for (const d of err.details) {
    const field = d.field ?? (Array.isArray(d.loc) ? d.loc.filter((part) => part !== "body").join(".") : null);
    const message = String(d.message ?? d.msg ?? "Invalid value").replace(/^Value error,\s*/i, "");
    if (field) out[field] = message;
    else out._form = message;
  }
  return out;
}
