-- Triggers: decided tickets/lines/evidence and approval rows immutable; expense_date >= trip created_on;
-- tickets only on APPROVED + ACTIVE trips.
-- Owner: Joyal (M1)  |  Spec: Agile Spec v2.0 > Indexes, integrity and immutability (migration 006)
--
-- Why triggers: the API already refuses these changes, but a trigger is the database's own lock,
-- so even a direct edit in pgAdmin cannot rewrite a decision. Each trigger raises an error whose
-- MESSAGE is the schemas.ErrorCode the service maps it to (e.g. TICKET_READ_ONLY).
-- TRUNCATE does not fire these row triggers, so test clean-up still works.

-- =============================================================================
-- (1) Decided tickets, their expense lines and their evidence are read-only.
--     Only the PENDING -> decided transition is allowed. A manager decision therefore
--     updates the lines FIRST (ticket still PENDING) and the ticket LAST (spec > Transactions).
-- =============================================================================
CREATE FUNCTION block_change_of_decided_ticket()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status <> 'PENDING' THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0001',
            MESSAGE = 'TICKET_READ_ONLY',
            DETAIL = format('Ticket %s is %s and cannot be changed or deleted.', OLD.ticket_code, OLD.status);
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_expense_tickets_read_only
BEFORE UPDATE OR DELETE ON expense_tickets
FOR EACH ROW
EXECUTE FUNCTION block_change_of_decided_ticket();

CREATE FUNCTION block_change_of_decided_expense()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    ticket_status TEXT;
BEGIN
    SELECT status INTO ticket_status
    FROM expense_tickets
    WHERE ticket_id = OLD.ticket_id;

    IF ticket_status <> 'PENDING' THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0001',
            MESSAGE = 'TICKET_READ_ONLY',
            DETAIL = format('Expense %s belongs to a decided ticket and cannot be changed or deleted.', OLD.expense_code);
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_expenses_read_only
BEFORE UPDATE OR DELETE ON expenses
FOR EACH ROW
EXECUTE FUNCTION block_change_of_decided_expense();

-- Evidence (metadata row and photo bytes) attached to a line of a decided ticket is frozen too.
-- Unattached uploads stay deletable, so the 24-hour clean-up job keeps working.
CREATE FUNCTION block_change_of_decided_evidence()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM expenses AS x
        JOIN expense_tickets AS k ON k.ticket_id = x.ticket_id
        WHERE x.evidence_id = OLD.evidence_id
          AND k.status <> 'PENDING'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0001',
            MESSAGE = 'TICKET_READ_ONLY',
            DETAIL = 'This receipt photo belongs to a decided ticket and cannot be changed or deleted.';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_expense_evidence_read_only
BEFORE UPDATE OR DELETE ON expense_evidence
FOR EACH ROW
EXECUTE FUNCTION block_change_of_decided_evidence();

CREATE TRIGGER trg_evidence_files_read_only
BEFORE UPDATE OR DELETE ON evidence_files
FOR EACH ROW
EXECUTE FUNCTION block_change_of_decided_evidence();

-- =============================================================================
-- (2) Decision history rows are never changed or deleted (trip and ticket approvals).
-- =============================================================================
CREATE FUNCTION block_change_of_approval_history()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION USING
        ERRCODE = 'P0001',
        MESSAGE = 'ALREADY_DECIDED',
        DETAIL = format('Rows in %s are permanent decision history and cannot be changed or deleted.', TG_TABLE_NAME);
END;
$$;

CREATE TRIGGER trg_trip_approvals_read_only
BEFORE UPDATE OR DELETE ON trip_approvals
FOR EACH ROW
EXECUTE FUNCTION block_change_of_approval_history();

CREATE TRIGGER trg_ticket_approvals_read_only
BEFORE UPDATE OR DELETE ON ticket_approvals
FOR EACH ROW
EXECUTE FUNCTION block_change_of_approval_history();

-- =============================================================================
-- (3) An expense date may not be before the date its trip was created [POL-8.2].
--     Backstop for TicketService (which reports it on field expenses.<n>.expense_date).
-- =============================================================================
CREATE FUNCTION check_expense_date_after_trip_created()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    trip_created_on DATE;
BEGIN
    SELECT created_on INTO trip_created_on
    FROM travel_requests
    WHERE trip_id = NEW.trip_id;

    IF NEW.expense_date < trip_created_on THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0001',
            MESSAGE = 'EXPENSE_DATE_BEFORE_TRIP_CREATED',
            DETAIL = format('Expense date %s is before the trip was created on %s.', NEW.expense_date, trip_created_on);
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_expenses_date_after_trip_created
BEFORE INSERT OR UPDATE OF expense_date, trip_id ON expenses
FOR EACH ROW
EXECUTE FUNCTION check_expense_date_after_trip_created();

-- =============================================================================
-- (4) A ticket can only be inserted on an Approved - Active trip.
--     Backstop for TicketService (409 TRIP_NOT_ACTIVE).
-- =============================================================================
CREATE FUNCTION check_ticket_trip_is_active()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM travel_requests
        WHERE trip_id = NEW.trip_id
          AND approval_status = 'APPROVED'
          AND trip_state = 'ACTIVE'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0001',
            MESSAGE = 'TRIP_NOT_ACTIVE',
            DETAIL = 'Tickets can only be raised on Approved - Active trips.';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_expense_tickets_trip_active
BEFORE INSERT ON expense_tickets
FOR EACH ROW
EXECUTE FUNCTION check_ticket_trip_is_active();
