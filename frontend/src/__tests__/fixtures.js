// Fake data for tests. No imports here, so the API mocks can load it safely.
export const mockAuth = {
  user: null, isManager: false, checking: false, sessionMessage: null, login: () => {}, logout: () => {},
};

export const TRIP = {
  trip_id: 2, trip_code: "TRP-00002", employee_id: 3, employee_name: "Rohan Mehta", department: "Tax",
  destination: "Bengaluru", start_date: "2026-12-01", end_date: "2026-12-04", purpose: "Client workshop for FY27 audit planning",
  approval_status: "APPROVED", trip_state: "ACTIVE", status_label: "Approved - Active",
  can_edit: false, can_raise_ticket: true, can_complete: false, is_owner: true,
  auto_complete_on: "2027-03-01", created_on: "2026-11-20", created_at: "2026-11-20T09:00:00",
  ticket_count: 0, total_claimed: 0, approvals: [], tickets: [],
};

export const TICKET = {
  ticket_id: 3, ticket_code: "TKT-00003", trip_id: 2, trip_code: "TRP-00002", destination: "Bengaluru",
  employee_id: 3, employee_name: "Rohan Mehta", status: "PENDING", routing: "MANAGER",
  line_count: 0, flag_count: 0, total_amount: 0, submitted_at: "2026-11-20T12:00:00",
  can_create_replacement: false, expenses: [], history: [],
};

export const DASHBOARD = {
  total_trips: 0, open_trips: 0, pending_trip_approval: 0, total_claimed: 0, recent_trips: [], spend_by_category: [],
};
