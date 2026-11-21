// =====================================================================
// Formatting and date helpers (all dates are local calendar days)
// =====================================================================

const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", minimumFractionDigits: 2 });

/** 18500 -> "₹18,500.00" */
export function formatINR(value) {
  if (value === null || value === undefined || value === "") return "–";
  return inr.format(Number(value));
}

/** "2026-11-25" -> "25 Nov 2026". Date-only strings are read as local dates, not UTC. */
export function formatDate(value) {
  if (!value) return "–";
  const d = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

/** ISO timestamp -> "25 Nov 2026, 10:42 am" */
export function formatDateTime(value) {
  if (!value) return "–";
  return new Date(value).toLocaleString("en-IN", {
    day: "2-digit", month: "short", year: "numeric", hour: "numeric", minute: "2-digit",
  });
}

export function formatDateRange(start, end) {
  return `${formatDate(start)} – ${formatDate(end)}`;
}

/** Date -> "2026-11-25" using the local calendar day */
export function toISODate(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export const todayISO = () => toISODate(new Date());

/** addDaysISO("2026-11-25", 3) -> "2026-11-28" */
export function addDaysISO(iso, days) {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  return toISODate(d);
}

/** Inclusive length: 25 Nov to 27 Nov is 3 days */
export function tripLengthDays(start, end) {
  const ms = new Date(`${end}T00:00:00`) - new Date(`${start}T00:00:00`);
  return Math.round(ms / 86400000) + 1;
}

/** Same labels the backend sends in status_label */
export function statusLabel(approvalStatus, tripState) {
  if (approvalStatus === "IN_PROGRESS") return "In Progress";
  if (approvalStatus === "REJECTED") return "Rejected";
  return tripState === "COMPLETED" ? "Approved - Completed" : "Approved - Active";
}

/** How long something has been waiting: "today", "1 day", "4 days" */
export function ageLabel(iso) {
  if (!iso) return "–";
  const start = new Date(iso);
  start.setHours(0, 0, 0, 0);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const days = Math.round((today - start) / 86400000);
  if (days <= 0) return "today";
  return days === 1 ? "1 day" : `${days} days`;
}
