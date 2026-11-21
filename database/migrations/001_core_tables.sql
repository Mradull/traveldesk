-- employees, travel_requests, trip_approvals (Agile Spec v2.0, Table definitions).
-- Owner: Joyal (M1)  |  Spec: Agile Spec v2.0

CREATE TABLE employees (
    employee_id SERIAL PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    department TEXT NOT NULL,
    role TEXT NOT NULL
        CHECK (role IN ('EMPLOYEE', 'MANAGER')),
    manager_id INT
        REFERENCES employees (employee_id) ON DELETE RESTRICT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_employees_email_lowercase
        CHECK (email = lower(email)),
    CONSTRAINT ck_employees_manager_not_self
        CHECK (manager_id IS NULL OR manager_id <> employee_id),
    CONSTRAINT ck_managers_have_no_manager
        CHECK (role <> 'MANAGER' OR manager_id IS NULL)
);

CREATE TABLE travel_requests (
    trip_id SERIAL PRIMARY KEY,
    trip_code TEXT GENERATED ALWAYS AS (
        'TRP-' || lpad(trip_id::text, 5, '0')
    ) STORED UNIQUE,
    employee_id INT NOT NULL
        REFERENCES employees (employee_id) ON DELETE RESTRICT,
    destination TEXT NOT NULL
        CHECK (length(destination) BETWEEN 2 AND 100),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    purpose TEXT NOT NULL
        CHECK (length(purpose) BETWEEN 10 AND 500),
    approval_status TEXT NOT NULL DEFAULT 'IN_PROGRESS'
        CHECK (approval_status IN ('IN_PROGRESS', 'APPROVED', 'REJECTED')),
    trip_state TEXT
        CHECK (trip_state IN ('ACTIVE', 'COMPLETED')),
    completion_type TEXT
        CHECK (completion_type IN ('MANAGER', 'AUTO')),
    completed_by INT
        REFERENCES employees (employee_id) ON DELETE RESTRICT,
    completed_at TIMESTAMPTZ,
    created_on DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_travel_requests_end_after_start
        CHECK (end_date > start_date),
    CONSTRAINT ck_travel_requests_max_duration
        CHECK (end_date - start_date <= 29),
    CONSTRAINT ck_travel_requests_approval_trip_state
        CHECK ((approval_status = 'APPROVED') = (trip_state IS NOT NULL)),
    CONSTRAINT ck_travel_requests_completion_type
        CHECK (
            (trip_state = 'COMPLETED' AND completion_type IS NOT NULL)
            OR (trip_state IS DISTINCT FROM 'COMPLETED' AND completion_type IS NULL)
        ),
    CONSTRAINT ck_travel_requests_completed_by
        CHECK (
            (completion_type = 'MANAGER' AND completed_by IS NOT NULL)
            OR (completion_type IS DISTINCT FROM 'MANAGER' AND completed_by IS NULL)
        )
);

CREATE TABLE trip_approvals (
    approval_id SERIAL PRIMARY KEY,
    trip_id INT NOT NULL UNIQUE
        REFERENCES travel_requests (trip_id) ON DELETE RESTRICT,
    reviewer_id INT NOT NULL
        REFERENCES employees (employee_id) ON DELETE RESTRICT,
    decision TEXT NOT NULL
        CHECK (decision IN ('APPROVED', 'REJECTED')),
    review_comment TEXT,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_trip_approvals_rejection_comment
        CHECK (
            decision = 'APPROVED'
            OR length(trim(COALESCE(review_comment, ''))) >= 10
        )
);

CREATE FUNCTION set_travel_request_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_travel_requests_updated_at
BEFORE UPDATE ON travel_requests
FOR EACH ROW
EXECUTE FUNCTION set_travel_request_updated_at();
