-- All indexes listed in Agile Spec v2.0 > Indexes, integrity and immutability.
-- Owner: Joyal (M1); chat indexes sent by Piyush (M2)  |  Spec: Agile Spec v2.0
-- An index is like a book's index: PostgreSQL finds rows without reading the whole table.

-- =============================================================================
-- [J] Joyal (M1): business and error-log indexes
-- =============================================================================
-- My Trips list (one employee's trips)
CREATE INDEX IF NOT EXISTS ix_travel_requests_employee ON travel_requests (employee_id);
-- Manager queues (In Progress trips, Active trips)
CREATE INDEX IF NOT EXISTS ix_travel_requests_status_state ON travel_requests (approval_status, trip_state);
-- Hourly auto-complete job (Active trips whose start date + 90 days has passed)
CREATE INDEX IF NOT EXISTS ix_travel_requests_state_start ON travel_requests (trip_state, start_date);
-- Tickets of one trip
CREATE INDEX IF NOT EXISTS ix_expense_tickets_trip ON expense_tickets (trip_id);
-- Expense Management list and status filters
CREATE INDEX IF NOT EXISTS ix_expense_tickets_employee_status ON expense_tickets (employee_id, status);
-- Lines of one ticket / one trip
CREATE INDEX IF NOT EXISTS ix_expenses_ticket ON expenses (ticket_id);
CREATE INDEX IF NOT EXISTS ix_expenses_trip ON expenses (trip_id);
-- DUPLICATE_RECEIPT check by invoice number (case-insensitive)
CREATE INDEX IF NOT EXISTS ix_expenses_invoice_upper ON expenses (upper(invoice_number));
-- DUPLICATE_RECEIPT check by photo hash
CREATE INDEX IF NOT EXISTS ix_expense_evidence_employee_sha256 ON expense_evidence (employee_id, sha256);
-- Newest errors first, and tracing one request across components
CREATE INDEX IF NOT EXISTS ix_error_logs_occurred ON error_logs (occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_error_logs_correlation ON error_logs (correlation_id);

-- =============================================================================
-- [P] Piyush (M2): chat indexes. Copied exactly from Piyush's file (Google Drive, 2026-11-20).
-- =============================================================================

-- [P] Past chats list: an employee's sessions, newest first.
CREATE INDEX IF NOT EXISTS ix_chat_sessions_employee_started ON chat_sessions (employee_id, started_at DESC);
-- [P] Loading one session's messages in order (history, transcript).
CREATE INDEX IF NOT EXISTS ix_chat_messages_session_created ON chat_messages (session_id, created_at);
