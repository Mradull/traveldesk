// =====================================================================
// MOCK BACKEND (only used when VITE_USE_MOCKS=true in frontend/.env)
// Mirrors the Spec v2.0 seed data and rules so screens can be built and
// demoed without FastAPI. Delete this file before submission.
// =====================================================================
import { ApiError } from "./client";
import {
  ERROR_MESSAGES, EVIDENCE_MAX_BYTES, EVIDENCE_TYPES, MIN_REVIEW_COMMENT_CHARS, POLICY_THRESHOLDS,
  REJECTION_REASONS, STORAGE_KEYS, TRIP_AUTO_COMPLETE_DAYS,
} from "../utils/constants";
import { addDaysISO, statusLabel, todayISO } from "../utils/format";
import { validateExpenseLines, validateTrip } from "../utils/validation";

// =====================================================================
// Users (same people as database/seed/seed_data.sql).
// Use the same password as SEED_DEMO_PASSWORD in backend/.env
// =====================================================================
export const MOCK_PASSWORD = "Demo@123";

export const MOCK_USERS = [
  { employee_id: 1, full_name: "Vikram Iyer", email: "vikram.iyer@veridian.example", department: "Advisory", role: "MANAGER", manager_id: null },
  { employee_id: 2, full_name: "Ananya Rao", email: "ananya.rao@veridian.example", department: "Consulting", role: "EMPLOYEE", manager_id: 1 },
  { employee_id: 3, full_name: "Rohan Mehta", email: "rohan.mehta@veridian.example", department: "Tax", role: "EMPLOYEE", manager_id: 1 },
  { employee_id: 4, full_name: "Sara Thomas", email: "sara.thomas@veridian.example", department: "Assurance", role: "EMPLOYEE", manager_id: 1 },
];

// ---------- helpers ----------
const delay = (ms = 400) => new Promise((resolve) => setTimeout(resolve, ms));
const D = (offset) => addDaysISO(todayISO(), offset);               // D-5, D+3 ... like the seed
const at = (offset, time = "10:00:00") => `${D(offset)}T${time}`;
const nowISO = () => new Date().toISOString();
const code = (prefix, id) => `${prefix}-${String(id).padStart(5, "0")}`;
const userById = (id) => MOCK_USERS.find((u) => u.employee_id === id);
const reportsTo = (me, employeeId) => userById(employeeId)?.manager_id === me.employee_id;

function apiError(status, errorCode, details = null) {
  return new ApiError({ status, code: errorCode, message: ERROR_MESSAGES[errorCode] ?? "Something went wrong.", details });
}

function validationError(errors) {
  return apiError(422, "VALIDATION_ERROR", Object.entries(errors).map(([field, message]) => ({ field, message })));
}

// ---------- auth ----------
export async function mockLogin(email, password) {
  await delay();
  const user = MOCK_USERS.find((u) => u.email === email.toLowerCase());
  if (!user || password !== MOCK_PASSWORD) throw apiError(401, "INVALID_CREDENTIALS");
  return { access_token: `mock-token-${user.employee_id}`, token_type: "bearer", expires_in: 3600, user };
}

function requireMockUser(role) {
  const token = sessionStorage.getItem(STORAGE_KEYS.TOKEN) ?? "";
  const user = userById(Number(token.replace("mock-token-", "")));
  if (!user) throw apiError(401, "INVALID_TOKEN");
  if (role && user.role !== role) throw apiError(403, "FORBIDDEN");
  return user;
}

export async function mockMe() {
  await delay(200);
  return requireMockUser();
}

// =====================================================================
// Storage: localStorage so data survives a reload, like a real database
// =====================================================================
const TRIPS_KEY = "td_mock_trips_v3";
const TICKETS_KEY = "td_mock_tickets_v3";

function loadStore(key, seed) {
  try {
    const stored = JSON.parse(localStorage.getItem(key));
    if (Array.isArray(stored)) return stored;
  } catch {
    /* corrupted storage: reseed below */
  }
  const seeded = seed();
  localStorage.setItem(key, JSON.stringify(seeded));
  return seeded;
}

const saveStore = (key, value) => localStorage.setItem(key, JSON.stringify(value));
const saveTrips = (trips) => saveStore(TRIPS_KEY, trips);
const loadTickets = () => loadStore(TICKETS_KEY, seedTickets);

/** Active trips auto-complete at start date + 90 days (the backend scheduler does this hourly) */
function loadTrips() {
  const trips = loadStore(TRIPS_KEY, seedTrips);
  let changed = false;
  for (const t of trips) {
    if (t.trip_state === "ACTIVE" && todayISO() >= addDaysISO(t.start_date, TRIP_AUTO_COMPLETE_DAYS)) {
      Object.assign(t, { trip_state: "COMPLETED", completion_type: "AUTO", completed_at: nowISO() });
      changed = true;
    }
  }
  if (changed) saveTrips(trips);
  return trips;
}

/** Start fresh: run localStorage.clear() in the browser console, or call this */
export function resetMockData() {
  localStorage.removeItem(TRIPS_KEY);
  localStorage.removeItem(TICKETS_KEY);
}

// =====================================================================
// Seed data (Spec v2.0 > Seed data)
// =====================================================================
function tripApproval(id, tripId, decision, comment, offset) {
  return {
    approval_id: id, trip_id: tripId, reviewer_id: 1, reviewer_name: "Vikram Iyer",
    decision, review_comment: comment, decided_at: at(offset, "11:00:00"),
  };
}

function seedTrip(id, employeeId, destination, createdOffset, startOffset, endOffset, purpose, status, state, approvals = []) {
  return {
    trip_id: id, trip_code: code("TRP", id), employee_id: employeeId, destination,
    start_date: D(startOffset), end_date: D(endOffset), purpose,
    approval_status: status, trip_state: state, approvals,
    completion_type: null, completed_by: null, completed_by_name: null, completed_at: null,
    created_on: D(createdOffset), created_at: at(createdOffset, "09:00:00"), updated_at: at(createdOffset, "09:00:00"),
  };
}

function seedTrips() {
  return [
    seedTrip(1, 2, "Mumbai", -30, -20, -17, "Client audit kickoff with the Mumbai team", "APPROVED", "ACTIVE",
      [tripApproval(1, 1, "APPROVED", null, -29)]),
    seedTrip(2, 3, "Bengaluru", -5, 3, 6, "Client workshop for FY27 audit planning", "APPROVED", "ACTIVE",
      [tripApproval(2, 2, "APPROVED", null, -4)]),
    seedTrip(3, 4, "Singapore", -2, 40, 44, "Regional assurance conference and partner meetings", "APPROVED", "ACTIVE",
      [tripApproval(3, 3, "APPROVED", null, -2)]),
    seedTrip(4, 3, "Jaipur", -1, 20, 22, "Tax advisory session with the Jaipur client", "IN_PROGRESS", null),
  ];
}

function flag(rule, type) {
  if (rule === "OVER_THRESHOLD") {
    const limit = POLICY_THRESHOLDS[type];
    return {
      rule_code: rule,
      message: `${type} amount is above the ₹${limit.toLocaleString("en-IN")} review threshold`,
      policy_ref: "[POL-6.2]",
      threshold_amount: limit,
    };
  }
  return { rule_code: rule, message: "Same receipt photo or invoice number claimed before", policy_ref: "[POL-7.4]", threshold_amount: null };
}

function seedLine(id, type, amount, offset, description, flags = []) {
  return {
    expense_id: id, expense_code: code("EXP", id), expense_type: type, amount, currency: "INR",
    expense_date: D(offset), description, invoice_number: null,
    evidence_id: `mock-evd-${id}`, evidence_code: code("EVD", id),
    flags: flags.map((r) => flag(r, type)),
  };
}

function seedTicket(id, tripId, employeeId, status, submittedOffset, lines, decision = null) {
  const submitted = at(submittedOffset, "12:00:00");
  const flagCount = lines.reduce((n, l) => n + l.flags.length, 0);
  let history = [];
  if (status === "AUTO_APPROVED") {
    history = [{
      approval_id: id, ticket_id: id, reviewer_type: "SYSTEM", reviewer_id: null, reviewer_name: "SYSTEM",
      decision: "AUTO_APPROVED", rejection_reason: null, review_comment: null, decided_at: submitted,
    }];
  } else if (decision) {
    history = [{ approval_id: id, ticket_id: id, reviewer_type: "MANAGER", reviewer_id: 1, reviewer_name: "Vikram Iyer", ...decision }];
  }
  return {
    ticket_id: id, ticket_code: code("TKT", id), trip_id: tripId, employee_id: employeeId,
    replacement_of_ticket_id: null, status, routing: status === "AUTO_APPROVED" ? "AUTO" : "MANAGER",
    line_count: lines.length, flag_count: flagCount,
    total_amount: lines.reduce((s, l) => s + l.amount, 0),
    submitted_at: submitted, decided_at: history[0]?.decided_at ?? null,
    expenses: lines.map((l) => ({ ...l, status })), history,
  };
}

function seedTickets() {
  return [
    seedTicket(1, 1, 2, "AUTO_APPROVED", -17, [
      seedLine(1, "AIRFARE", 8500, -28, "Return flight to Mumbai"),
      seedLine(2, "LODGING", 6200, -20, "Hotel, 3 nights"),
    ]),
    seedTicket(2, 1, 2, "APPROVED", -17, [
      seedLine(3, "MEALS", 2400, -19, "Client dinner", ["OVER_THRESHOLD"]),
      seedLine(4, "INCIDENTALS", 400, -18, "Local SIM card"),
    ], {
      decision: "APPROVED", rejection_reason: null,
      review_comment: "Client dinner with three attendees; approved as an exception.", decided_at: at(-16, "15:00:00"),
    }),
    seedTicket(3, 2, 3, "PENDING", -1, [
      seedLine(5, "AIRFARE", 24500, -1, "Return flight to Bengaluru", ["OVER_THRESHOLD"]),
      seedLine(6, "LODGING", 6000, -1, "Hotel advance"),
    ]),
    seedTicket(4, 2, 3, "REJECTED", -1, [
      seedLine(7, "AIRFARE", 4200, -1, "Extra baggage"),
    ], {
      decision: "REJECTED", rejection_reason: "INSUFFICIENT_EVIDENCE",
      review_comment: "Photo is blurred and the amount is not readable. Raise a new ticket with a clear photo.",
      decided_at: at(0, "09:30:00"),
    }),
    seedTicket(5, 3, 4, "AUTO_APPROVED", -1, [
      seedLine(8, "AIRFARE", 18000, -1, "Flight to Singapore"),
    ]),
  ];
}

// =====================================================================
// Trips
// =====================================================================
function summarizeTicket(k) {
  const { expenses, history, ...summary } = k; // eslint-disable-line no-unused-vars
  return summary;
}

/** Adds what the backend computes: label, permissions, totals, tickets */
function enrichTrip(trip, me) {
  const owner = userById(trip.employee_id);
  const tickets = loadTickets()
    .filter((k) => k.trip_id === trip.trip_id)
    .sort((a, b) => b.submitted_at.localeCompare(a.submitted_at))
    .map(summarizeTicket);
  const autoOn = addDaysISO(trip.start_date, TRIP_AUTO_COMPLETE_DAYS);
  const active = trip.approval_status === "APPROVED" && trip.trip_state === "ACTIVE";
  const isOwner = trip.employee_id === me.employee_id;
  const isApprover = reportsTo(me, trip.employee_id);
  return {
    ...trip,
    employee_name: owner.full_name,
    department: owner.department,
    status_label: statusLabel(trip.approval_status, trip.trip_state),
    is_owner: isOwner,
    can_edit: isOwner && trip.approval_status === "IN_PROGRESS",
    can_raise_ticket: isOwner && active && todayISO() < autoOn,
    can_complete: isApprover && active && todayISO() >= trip.end_date,
    auto_close_on: autoOn,
    ticket_count: tickets.length,
    pending_ticket_count: tickets.filter((k) => k.status === "PENDING").length,
    total_claimed: tickets.filter((k) => k.status !== "REJECTED").reduce((s, k) => s + k.total_amount, 0),
    tickets,
  };
}

/** Owner or their direct manager can see a trip; everyone else gets 404 */
function findVisibleTrip(trips, tripId, me) {
  const trip = trips.find((t) => t.trip_id === Number(tripId));
  if (!trip) return null;
  return trip.employee_id === me.employee_id || reportsTo(me, trip.employee_id) ? trip : null;
}

export async function mockListTrips({ when = "all" } = {}) {
  await delay();
  const me = requireMockUser("EMPLOYEE");
  const today = todayISO();
  return loadTrips()
    .filter((t) => t.employee_id === me.employee_id)
    .filter((t) => when === "all" || (when === "upcoming" ? t.end_date >= today : t.end_date < today))
    .sort((a, b) => b.start_date.localeCompare(a.start_date))
    .map((t) => enrichTrip(t, me));
}

export async function mockGetTrip(tripId) {
  await delay();
  const me = requireMockUser();
  const trip = findVisibleTrip(loadTrips(), tripId, me);
  if (!trip) throw apiError(404, "NOT_FOUND");
  return enrichTrip(trip, me);
}

export async function mockCreateTrip(input) {
  await delay(600);
  const me = requireMockUser("EMPLOYEE");
  const errors = validateTrip(input);
  if (Object.keys(errors).length) throw validationError(errors);
  const trips = loadTrips();
  const id = Math.max(0, ...trips.map((t) => t.trip_id)) + 1;
  const now = nowISO();
  const trip = {
    trip_id: id, trip_code: code("TRP", id), employee_id: me.employee_id,
    destination: input.destination, start_date: input.start_date, end_date: input.end_date, purpose: input.purpose,
    approval_status: "IN_PROGRESS", trip_state: null, approvals: [],
    completion_type: null, completed_by: null, completed_by_name: null, completed_at: null,
    created_on: todayISO(), created_at: now, updated_at: now,
  };
  saveTrips([...trips, trip]);
  return enrichTrip(trip, me);
}

export async function mockUpdateTrip(tripId, input) {
  await delay(600);
  const me = requireMockUser("EMPLOYEE");
  const trips = loadTrips();
  const trip = trips.find((t) => t.trip_id === Number(tripId) && t.employee_id === me.employee_id);
  if (!trip) throw apiError(404, "NOT_FOUND");
  if (trip.approval_status !== "IN_PROGRESS") throw apiError(409, "TRIP_NOT_EDITABLE");
  const errors = validateTrip(input);
  if (Object.keys(errors).length) throw validationError(errors);
  Object.assign(trip, { ...input, updated_at: nowISO() });
  saveTrips(trips);
  return enrichTrip(trip, me);
}

export async function mockDecideTrip(tripId, { decision, review_comment }) {
  await delay(600);
  const me = requireMockUser("MANAGER");
  const trips = loadTrips();
  const trip = findVisibleTrip(trips, tripId, me);
  if (!trip) throw apiError(404, "NOT_FOUND");
  if (trip.employee_id === me.employee_id) throw apiError(403, "SELF_APPROVAL");
  if (trip.approval_status !== "IN_PROGRESS") throw apiError(409, "ALREADY_DECIDED");
  if (todayISO() >= addDaysISO(trip.start_date, TRIP_AUTO_COMPLETE_DAYS)) throw apiError(409, "TRIP_APPROVAL_WINDOW_PASSED");
  const comment = (review_comment ?? "").trim();
  if (decision === "REJECTED" && comment.length < MIN_REVIEW_COMMENT_CHARS) {
    throw validationError({ review_comment: `A review comment of at least ${MIN_REVIEW_COMMENT_CHARS} characters is required to reject` });
  }
  const now = nowISO();
  trip.approval_status = decision;
  trip.trip_state = decision === "APPROVED" ? "ACTIVE" : null;
  trip.updated_at = now;
  trip.approvals = [{
    approval_id: Date.now(), trip_id: trip.trip_id, reviewer_id: me.employee_id, reviewer_name: me.full_name,
    decision, review_comment: comment || null, decided_at: now,
  }];
  saveTrips(trips);
  return enrichTrip(trip, me);
}

export async function mockCompleteTrip(tripId) {
  await delay(600);
  const me = requireMockUser("MANAGER");
  const trips = loadTrips();
  const trip = findVisibleTrip(trips, tripId, me);
  if (!trip) throw apiError(404, "NOT_FOUND");
  if (trip.approval_status !== "APPROVED" || trip.trip_state !== "ACTIVE") throw apiError(409, "TRIP_NOT_ACTIVE");
  if (todayISO() < trip.end_date) throw apiError(409, "TRIP_NOT_FINISHED");
  const now = nowISO();
  Object.assign(trip, {
    trip_state: "COMPLETED", completion_type: "MANAGER", completed_by: me.employee_id,
    completed_by_name: me.full_name, completed_at: now, updated_at: now,
  });
  saveTrips(trips);
  return enrichTrip(trip, me);
}

// =====================================================================
// Manager queues (direct reports only)
// =====================================================================
export async function mockListPendingTrips() {
  await delay();
  const me = requireMockUser("MANAGER");
  return loadTrips()
    .filter((t) => t.approval_status === "IN_PROGRESS" && reportsTo(me, t.employee_id))
    .sort((a, b) => a.created_at.localeCompare(b.created_at))
    .map((t) => enrichTrip(t, me));
}

export async function mockListTripsToComplete() {
  await delay();
  const me = requireMockUser("MANAGER");
  return loadTrips()
    .filter((t) => t.trip_state === "ACTIVE" && reportsTo(me, t.employee_id) && todayISO() >= t.end_date)
    .sort((a, b) => a.end_date.localeCompare(b.end_date))
    .map((t) => enrichTrip(t, me));
}

export async function mockListPendingTickets() {
  await delay();
  const me = requireMockUser("MANAGER");
  const trips = loadTrips();
  return loadTickets()
    .filter((k) => k.status === "PENDING" && reportsTo(me, k.employee_id))
    .sort((a, b) => a.submitted_at.localeCompare(b.submitted_at))
    .map((k) => {
      const trip = trips.find((t) => t.trip_id === k.trip_id);
      return {
        ...summarizeTicket(k),
        trip_code: trip.trip_code,
        destination: trip.destination,
        employee_name: userById(k.employee_id).full_name,
        flag_codes: [...new Set(k.expenses.flatMap((l) => l.flags.map((f) => f.rule_code)))],
      };
    });
}

// =====================================================================
// Receipt photos (POST /evidence). Kept in memory: photos vanish on reload in mock mode.
// =====================================================================
const evidenceStore = new Map();

async function sha256Hex(file) {
  const hash = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return [...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function nextEvidenceNumber() {
  const fromTickets = loadTickets().flatMap((k) => k.expenses.map((l) => Number(l.evidence_code.slice(4))));
  const fromUploads = [...evidenceStore.values()].map((e) => Number(e.evidence_code.slice(4)));
  return Math.max(8, ...fromTickets, ...fromUploads) + 1;
}

export async function mockUploadEvidence(file) {
  await delay(500);
  const me = requireMockUser("EMPLOYEE");
  if (!EVIDENCE_TYPES.includes(file.type)) throw apiError(415, "EVIDENCE_INVALID_FILE");
  if (file.size > EVIDENCE_MAX_BYTES) throw apiError(413, "EVIDENCE_TOO_LARGE");
  const evidence = {
    evidence_id: crypto.randomUUID(),
    evidence_code: code("EVD", nextEvidenceNumber()),
    employee_id: me.employee_id,
    original_filename: file.name,
    mime_type: file.type,
    size_bytes: file.size,
    sha256: await sha256Hex(file),
    uploaded_at: nowISO(),
    attached: false,
    url: URL.createObjectURL(file),
  };
  evidenceStore.set(evidence.evidence_id, evidence);
  const { url, attached, employee_id, ...out } = evidence; // eslint-disable-line no-unused-vars
  return out;
}

export async function mockEvidenceUrl(evidenceId) {
  return evidenceStore.get(evidenceId)?.url ?? null;
}

export async function mockGetPolicyRules() {
  await delay(200);
  return {
    rules_version: "VGS-FIN-TE-001 v1.0",
    review_thresholds_inr: { ...POLICY_THRESHOLDS },
    hard_cap_per_line_inr: 200000,
    receipt_photo_required: true,
    evidence_max_bytes: EVIDENCE_MAX_BYTES,
    evidence_mime_types: EVIDENCE_TYPES,
    max_lines_per_ticket: 20,
  };
}

// =====================================================================
// Tickets: create (validation, policy engine, routing), detail, decision
// =====================================================================
function ticketDetail(ticket, trips = loadTrips()) {
  const trip = trips.find((t) => t.trip_id === ticket.trip_id);
  const all = loadTickets();
  const replacedBy = all.find((k) => k.replacement_of_ticket_id === ticket.ticket_id);
  const tripActive = trip.approval_status === "APPROVED" && trip.trip_state === "ACTIVE"
    && todayISO() < addDaysISO(trip.start_date, TRIP_AUTO_COMPLETE_DAYS);
  return {
    ...ticket,
    trip_code: trip.trip_code,
    destination: trip.destination,
    trip_start_date: trip.start_date,
    trip_end_date: trip.end_date,
    trip_purpose: trip.purpose,
    trip_status_label: statusLabel(trip.approval_status, trip.trip_state),
    employee_name: userById(ticket.employee_id).full_name,
    replaces_ticket_code: all.find((k) => k.ticket_id === ticket.replacement_of_ticket_id)?.ticket_code ?? null,
    replaced_by_ticket_id: replacedBy?.ticket_id ?? null,
    replaced_by_ticket_code: replacedBy?.ticket_code ?? null,
    // A rejected ticket can be replaced once, while its trip is still Approved - Active
    can_replace: ticket.status === "REJECTED" && !replacedBy && tripActive,
  };
}

export async function mockCreateTicket(tripId, body) {
  await delay(700);
  const me = requireMockUser("EMPLOYEE");
  const trips = loadTrips();
  const trip = trips.find((t) => t.trip_id === Number(tripId) && t.employee_id === me.employee_id);
  if (!trip) throw apiError(404, "NOT_FOUND");
  const active = trip.approval_status === "APPROVED" && trip.trip_state === "ACTIVE"
    && todayISO() < addDaysISO(trip.start_date, TRIP_AUTO_COMPLETE_DAYS);
  if (!active) throw apiError(409, "TRIP_NOT_ACTIVE");

  const lines = body.expenses ?? [];
  const errors = validateExpenseLines(lines, trip.created_on);
  if (Object.keys(errors).length) throw validationError(errors);

  const evidence = lines.map((l) => evidenceStore.get(l.evidence_id));
  if (evidence.some((e) => !e || e.employee_id !== me.employee_id)) throw apiError(404, "EVIDENCE_NOT_FOUND");
  if (evidence.some((e) => e.attached)) throw apiError(409, "EVIDENCE_ALREADY_USED");

  const tickets = loadTickets();
  const replacesId = body.replacement_of_ticket_id ? Number(body.replacement_of_ticket_id) : null;
  if (replacesId) {
    const old = tickets.find((k) => k.ticket_id === replacesId);
    const alreadyReplaced = tickets.some((k) => k.replacement_of_ticket_id === replacesId);
    if (!old || old.employee_id !== me.employee_id || old.trip_id !== trip.trip_id || old.status !== "REJECTED" || alreadyReplaced) {
      throw apiError(409, "REPLACEMENT_NOT_ALLOWED");
    }
  }

  // Policy engine: OVER_THRESHOLD and DUPLICATE_RECEIPT (ignoring rejected tickets)
  const previous = tickets.filter((k) => k.employee_id === me.employee_id && k.status !== "REJECTED").flatMap((k) => k.expenses);
  const knownHashes = new Set(previous.map((l) => l.sha256).filter(Boolean));
  const knownInvoices = new Set(previous.map((l) => l.invoice_number).filter(Boolean));
  const firstExpenseId = Math.max(0, ...tickets.flatMap((k) => k.expenses.map((l) => l.expense_id))) + 1;
  const ticketId = Math.max(0, ...tickets.map((k) => k.ticket_id)) + 1;

  const built = lines.map((l, i) => {
    const ev = evidence[i];
    const amount = Number(l.amount);
    const invoice = l.invoice_number ? l.invoice_number.trim().toUpperCase() : null;
    const flags = [];
    if (amount > POLICY_THRESHOLDS[l.expense_type]) flags.push(flag("OVER_THRESHOLD", l.expense_type));
    if (knownHashes.has(ev.sha256) || (invoice && knownInvoices.has(invoice))) flags.push(flag("DUPLICATE_RECEIPT", l.expense_type));
    const id = firstExpenseId + i;
    return {
      expense_id: id, expense_code: code("EXP", id), expense_type: l.expense_type, amount, currency: "INR",
      expense_date: l.expense_date, description: l.description.trim(), invoice_number: invoice,
      evidence_id: ev.evidence_id, evidence_code: ev.evidence_code, sha256: ev.sha256, flags,
    };
  });

  const flagCount = built.reduce((n, l) => n + l.flags.length, 0);
  const status = flagCount > 0 ? "PENDING" : "AUTO_APPROVED";
  const now = nowISO();
  const ticket = {
    ticket_id: ticketId, ticket_code: code("TKT", ticketId), trip_id: trip.trip_id, employee_id: me.employee_id,
    replacement_of_ticket_id: replacesId, status, routing: flagCount > 0 ? "MANAGER" : "AUTO",
    line_count: built.length, flag_count: flagCount,
    total_amount: built.reduce((s, l) => s + l.amount, 0),
    submitted_at: now, decided_at: flagCount > 0 ? null : now,
    expenses: built.map((l) => ({ ...l, status })),
    history: flagCount > 0 ? [] : [{
      approval_id: Date.now(), ticket_id: ticketId, reviewer_type: "SYSTEM", reviewer_id: null, reviewer_name: "SYSTEM",
      decision: "AUTO_APPROVED", rejection_reason: null, review_comment: null, decided_at: now,
    }],
  };
  saveStore(TICKETS_KEY, [...tickets, ticket]);
  evidence.forEach((e) => { e.attached = true; });
  return ticketDetail(ticket, trips);
}

export async function mockGetTicket(ticketId) {
  await delay();
  const me = requireMockUser();
  const ticket = loadTickets().find((k) => k.ticket_id === Number(ticketId));
  if (!ticket || (ticket.employee_id !== me.employee_id && !reportsTo(me, ticket.employee_id))) {
    throw apiError(404, "NOT_FOUND");
  }
  const detail = ticketDetail(ticket);
  return { ...detail, can_replace: detail.can_replace && ticket.employee_id === me.employee_id };
}

export async function mockDecideTicket(ticketId, body) {
  await delay(600);
  const me = requireMockUser("MANAGER");
  const tickets = loadTickets();
  const ticket = tickets.find((k) => k.ticket_id === Number(ticketId));
  if (!ticket || !reportsTo(me, ticket.employee_id)) throw apiError(404, "NOT_FOUND");
  if (ticket.status !== "PENDING") throw apiError(409, "ALREADY_DECIDED");

  const comment = (body.review_comment ?? "").trim();
  if (body.decision === "REJECTED") {
    const errors = {};
    if (!REJECTION_REASONS.some((r) => r.value === body.rejection_reason)) errors.rejection_reason = "Choose a rejection reason";
    if (comment.length < MIN_REVIEW_COMMENT_CHARS) {
      errors.review_comment = `A review comment of at least ${MIN_REVIEW_COMMENT_CHARS} characters is required to reject`;
    }
    if (Object.keys(errors).length) throw validationError(errors);
  } else if (body.decision === "APPROVED") {
    if (body.rejection_reason) throw validationError({ rejection_reason: "A rejection reason is not allowed when approving" });
  } else {
    throw validationError({ decision: "Decision must be APPROVED or REJECTED" });
  }

  const now = nowISO();
  ticket.status = body.decision;
  ticket.decided_at = now;
  ticket.expenses = ticket.expenses.map((l) => ({ ...l, status: body.decision }));
  ticket.history = [...ticket.history, {
    approval_id: Date.now(), ticket_id: ticket.ticket_id, reviewer_type: "MANAGER",
    reviewer_id: me.employee_id, reviewer_name: me.full_name, decision: body.decision,
    rejection_reason: body.decision === "REJECTED" ? body.rejection_reason : null,
    review_comment: comment || null, decided_at: now,
  }];
  saveStore(TICKETS_KEY, tickets);
  return ticketDetail(ticket);
}

// =====================================================================
// Employee dashboard (GET /dashboard/employee, new endpoint for Joyal)
// =====================================================================
export async function mockGetEmployeeDashboard() {
  await delay();
  const me = requireMockUser("EMPLOYEE");
  const trips = loadTrips().filter((t) => t.employee_id === me.employee_id).map((t) => enrichTrip(t, me));
  const claims = loadTickets().filter((k) => k.employee_id === me.employee_id && k.status !== "REJECTED");
  const byCategory = {};
  claims.flatMap((k) => k.expenses).forEach((l) => {
    byCategory[l.expense_type] = (byCategory[l.expense_type] ?? 0) + l.amount;
  });
  return {
    total_trips: trips.length,
    open_trips: trips.filter((t) => t.trip_state === "ACTIVE").length,
    pending_trip_approval: trips.filter((t) => t.approval_status === "IN_PROGRESS").length,
    total_claimed: claims.reduce((s, k) => s + k.total_amount, 0),
    recent_trips: [...trips].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 5),
    spend_by_category: Object.entries(byCategory)
      .map(([expense_type, total_amount]) => ({ expense_type, total_amount }))
      .sort((a, b) => b.total_amount - a.total_amount),
  };
}

// =====================================================================
// Reports (Spending Summary): the three required SQL demonstrations
// =====================================================================
function teamTicketsWithTrips(me) {
  const trips = loadTrips();
  return loadTickets()
    .filter((k) => reportsTo(me, k.employee_id))
    .map((k) => ({ ticket: k, trip: trips.find((t) => t.trip_id === k.trip_id) }));
}

/** SQL 1: JOIN employees + trips + expenses */
export async function mockReportTripExpenses() {
  await delay();
  const me = requireMockUser("MANAGER");
  return teamTicketsWithTrips(me)
    .flatMap(({ ticket, trip }) => ticket.expenses.map((l) => ({
      employee_name: userById(ticket.employee_id).full_name,
      trip_code: trip.trip_code,
      destination: trip.destination,
      expense_code: l.expense_code,
      expense_type: l.expense_type,
      amount: l.amount,
      status: l.status,
    })))
    .sort((a, b) => a.trip_code.localeCompare(b.trip_code) || a.expense_code.localeCompare(b.expense_code));
}

/** SQL 2: approved money by trip and category, plus a trip total row (expense_type = null) */
export async function mockReportSpendByTripCategory() {
  await delay();
  const me = requireMockUser("MANAGER");
  const groups = new Map();
  for (const { ticket, trip } of teamTicketsWithTrips(me)) {
    for (const l of ticket.expenses) {
      if (!["APPROVED", "AUTO_APPROVED"].includes(l.status)) continue;
      for (const type of [l.expense_type, null]) { // category row and trip total row
        const key = `${trip.trip_code}|${type}`;
        const row = groups.get(key) ?? { trip_code: trip.trip_code, destination: trip.destination, expense_type: type, line_count: 0, total_amount: 0 };
        row.line_count += 1;
        row.total_amount += l.amount;
        groups.set(key, row);
      }
    }
  }
  return [...groups.values()].sort((a, b) =>
    a.trip_code.localeCompare(b.trip_code)
    || (a.expense_type === null) - (b.expense_type === null)  // NULLS LAST
    || String(a.expense_type).localeCompare(String(b.expense_type)));
}

/** SQL 3: flagged lines in PENDING tickets */
export async function mockListPendingExpenses() {
  await delay();
  const me = requireMockUser("MANAGER");
  return teamTicketsWithTrips(me)
    .filter(({ ticket }) => ticket.status === "PENDING")
    .flatMap(({ ticket, trip }) => ticket.expenses
      .filter((l) => l.flags.length > 0)
      .map((l) => ({
        expense_id: l.expense_id,
        expense_code: l.expense_code,
        ticket_id: ticket.ticket_id,
        ticket_code: ticket.ticket_code,
        trip_code: trip.trip_code,
        employee_name: userById(ticket.employee_id).full_name,
        destination: trip.destination,
        expense_type: l.expense_type,
        amount: l.amount,
        flag_codes: l.flags.map((f) => f.rule_code).sort(),
        submitted_at: ticket.submitted_at,
      })))
    .sort((a, b) => a.submitted_at.localeCompare(b.submitted_at));
}

// =====================================================================
// Vera chat (rule-based stand-in for Piyush's backend). Replies use the
// EXACT ChatReplyOut shape from docs/vera_sample_replies.json.
// The mock understands dates only as YYYY-MM-DD.
// Type "simulate timeout" in a weather question to test the Retry button.
// =====================================================================
const chatSessions = new Map();
const VERA_INTRO = "Hi, I'm Vera, Veridian Global's travel assistant. I can explain our expense policy and how to use TravelDesk, and check the weather for a destination and dates you give me.";
const WEATHER_RE = /\b(weather|rain|temperature|forecast|pack|wear|umbrella|cold|hot|wind|humid)\b/i;
const POLICY_RE = /\b(expense|claim|receipt|photo|limit|policy|reimburse|ticket|flag|category|meal|meals|hotel|lodging|airfare|threshold)\b/i;
const BUSINESS_RE = /\b(my trips?|my tickets?|status of|TKT-\d+|TRP-\d+)\b/i;
const GREETING_RE = /^(hi|hello|hey|thanks|thank you|bye)\b/i;
const INJECTION_RE = /(ignore (all |the )?previous|system prompt|act as (a )?manager|developer mode)/i;
const WEATHER_DISCLAIMER = "Weather guidance is informational only. It is not an approval, a booking or a safety guarantee.";

const tool = (tool_name, status = "ok", error_code = null) => ({ tool_name, status, error_code, latency_ms: 12 });
const fmtDay = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

function mockWeather(place, from, to) {
  const today = todayISO();
  const horizonEnd = addDaysISO(today, 15);
  const dates = [];
  for (let d = from; d <= to && dates.length < 30; d = addDaysISO(d, 1)) dates.push(d);
  const covered = dates.filter((d) => d >= today && d <= horizonEnd);
  const uncovered = dates.filter((d) => !covered.includes(d));
  const days = covered.map((d, i) => ({
    date: d,
    condition: i % 3 === 1 ? "Light rain" : "Partly cloudy",
    temp_min_c: 19.4 + (i % 2),
    temp_max_c: 26.8 + (i % 3) * 0.5,
    precipitation_probability_max_pct: i % 3 === 1 ? 70 : 20,
    precipitation_sum_mm: i % 3 === 1 ? 3.2 : 0,
    wind_speed_max_kmh: 14 + i,
  }));
  const rainy = days.some((d) => d.precipitation_probability_max_pct >= 50);
  const lows = days.map((d) => d.temp_min_c);
  const highs = days.map((d) => d.temp_max_c);
  const resolved = `${place} (mock data)`;
  const range = `${fmtDay(from)} to ${fmtDay(to)}`;
  const retrieved = nowISO();

  const summary = days.length
    ? `${place} looks ${rainy ? "wet" : "mostly dry"} for your trip: temperatures between ${Math.min(...lows)} °C and ${Math.max(...highs)} °C${rainy ? ", rain chance up to 70%" : ""}.`
    : `Forecast not available for ${resolved} on ${range}.`;
  const checklist = days.length
    ? [rainy ? "Umbrella or raincoat - rain chance up to 70%" : "Sunglasses for bright afternoons", "Light, breathable clothing", `A light layer for the ${Math.min(...lows)} °C mornings`]
    : ["Comfortable shoes for meetings and getting around", "Your ID and travel documents", "Phone charger and a power bank"];
  const limitations = [`Forecast from Open-Meteo (mock), retrieved ${formatTime(retrieved)}; forecasts can change.`];
  if (uncovered.length) limitations.push(`Forecast not available for ${fmtDay(uncovered[0])} to ${fmtDay(uncovered[uncovered.length - 1])} (outside the 16-day forecast range). Check again closer to travel.`);

  return {
    covered,
    reply: days.length
      ? `${summary}\n\nWhat to pack:\n${checklist.map((c) => `• ${c}`).join("\n")}\n\nForecasts can change, so check again a day before you travel.`
      : `Forecast not available for ${resolved} on ${range}. Forecasts cover today plus 15 days, so please ask again closer to your travel date.`,
    weather: {
      destination: place,
      forecast_basis: {
        source: "Open-Meteo", resolved_location: resolved, date_from: from, date_to: to,
        forecast_available: covered.length > 0,
        coverage: covered.length === dates.length ? "FULL" : covered.length ? "PARTIAL" : "NONE",
        covered_dates: covered, uncovered_dates: uncovered, retrieved_at: retrieved,
      },
      weather_summary: summary,
      travel_checklist: checklist,
      limitations,
      disclaimer: WEATHER_DISCLAIMER,
      days, // proposed field (open team decision); the card shows a daily table only when it is present
    },
  };
}

function formatTime(iso) {
  return new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function mockVeraAnswer(text, session) {
  const base = { intent: "OUT_OF_SCOPE", citations: [], weather: null, tools_used: [], guardrail_status: "PASSED", status: "COMPLETED", error_code: null, retryable: false };

  if (INJECTION_RE.test(text)) {
    return { ...base, guardrail_status: "INPUT_BLOCKED", status: "BLOCKED",
      reply: "I can't help with that request. I can answer questions about the expense policy, using TravelDesk, or the weather for a destination and dates you give me." };
  }
  if (BUSINESS_RE.test(text)) {
    return { ...base, reply: "I can't see your trips, tickets or expenses. Please open My Trips to check them." };
  }
  if (WEATHER_RE.test(text)) {
    const w = { ...base, intent: "WEATHER" };
    if (/\b(pack|wear)\b/i.test(text) && session.lastWeather) {
      return { ...w, reply: `Based on the forecast in this chat:\n\nWhat to pack:\n${session.lastWeather.travel_checklist.map((c) => `• ${c}`).join("\n")}`, weather: session.lastWeather };
    }
    const dates = text.match(/\d{4}-\d{2}-\d{2}/g) ?? [];
    const place = text.match(/\b(?:in|to|for)\s+([A-Z][a-zA-Z]+)/)?.[1];
    if (!place) return { ...w, reply: "Sure - which destination and dates? For example: weather in Bengaluru from 2026-11-24 to 2026-11-27." };
    if (dates.length < 2) return { ...w, reply: `Sure - which dates will you be in ${place}? Please give a start and end date (YYYY-MM-DD in mock mode).` };
    if (/simulate timeout/i.test(text)) {
      return { ...w, status: "FAILED", error_code: "WEATHER_TIMEOUT", retryable: true,
        tools_used: [tool("get_weather_forecast", "error", "WEATHER_TIMEOUT")],
        reply: "The weather service did not answer in time. Please try again." };
    }
    const result = mockWeather(place, dates[0], dates[1]);
    session.lastWeather = result.weather;
    return { ...w, reply: result.reply, weather: result.weather,
      tools_used: [tool("get_weather_forecast", "ok", result.covered.length ? null : "FORECAST_OUT_OF_RANGE")] };
  }
  if (POLICY_RE.test(text)) {
    const p = { ...base, intent: "POLICY", tools_used: [tool("search_expense_policy")] };
    if (/\bmeals?\b/i.test(text)) {
      return { ...p, reply: "A MEALS line above INR 1,500 goes to your manager for review; up to 1,500 is fine. [POL-6.2]",
        citations: [{ ref_id: "POL-6.2", title: "Review thresholds", similarity: 0.82 }] };
    }
    if (/\b(receipt|photo)\b/i.test(text)) {
      return { ...p, reply: "Every expense line needs its own receipt photo (JPEG, PNG or WEBP, up to 5 MB). A line without one can't be submitted. [POL-7.1]",
        citations: [{ ref_id: "POL-7.1", title: "Receipt photos", similarity: 0.79 }] };
    }
    return { ...p, reply: "I couldn't find this in the expense policy. Please contact Finance Operations at finance.ops@veridian.example." };
  }
  if (GREETING_RE.test(text)) return { ...base, intent: "GREETING", reply: "Hello! Ask me about the expense policy or the weather for a trip." };
  return { ...base, reply: "I can only help with the expense policy, using TravelDesk, and the weather for a destination and dates you give me." };
}

function ownSession(sessionId, me) {
  const s = chatSessions.get(sessionId);
  if (!s || s.employee_id !== me.employee_id) throw apiError(404, "NOT_FOUND");
  return s;
}

export async function mockChatCreate() {
  await delay(300);
  const me = requireMockUser("EMPLOYEE");
  for (const s of chatSessions.values()) {
    if (s.employee_id === me.employee_id && s.status === "ACTIVE") {
      Object.assign(s, { status: "CLOSED", close_reason: "REPLACED", closed_at: nowISO() });
    }
  }
  const session = {
    session_id: crypto.randomUUID(), employee_id: me.employee_id, status: "ACTIVE", close_reason: null,
    started_at: nowISO(), closed_at: null, last_activity: Date.now(), turn_count: 0, messages: [], preview: null,
  };
  chatSessions.set(session.session_id, session);
  return { session_id: session.session_id, status: "ACTIVE", intro_message: VERA_INTRO, idle_timeout_minutes: 60, started_at: session.started_at };
}

export async function mockChatSend(sessionId, message) {
  await delay(900);
  const me = requireMockUser("EMPLOYEE");
  const s = ownSession(sessionId, me);
  if (s.status === "ACTIVE" && Date.now() - s.last_activity > 60 * 60 * 1000) {
    Object.assign(s, { status: "EXPIRED", close_reason: "IDLE_TIMEOUT", closed_at: nowISO() });
  }
  if (s.status === "EXPIRED") throw apiError(410, "SESSION_EXPIRED");
  if (s.status === "CLOSED") throw apiError(410, "SESSION_CLOSED");
  const text = message.trim();
  if (!text || text.length > 1000) throw validationError({ message: "A message must be 1 to 1000 characters" });

  const answer = mockVeraAnswer(text, s);
  const now = nowISO();
  s.turn_count += 1;
  s.last_activity = Date.now();
  s.preview = s.preview ?? text.slice(0, 60);
  s.messages.push(
    { message_id: s.messages.length + 1, message_type: "human_message", content: text, metadata: null, created_at: now },
    { message_id: s.messages.length + 2, message_type: "ai_response", content: answer.reply,
      metadata: { citations: answer.citations, weather: answer.weather }, created_at: now },
  );
  return { session_id: sessionId, conversation_id: crypto.randomUUID(), turn_number: s.turn_count, ...answer, created_at: now };
}

export async function mockChatList() {
  await delay(300);
  const me = requireMockUser("EMPLOYEE");
  return [...chatSessions.values()]
    .filter((s) => s.employee_id === me.employee_id)
    .sort((a, b) => b.started_at.localeCompare(a.started_at))
    .map((s) => ({
      session_id: s.session_id, status: s.status, started_at: s.started_at, closed_at: s.closed_at,
      close_reason: s.close_reason, first_message_preview: s.preview, turn_count: s.turn_count,
    }));
}

export async function mockChatHistory(sessionId) {
  await delay(300);
  const me = requireMockUser("EMPLOYEE");
  const s = ownSession(sessionId, me);
  return {
    session_id: sessionId, status: s.status, read_only: s.status !== "ACTIVE",
    messages: s.messages.map((m, i) => ({ ...m, sequence_no: i + 1 })),
  };
}

export async function mockChatClose(sessionId) {
  await delay(200);
  const me = requireMockUser("EMPLOYEE");
  const s = ownSession(sessionId, me);
  if (s.status === "ACTIVE") Object.assign(s, { status: "CLOSED", close_reason: "USER_CLOSED", closed_at: nowISO() });
  return { session_id: sessionId, status: s.status, close_reason: s.close_reason, closed_at: s.closed_at };
}
