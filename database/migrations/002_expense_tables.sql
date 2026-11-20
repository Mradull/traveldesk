-- evidence_code_seq, expense_evidence, evidence_files, expense_tickets, expenses, policy_flags, ticket_approvals.
-- Owner: Joyal (M1)  |  Spec: Agile Spec v2.0

CREATE SEQUENCE evidence_code_seq;

CREATE TABLE expense_evidence (
    evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evidence_code TEXT NOT NULL UNIQUE DEFAULT (
        'EVD-' || lpad(nextval('evidence_code_seq')::text, 5, '0')
    ),
    employee_id INT NOT NULL
        REFERENCES employees (employee_id) ON DELETE RESTRICT,
    original_filename TEXT NOT NULL,
    mime_type TEXT NOT NULL
        CHECK (mime_type IN ('image/jpeg', 'image/png', 'image/webp')),
    size_bytes INT NOT NULL
        CHECK (size_bytes BETWEEN 1 AND 5242880),
    sha256 CHAR(64) NOT NULL
        CHECK (length(sha256) = 64),
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE evidence_files (
    evidence_id UUID PRIMARY KEY
        REFERENCES expense_evidence (evidence_id) ON DELETE CASCADE,
    content BYTEA NOT NULL
);

CREATE TABLE expense_tickets (
    ticket_id SERIAL PRIMARY KEY,
    ticket_code TEXT GENERATED ALWAYS AS (
        'TKT-' || lpad(ticket_id::text, 5, '0')
    ) STORED UNIQUE,
    trip_id INT NOT NULL
        REFERENCES travel_requests (trip_id) ON DELETE RESTRICT,
    employee_id INT NOT NULL
        REFERENCES employees (employee_id) ON DELETE RESTRICT,
    replacement_of_ticket_id INT UNIQUE
        REFERENCES expense_tickets (ticket_id) ON DELETE RESTRICT,
    status TEXT NOT NULL
        CHECK (status IN ('PENDING', 'AUTO_APPROVED', 'APPROVED', 'REJECTED')),
    routing TEXT NOT NULL
        CHECK (routing IN ('AUTO', 'MANAGER')),
    line_count INT NOT NULL
        CHECK (line_count BETWEEN 1 AND 20),
    flag_count INT NOT NULL
        CHECK (flag_count >= 0),
    total_amount NUMERIC(12, 2) NOT NULL
        CHECK (total_amount > 0),
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at TIMESTAMPTZ,
    CONSTRAINT uq_expense_tickets_ticket_trip UNIQUE (ticket_id, trip_id),
    CONSTRAINT ck_expense_tickets_pending_decision_time
        CHECK ((status = 'PENDING') = (decided_at IS NULL)),
    CONSTRAINT ck_expense_tickets_routing_status
        CHECK (
            (status = 'AUTO_APPROVED' AND routing = 'AUTO')
            OR (status <> 'AUTO_APPROVED' AND routing = 'MANAGER')
        )
);

CREATE TABLE expenses (
    expense_id SERIAL PRIMARY KEY,
    expense_code TEXT GENERATED ALWAYS AS (
        'EXP-' || lpad(expense_id::text, 5, '0')
    ) STORED UNIQUE,
    ticket_id INT NOT NULL,
    trip_id INT NOT NULL
        REFERENCES travel_requests (trip_id) ON DELETE RESTRICT,
    evidence_id UUID NOT NULL UNIQUE
        REFERENCES expense_evidence (evidence_id) ON DELETE RESTRICT,
    expense_type TEXT NOT NULL
        CHECK (
            expense_type IN (
                'AIRFARE',
                'LODGING',
                'MEALS',
                'GROUND_TRANSPORT',
                'INCIDENTALS'
            )
        ),
    amount NUMERIC(12, 2) NOT NULL
        CHECK (amount > 0 AND amount <= 200000),
    currency CHAR(3) NOT NULL DEFAULT 'INR'
        CHECK (currency = 'INR'),
    expense_date DATE NOT NULL,
    description TEXT NOT NULL,
    invoice_number TEXT,
    status TEXT NOT NULL
        CHECK (status IN ('PENDING', 'AUTO_APPROVED', 'APPROVED', 'REJECTED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_expenses_ticket_trip
        FOREIGN KEY (ticket_id, trip_id)
        REFERENCES expense_tickets (ticket_id, trip_id) ON DELETE RESTRICT
);

CREATE TABLE policy_flags (
    flag_id SERIAL PRIMARY KEY,
    expense_id INT NOT NULL
        REFERENCES expenses (expense_id) ON DELETE RESTRICT,
    rule_code TEXT NOT NULL
        CHECK (rule_code IN ('OVER_THRESHOLD', 'DUPLICATE_RECEIPT')),
    message TEXT NOT NULL,
    policy_ref TEXT NOT NULL,
    threshold_amount NUMERIC(12, 2),
    rules_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_policy_flags_expense_rule UNIQUE (expense_id, rule_code),
    CONSTRAINT ck_policy_flags_threshold
        CHECK ((rule_code = 'OVER_THRESHOLD') = (threshold_amount IS NOT NULL))
);

CREATE TABLE ticket_approvals (
    approval_id SERIAL PRIMARY KEY,
    ticket_id INT NOT NULL UNIQUE
        REFERENCES expense_tickets (ticket_id) ON DELETE RESTRICT,
    reviewer_type TEXT NOT NULL
        CHECK (reviewer_type IN ('MANAGER', 'SYSTEM')),
    reviewer_id INT
        REFERENCES employees (employee_id) ON DELETE RESTRICT,
    decision TEXT NOT NULL
        CHECK (decision IN ('APPROVED', 'REJECTED', 'AUTO_APPROVED')),
    rejection_reason TEXT
        CHECK (
            rejection_reason IN (
                'MISSING_EVIDENCE',
                'INSUFFICIENT_EVIDENCE',
                'INCORRECT_EVIDENCE',
                'UNCLEAR_PURPOSE',
                'POLICY_CONCERN',
                'OTHER'
            )
        ),
    review_comment TEXT,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_ticket_approvals_reviewer
        CHECK ((reviewer_type = 'SYSTEM') = (reviewer_id IS NULL)),
    CONSTRAINT ck_ticket_approvals_rejection_reason
        CHECK ((decision = 'REJECTED') = (rejection_reason IS NOT NULL)),
    CONSTRAINT ck_ticket_approvals_rejection_comment
        CHECK (
            decision <> 'REJECTED'
            OR length(trim(COALESCE(review_comment, ''))) >= 10
        )
);
